# -*- coding: utf-8 -*-
"""
main.py – FastAPI backend, thuần theo arXiv 2504.08384
=======================================================
Endpoints:
  POST /ensemble-search   Alg.3 — search → rerank từng model → ensemble
  POST /single-search     Một model duy nhất (beit3 hoặc clip) — phục vụ Q4
  POST /temporal-search   Alg.4 — cặp frame bắt đầu/kết thúc
  GET  /status            Còn thiếu file gì
  GET  /health            Kiểm tra sống

Đã BỎ toàn bộ endpoint cũ: /text-search, /text-no-agent-search, /faiss-search,
/ocr-search, /combined-search, /filter-search. Chúng đọc temp.json với các
trường content/ocr/object/color/action của mùa trước — pipeline hiện tại không
sinh ra file đó, nên chúng luôn trả rỗng mà vẫn HTTP 200 (thất bại im lặng).

Tuyến từ vựng (OCR / ASR / caption / tag → BM25 → RRF) CHƯA có ở đây. Đó là
nửa dưới của sơ đồ online, sẽ thêm sau khi chốt Q5/Q6.
"""

import os
import threading
import time
from contextlib import asynccontextmanager
from datetime import datetime
from typing import List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.models import SearchResult, SearchResponse
from app.version import SHORT_COMMIT, VERSION
from app.preprocess import (
    ensemble_search,
    single_model_search,
    temporal_search,
    system_status,
    preload,
    MODEL_NAMES,
)

# ─────────────────────────────────────────────────────────────────────────────
#  Schemas
# ─────────────────────────────────────────────────────────────────────────────


class SearchResultEx(SearchResult):
    """SearchResult + các trường UI cần. Tất cả optional nên frontend cũ không vỡ.

    `routes` cho biết mỗi model xếp ảnh này ở hạng mấy — dòng nào cả hai model
    cùng thấy thì đáng tin hơn hẳn. UI nên tô màu theo số model có mặt.

    `has_image` = ảnh đã tải về chưa. Index phủ đủ 868,524 frame nhưng ảnh tải
    riêng theo ZIP hàng chục GB, nên UI cần cờ này để vẽ placeholder.
    """
    video:     Optional[str]   = None
    frame_idx: Optional[int]   = None
    timestamp: Optional[str]   = None
    routes:    Optional[dict]  = None
    has_image: Optional[bool]  = None


class SearchResponseEx(SearchResponse):
    results: List[SearchResultEx]


class EnsembleSearchRequest(BaseModel):
    query:      str  = Field(..., min_length=1, description="Truy vấn văn bản")
    limit:      int  = Field(100, ge=1, le=500, description="Số dòng trả về (top-K)")
    top_m:      int  = Field(50,  ge=1, le=200,
                             description="Top-M mỗi model trước khi gộp (Alg.3, paper dùng 50)")
    use_rerank: bool = Field(True,
                             description="Bật Alg.2 rerank lân cận cho TỪNG model trước khi ensemble")

    class Config:
        json_schema_extra = {"example": {
            "query": "người đàn ông đội nón tai bèo đang phỏng vấn bên bờ biển",
            "limit": 100, "top_m": 50, "use_rerank": True,
        }}


class SingleSearchRequest(EnsembleSearchRequest):
    model: str = Field("clip", description="beit3 hoặc clip")

    class Config:
        json_schema_extra = {"example": {
            "query": "lễ trao kinh phí hỗ trợ trẻ em mồ côi",
            "model": "beit3", "limit": 100, "top_m": 50, "use_rerank": True,
        }}


class TemporalSearchRequest(BaseModel):
    query_start: str   = Field(..., description="Mô tả khoảnh khắc BẮT ĐẦU")
    query_end:   str   = Field(..., description="Mô tả khoảnh khắc KẾT THÚC")
    anchor_name: str   = Field(..., description="Tên file keyframe neo, lấy từ kết quả search")
    gap_c:       int   = Field(20, ge=1, le=300, description="Khoảng cách tối đa (giây) — paper: gap_C")
    max_frames:  int   = Field(20, ge=1, le=100, description="Số frame tối đa mỗi chiều — paper: 20")
    sim_thr:     float = Field(0.10, description="Dừng mở rộng khi điểm tụt dưới ngưỡng này")
    model:       str   = Field("clip", description="Model dùng để tính điểm: beit3 hoặc clip")

    class Config:
        json_schema_extra = {"example": {
            "query_start": "người đang đứng phát biểu trên sân khấu",
            "query_end":   "khán giả vỗ tay sau bài phát biểu",
            "anchor_name": "L21_V015-0042-003729.jpg",
            "gap_c": 20,
        }}


class TemporalCandidate(BaseModel):
    """1 frame ứng viên trái/phải — đủ data để UI cho người dùng click chọn
    thay thế, khớp Figure 4c paper: 'Users can review these suggestions and
    adjust them if necessary to refine the moment boundaries.'"""
    name:      str
    url:       str
    frame_idx: Optional[int] = None
    timestamp: Optional[str] = None
    score:     Optional[float] = None


class TemporalSearchResponse(BaseModel):
    video:           Optional[str] = None
    start_frame:     Optional[str] = None
    end_frame:       Optional[str] = None
    start_ts:        Optional[str] = None
    end_ts:          Optional[str] = None
    start_frame_idx: Optional[int] = None
    end_frame_idx:   Optional[int] = None
    combined_score:  Optional[float] = None
    start_url:       Optional[str] = None
    end_url:         Optional[str] = None
    n_left:          Optional[int] = None
    n_right:         Optional[int] = None
    # MỚI — Figure 4c "Boundary Selection": danh sách ứng viên để người dùng
    # tự điều chỉnh nếu cặp start/end đề xuất chưa đúng ý. Optional nên không
    # phá vỡ gì nếu preprocess.py chưa kịp cập nhật (mặc định None).
    left_candidates:  Optional[List[TemporalCandidate]] = None
    right_candidates: Optional[List[TemporalCandidate]] = None
    error:           Optional[str] = None


# ─────────────────────────────────────────────────────────────────────────────
#  App
# ─────────────────────────────────────────────────────────────────────────────

BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
IMAGES_DIR = os.environ.get("AIC_IMAGES_DIR", os.path.join(BASE_DIR, "static", "images"))

# Tạo trước, nếu không StaticFiles ném lỗi ngay lúc khởi động khi thư mục chưa có.
os.makedirs(IMAGES_DIR, exist_ok=True)


# ─────────────────────────────────────────────────────────────────────────────
#  Warm-up
#
#  Indexes, metadata and models add up to roughly 16 GB of disk reads. They are
#  otherwise lazy-loaded on the first request, so on a machine that is stopped
#  and started daily the first user of the day waits minutes with no feedback.
#
#  This runs on a background thread rather than inline in the lifespan hook so
#  uvicorn binds its port and answers /health immediately, letting the UI show
#  that the machine is up and warming. A request arriving early still works:
#  the search functions call the same idempotent loaders and simply wait.
# ─────────────────────────────────────────────────────────────────────────────

_warm: dict = {"state": "cold", "seconds": None, "error": None}


def _run_warmup() -> None:
    t0 = time.monotonic()
    _warm["state"] = "warming"
    try:
        preload()
        _warm["state"] = "ready"
    except Exception as exc:                  # noqa: BLE001 — surfaced on /health
        _warm["state"] = "failed"
        _warm["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        _warm["seconds"] = round(time.monotonic() - t0, 1)
        print(f"[warmup] {_warm['state']} after {_warm['seconds']}s"
              + (f" — {_warm['error']}" if _warm["error"] else ""))


@asynccontextmanager
async def lifespan(app: FastAPI):
    if os.environ.get("AIC_WARMUP", "1") != "0":
        threading.Thread(target=_run_warmup, name="warmup", daemon=True).start()
    else:
        _warm["state"] = "ready"
        _warm["seconds"] = 0.0
        print("[warmup] skipped (AIC_WARMUP=0)")
    yield


app = FastAPI(
    title="AI Challenge HCM 2026 – Video Moment Retrieval API",
    description="arXiv 2504.08384 · search → rerank (per-model) → ensemble → temporal",
    version=VERSION,
    lifespan=lifespan,
)

app.mount("/static/images", StaticFiles(directory=IMAGES_DIR), name="images")

# The frontend is served from a different origin than the API, so CORS is
# required. Leaving AIC_CORS_ORIGINS empty allows any origin, which is
# convenient locally; production pins it to the frontend origin.
#
# allow_credentials=False: auth uses a Bearer token in the header, not cookies.
# Credentials combined with allow_origins=["*"] is a pairing browsers reject.
_cors_origins = [o.strip() for o in os.environ.get("AIC_CORS_ORIGINS", "").split(",")
                 if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins or ["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _make_response(results: list[dict], query_type: str, t0: datetime) -> SearchResponseEx:
    rows = [SearchResultEx(**r) for r in results]
    return SearchResponseEx(
        total_results=len(rows),
        returned_results=len(rows),
        results=rows,
        query_type=query_type,
        processing_time=(datetime.now() - t0).total_seconds(),
        max_distance=max((r["distance"] for r in results), default=0.0),
    )


# ─────────────────────────────────────────────────────────────────────────────
#  Endpoints
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/ensemble-search", response_model=SearchResponseEx,
          summary="Alg.3 — search → rerank từng model → ensemble")
async def ensemble_search_endpoint(req: EnsembleSearchRequest):
    """Chuỗi đầy đủ theo thứ tự đã chốt.

        query ─┬─→ BEiT3 top-M ─→ rerank lân cận (BEiT3) ─┐
               │                                            ├─→ ensemble ─→ top-K
               └─→ CLIP  top-M ─→ rerank lân cận (CLIP)  ─┘

    Rerank chạy trong không gian RIÊNG của từng model — điểm lân cận phải tính
    bằng chính embedding của model đó mới có nghĩa. Sau đó Alg.3 chuẩn hoá
    s/S_max nên hai thang điểm khác nhau vẫn gộp được công bằng.
    """
    t0 = datetime.now()
    try:
        results = ensemble_search(req.query, top_k=req.limit, top_m=req.top_m,
                                  use_rerank=req.use_rerank)
        return _make_response(results, "ensemble", t0)
    except Exception as e:
        raise HTTPException(500, f"Ensemble search error: {e}")


@app.post("/single-search", response_model=SearchResponseEx,
          summary="Chạy một model duy nhất — phục vụ thí nghiệm Q4")
async def single_search_endpoint(req: SingleSearchRequest):
    """So model đơn với ensemble trên cùng bộ truy vấn.

    Q4 cần 6 lần chạy: beit3 đơn, clip đơn, ensemble — mỗi cái có/không rerank.
    Endpoint này lo 4 trường hợp đầu, /ensemble-search lo 2 cái còn lại.
    """
    if req.model not in MODEL_NAMES:
        raise HTTPException(400, f"model phải là một trong {list(MODEL_NAMES)}")
    t0 = datetime.now()
    try:
        results = single_model_search(req.query, req.model, top_k=req.limit,
                                      top_m=req.top_m, use_rerank=req.use_rerank)
        return _make_response(results, f"single:{req.model}", t0)
    except Exception as e:
        raise HTTPException(500, f"Single search error: {e}")


@app.post("/temporal-search", response_model=TemporalSearchResponse,
          summary="Alg.4 — cặp frame bắt đầu/kết thúc quanh keyframe neo")
async def temporal_search_endpoint(req: TemporalSearchRequest):
    """Mở rộng hai chiều từ keyframe neo: sang trái bằng query_start, sang phải
    bằng query_end. Dừng khi điểm tụt dưới sim_thr hoặc đủ max_frames. Chọn cặp
    có tổng điểm cao nhất mà khoảng cách thời gian không vượt gap_C giây.
    """
    if req.model not in MODEL_NAMES:
        raise HTTPException(400, f"model phải là một trong {list(MODEL_NAMES)}")
    try:
        result = temporal_search(
            query_start=req.query_start,
            query_end=req.query_end,
            anchor_name=req.anchor_name,
            gap_c=req.gap_c,
            max_frames=req.max_frames,
            sim_thr=req.sim_thr,
            model_name=req.model,
        )
        return TemporalSearchResponse(**result)
    except Exception as e:
        raise HTTPException(500, f"Temporal search error: {e}")


@app.get("/status", summary="Còn thiếu file gì")
def status():
    return {**system_status(), "warmup": _warm}


@app.get("/health")
def health():
    """Liveness, plus how far along the warm-up is.

    `ok` flips as soon as the process is running, which is what infrastructure
    health checks want. `warmup.state` (cold -> warming -> ready | failed) tells
    the UI whether to show a starting-up notice or accept queries. This is the
    cost of running the machine on demand, and it is what the frontend polls.
    """
    return {"ok": True, "version": VERSION, "commit": SHORT_COMMIT, "warmup": _warm}


@app.get("/")
def root():
    return {
        "name":    "AI Challenge HCM 2026 – Video Moment Retrieval API",
        "version": VERSION,
        "paper":   "arXiv:2504.08384",
        "pipeline": "search → rerank (per-model) → ensemble → temporal",
        "endpoints": ["/ensemble-search", "/single-search", "/temporal-search",
                      "/status", "/health", "/docs"],
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
