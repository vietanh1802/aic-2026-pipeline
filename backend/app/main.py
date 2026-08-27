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

  POST /ocr-search        Tìm bằng chữ Vintern OCR đọc được trên màn hình

Đã BỎ các endpoint cũ: /text-search, /text-no-agent-search, /faiss-search,
/combined-search, /filter-search. Chúng đọc temp.json với các trường
content/ocr/object/color/action của mùa trước — pipeline hiện tại không sinh ra
file đó, nên chúng luôn trả rỗng mà vẫn HTTP 200 (thất bại im lặng).

/ocr-search is BACK, but rewritten from scratch on app/ocr_search.py, reading
indexes/ocr_clean.json (360,531 keyframes, 179,728 of them carrying text)
rather than the old temp.json.

The OCR route runs ON ITS OWN and is not blended with the visual route. That is
deliberate: over the 25 preliminary queries (notebook 78), 13 of 25 answer
frames carry no text at all, while distinctive text puts the right video first
immediately — an RRF blend would smear out exactly that advantage. Blending
(OCR / ASR / caption / tag -> BM25 -> RRF) waits until Q5/Q6 are settled.
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
from app.db.connection import get_conn
from app.db.migrate import migrate
from app.routers import (
    answers as answers_router,
    auth as auth_router,
    board as board_router,
    export as export_router,
    packs as packs_router,
    rounds as rounds_router,
)
from app.version import SHORT_COMMIT, VERSION
from app import ocr_search as ocr_route
# Import the MODULE, not just its functions: _load_meta() rebinds _name2meta
# rather than mutating it, so `from ... import _name2meta` would hold the empty
# startup dict forever and every OCR result would lose video/timestamp.
from app import preprocess as _pp
from app.preprocess import (
    ensemble_search,
    single_model_search,
    temporal_search,
    trake_search,
    temporal_search_candidates,
    trake_search_candidates,
    temporal_search_text,
    trake_search_text,
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


class OcrSearchRequest(BaseModel):
    query: str  = Field(..., min_length=1,
                        description="Cụm chữ nhìn thấy trên màn hình")
    limit: int  = Field(100, ge=1, le=2000, description="Số dòng trả về")
    strip_diacritics: bool = Field(
        True,
        description="Bỏ dấu cả 2 phía trước khi so. Bật thì bắt được cả lỗi dấu "
                    "của OCR (HỂ THAO ~ THỂ THAO); tắt thì khớp chính xác hơn.")
    video: Optional[str] = Field(
        None, description='Bó hẹp trong 1 batch hoặc 1 video: "L25" hoặc "L25_V041"')

    class Config:
        json_schema_extra = {"example": {
            "query": "Quán ăn Chợ Lớn", "limit": 100, "strip_diacritics": True,
        }}


class OcrSearchResultEx(SearchResultEx):
    """An OCR hit — same shape as a visual-route hit, so the UI grid is reused
    unchanged; the extra fields only explain WHY it matched.

    `ocr_text` is the valuable one: the operator reads the line directly and
    decides on the spot whether it is what they want, without opening the image.
    """
    ocr_text:      Optional[str]  = None
    exact_phrase:  Optional[bool] = None
    matched_words: Optional[int]  = None
    total_words:   Optional[int]  = None


class OcrSearchResponse(SearchResponse):
    results: List[OcrSearchResultEx]
    # Three counts, not one. Notebook 78 measured: all_word_matches <= 4 puts
    # the right video first (6/6), >= 142 gets it right only 1/6 — so surface
    # all three and the operator knows at once whether 500 images are worth
    # paging through.
    phrase_matches:   int = 0
    all_word_matches: int = 0
    searched_frames:  int = 0


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


# ─── TRAKE — N sự kiện tuần tự, tổng quát hóa từ TemporalSearchRequest ────────
# Merge lại sau khi nhánh bạn cùng team tách trước lúc phần này được thêm.

class TrakeSearchRequest(BaseModel):
    queries:     List[str] = Field(..., min_length=2,
                                   description="Danh sách mô tả N sự kiện, ĐÚNG THỨ TỰ thời gian (E1, E2, ...)")
    anchor_name: str       = Field(..., description="Tên file keyframe neo, lấy từ kết quả search — xác định VIDEO cần tìm")
    gap_c:       int       = Field(60, ge=1, le=600,
                                   description="Khoảng cách tối đa (giây) giữa 2 event LIÊN TIẾP")
    model:       str       = Field("clip", description="Model dùng để tính điểm: beit3 hoặc clip")

    class Config:
        json_schema_extra = {"example": {
            "queries": [
                "Khoảnh khắc đầu tiên bột được bỏ vào tô măng tây",
                "Khoảnh khắc miếng măng tây đầu tiên tiếp xúc với dầu trong chảo",
                "Khoảnh khắc miếng măng tây đầu tiên rời khỏi chảo dầu",
                "Khoảnh khắc miếng măng tây cuối cùng rời chảo dầu và nằm hoàn toàn trên dĩa",
            ],
            "anchor_name": "L26_V194-0012-004707.jpg",
            "gap_c": 60,
        }}


class TrakeEvent(BaseModel):
    name:       str
    url:        str
    frame_idx:  Optional[int] = None
    timestamp:  Optional[str] = None
    score:      Optional[float] = None
    # Ứng viên khác cho ĐÚNG event này — cùng tinh thần Figure 4c, cho phép
    # người dùng đổi từng event riêng lẻ nếu DP chọn chưa đúng ý.
    candidates: Optional[List[TemporalCandidate]] = None


class TrakeSearchResponse(BaseModel):
    video:           Optional[str] = None
    events:          Optional[List[TrakeEvent]] = None
    combined_score:  Optional[float] = None
    error:           Optional[str] = None


# ─── Auto-discovery — không cần anchor_name thủ công ──────────────────────────
# Bổ sung THÊM bên cạnh /temporal-search và /trake-search (2 endpoint đó giữ
# nguyên, không đổi gì). Dùng khi muốn hệ thống tự tìm video ứng viên thay vì
# bắt người dùng bấm chọn 1 frame trước — xem preprocess.py
# _discover_candidate_videos() để biết cơ sở lý luận đầy đủ.

class TemporalSearchCandidatesRequest(BaseModel):
    query_start: str   = Field(..., description="Mô tả khoảnh khắc BẮT ĐẦU")
    query_end:   str   = Field(..., description="Mô tả khoảnh khắc KẾT THÚC")
    top_m:       int   = Field(50, ge=1, le=200, description="Top-M mỗi query lúc khám phá video ứng viên")
    top_videos:  int   = Field(5,  ge=1, le=20,  description="Số video ứng viên tối đa để thử temporal_search")
    gap_c:       int   = Field(20, ge=1, le=300)
    max_frames:  int   = Field(20, ge=1, le=100)
    sim_thr:     float = Field(0.10)
    model:       str   = Field("clip", description="beit3 hoặc clip")


class TrakeSearchCandidatesRequest(BaseModel):
    queries:    List[str] = Field(..., min_length=2, description="N mô tả sự kiện, đúng thứ tự")
    top_m:      int       = Field(50, ge=1, le=200)
    top_videos: int       = Field(5,  ge=1, le=20)
    gap_c:      int       = Field(60, ge=1, le=600)
    min_score:  float     = Field(0.10, description="Ngưỡng 'đủ tốt' lúc đếm tần suất khám phá video")
    model:      str       = Field("clip", description="beit3 hoặc clip")


class TemporalCandidateResult(TemporalSearchResponse):
    # discovery_score = TẦN SUẤT (bao nhiêu trong số 2 query có match đạt
    # ngưỡng ở video này, 0-2) — không phải cosine score. discovery_score_sum
    # là tổng điểm các query đã khớp, dùng tie-break khi tần suất bằng nhau.
    # Khác combined_score (điểm thật sau khi chạy temporal_search() đầy đủ ở
    # Bước 2) — giữ cả 2 để soi lỗi nếu 1 video tần suất cao nhưng
    # combined_score sau đó lại thấp.
    discovery_score:     Optional[int]   = None
    discovery_score_sum: Optional[float] = None


class TrakeCandidateResult(TrakeSearchResponse):
    discovery_score:     Optional[int]   = None
    discovery_score_sum: Optional[float] = None


# ─── Bản "1 ô nhập" — khung nhập giữ nguyên 1 field, tách bằng dấu "." ────────
# Frontend gửi thẳng chuỗi thô người dùng gõ, KHÔNG tự tách ở FE — tách ở
# preprocess._split_query_text() (dấu "." + khoảng trắng theo sau, an toàn
# với số thập phân như "3.5"). Bổ sung bên cạnh 2 endpoint *-candidates ở
# trên (giữ nguyên, nhận query_start/query_end hoặc queries[] đã tách sẵn).

class TemporalSearchTextRequest(BaseModel):
    query:      str = Field(..., min_length=1,
                            description="1 chuỗi, 2 đoạn cách nhau bằng dấu '.' — vd 'người bước lên sân khấu. khán giả vỗ tay'")
    top_m:      int   = Field(50, ge=1, le=200)
    top_videos: int   = Field(5,  ge=1, le=20)
    gap_c:      int   = Field(20, ge=1, le=300)
    max_frames: int   = Field(20, ge=1, le=100)
    sim_thr:    float = Field(0.10)
    model:      str   = Field("clip", description="beit3 hoặc clip")


class TrakeSearchTextRequest(BaseModel):
    query:      str   = Field(..., min_length=1,
                              description="1 chuỗi, N đoạn (N>=2) cách nhau bằng dấu '.'")
    top_m:      int   = Field(50, ge=1, le=200)
    top_videos: int   = Field(5,  ge=1, le=20)
    gap_c:      int   = Field(60, ge=1, le=600)
    min_score:  float = Field(0.10)
    model:      str   = Field("clip", description="beit3 hoặc clip")


class TemporalSearchTextResponse(BaseModel):
    results: Optional[List[TemporalCandidateResult]] = None
    error:   Optional[str] = None


class TrakeSearchTextResponse(BaseModel):
    results: Optional[List[TrakeCandidateResult]] = None
    error:   Optional[str] = None


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
        # After preload(): 1.3 s against several minutes for indexes and models.
        # Missing OCR files only print a warning — they must never flip the
        # whole warm-up to failed and take the visual route down with them.
        ocr_route.preload()
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
    # Bảng cộng tác nằm cùng process với search, migrate lúc khởi động để việc
    # triển khai chỉ còn một artefact. Chạy trước warm-up vì nó tính bằng mili
    # giây, còn warm-up tính bằng phút.
    _conn = get_conn()
    try:
        migrate(_conn)
    finally:
        _conn.close()

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

# Tầng cộng tác. Search giữ nguyên các endpoint gốc ở gốc đường dẫn;
# mọi thứ mới nằm dưới /api.
app.include_router(auth_router.router)
app.include_router(packs_router.router)
app.include_router(board_router.router)
app.include_router(answers_router.router)
app.include_router(export_router.router)
app.include_router(rounds_router.router)

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


def _frame_idx_from_name(name: str) -> Optional[int]:
    """Read the frame number out of a filename: "L24_V010-0031-8228.jpg" -> 8228.

    A fallback for the OCR route. ocr_clean.json covers all 360,531 keyframes of
    L21-L30, while keyframe_metadata.json may be regenerated from a different
    set of ZIPs — when they diverge, frame_idx=None breaks the UI's "open the
    video at this second" button, over a number the filename already carries.
    """
    try:
        return int(name.rsplit("-", 1)[1].split(".")[0])
    except (IndexError, ValueError):
        return None


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
#fix async def
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/ensemble-search", response_model=SearchResponseEx,
          summary="Alg.3 — search → rerank từng model → ensemble")
def ensemble_search_endpoint(req: EnsembleSearchRequest):
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
def single_search_endpoint(req: SingleSearchRequest):
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
def temporal_search_endpoint(req: TemporalSearchRequest):
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


@app.post("/trake-search", response_model=TrakeSearchResponse,
          summary="TRAKE — N sự kiện tuần tự trong cùng 1 video (tổng quát hóa Alg.4)")
def trake_search_endpoint(req: TrakeSearchRequest):
    """Chấm điểm ĐỘC LẬP từng query lên toàn bộ frame video của anchor, rồi
    dùng DP chọn 1 frame/event sao cho frame_idx tăng dần đúng thứ tự VÀ tổng
    điểm N frame lớn nhất. Độ phức tạp O(N × F²) — xem docstring
    preprocess.trake_search() để biết lý do không dùng brute-force O(F^N).
    """
    if req.model not in MODEL_NAMES:
        raise HTTPException(400, f"model phải là một trong {list(MODEL_NAMES)}")
    try:
        result = trake_search(
            queries=req.queries,
            anchor_name=req.anchor_name,
            gap_c=req.gap_c,
            model_name=req.model,
        )
        return TrakeSearchResponse(**result)
    except Exception as e:
        raise HTTPException(500, f"TRAKE search error: {e}")


@app.post("/temporal-search-candidates", response_model=List[TemporalCandidateResult],
          summary="Tự động khám phá video ứng viên cho Temporal Search — không cần anchor_name")
def temporal_search_candidates_endpoint(req: TemporalSearchCandidatesRequest):
    """Chạy song song 2 lần _search_one() (query_start, query_end), group theo
    video giữ điểm cao nhất, rồi gọi temporal_search() ĐÃ CÓ (không đổi) cho
    mỗi video ứng viên. Trả về LIST kết quả, sort theo combined_score.

    Bổ sung bên cạnh /temporal-search (vẫn giữ nguyên, cần anchor_name thủ
    công) — dùng endpoint này khi muốn hệ thống tự đề xuất thay vì bắt người
    dùng bấm chọn 1 frame trước.
    """
    if req.model not in MODEL_NAMES:
        raise HTTPException(400, f"model phải là một trong {list(MODEL_NAMES)}")
    try:
        results = temporal_search_candidates(
            query_start=req.query_start, query_end=req.query_end,
            top_m=req.top_m, top_videos=req.top_videos,
            gap_c=req.gap_c, max_frames=req.max_frames, sim_thr=req.sim_thr,
            model_name=req.model,
        )
        return [TemporalCandidateResult(**r) for r in results]
    except Exception as e:
        raise HTTPException(500, f"Temporal search candidates error: {e}")


@app.post("/trake-search-candidates", response_model=List[TrakeCandidateResult],
          summary="Tự động khám phá video ứng viên cho TRAKE — không cần anchor_name")
def trake_search_candidates_endpoint(req: TrakeSearchCandidatesRequest):
    """Tương tự /temporal-search-candidates nhưng cho N query (TRAKE). Gọi
    trake_search() ĐÃ CÓ (không đổi) cho mỗi video ứng viên.
    """
    if req.model not in MODEL_NAMES:
        raise HTTPException(400, f"model phải là một trong {list(MODEL_NAMES)}")
    try:
        results = trake_search_candidates(
            queries=req.queries, top_m=req.top_m, top_videos=req.top_videos,
            gap_c=req.gap_c, min_score=req.min_score, model_name=req.model,
        )
        return [TrakeCandidateResult(**r) for r in results]
    except Exception as e:
        raise HTTPException(500, f"TRAKE search candidates error: {e}")


@app.post("/temporal-search-text", response_model=TemporalSearchTextResponse,
          summary="Temporal Search — 1 ô nhập duy nhất, tách bằng dấu '.'")
def temporal_search_text_endpoint(req: TemporalSearchTextRequest):
    """Frontend gửi thẳng chuỗi thô (khung nhập giữ nguyên 1 field) — tách
    thành query_start/query_end ở backend rồi gọi
    temporal_search_candidates() ĐÃ CÓ (không đổi).
    """
    if req.model not in MODEL_NAMES:
        raise HTTPException(400, f"model phải là một trong {list(MODEL_NAMES)}")
    try:
        result = temporal_search_text(
            req.query, top_m=req.top_m, top_videos=req.top_videos,
            gap_c=req.gap_c, max_frames=req.max_frames, sim_thr=req.sim_thr,
            model_name=req.model,
        )
        return TemporalSearchTextResponse(**result)
    except Exception as e:
        raise HTTPException(500, f"Temporal search text error: {e}")


@app.post("/trake-search-text", response_model=TrakeSearchTextResponse,
          summary="TRAKE — 1 ô nhập duy nhất, tách bằng dấu '.'")
def trake_search_text_endpoint(req: TrakeSearchTextRequest):
    """Tương tự /temporal-search-text nhưng cho N đoạn (TRAKE). Gọi
    trake_search_candidates() ĐÃ CÓ (không đổi).
    """
    if req.model not in MODEL_NAMES:
        raise HTTPException(400, f"model phải là một trong {list(MODEL_NAMES)}")
    try:
        result = trake_search_text(
            req.query, top_m=req.top_m, top_videos=req.top_videos,
            gap_c=req.gap_c, min_score=req.min_score, model_name=req.model,
        )
        return TrakeSearchTextResponse(**result)
    except Exception as e:
        raise HTTPException(500, f"TRAKE search text error: {e}")


@app.post("/ocr-search", response_model=OcrSearchResponse,
          summary="Tìm bằng chữ Vintern OCR đọc được trên màn hình")
def ocr_search_endpoint(req: OcrSearchRequest):
    """Pure lexical route: give it a phrase, get the frames containing it.

    No model takes part in scoring. Order is decided entirely by what was
    typed — whole phrase first, then word count, then shorter text first.

    Deliberately NOT blended with /ensemble-search. See the app/ocr_search.py
    docstring for why (13 of the 25 preliminary answer frames carry no text).
    """
    started = datetime.now()
    try:
        found = ocr_route.search(req.query, limit=req.limit,
                                 strip_diacritics=req.strip_diacritics,
                                 video=req.video)
    except FileNotFoundError as e:
        raise HTTPException(503, str(e))
    except Exception as e:
        raise HTTPException(500, f"OCR search error: {e}")

    # Fill in video/frame_idx/timestamp/url to match the visual route's shape,
    # so the existing UI grid renders these without a new component.
    _pp._load_meta()
    rows = []
    for hit in found["results"]:
        name = hit["name"]
        meta = _pp._name2meta.get(name, {})
        rows.append(OcrSearchResultEx(
            frame=name, name=name, url=_pp._image_url(name),
            # distance: the UI scales its score bar against max_distance. Whole
            # phrases get +1000, so they separate into their own top band.
            distance=hit["score"],
            video=meta.get("video") or name.split("-")[0],
            frame_idx=meta.get("frame_idx", _frame_idx_from_name(name)),
            timestamp=meta.get("timestamp"),
            has_image=_pp._has_image(name),
            ocr_text=hit["ocr_text"],
            exact_phrase=hit["exact_phrase"],
            matched_words=hit["matched_words"],
            total_words=hit["total_words"],
        ))

    return OcrSearchResponse(
        total_results=found["all_word_matches"],
        returned_results=len(rows),
        results=rows,
        query_type="ocr" + ("" if req.strip_diacritics else ":with_marks"),
        processing_time=(datetime.now() - started).total_seconds(),
        max_distance=max((r.distance for r in rows), default=0.0),
        phrase_matches=found["phrase_matches"],
        all_word_matches=found["all_word_matches"],
        searched_frames=found["searched_frames"],
    )


@app.get("/ocr-text/{name}", summary="Chữ OCR của đúng 1 keyframe")
def ocr_text_endpoint(name: str):
    """Lets the UI show the text on whichever frame the user is looking at,
    including frames that came from the visual route rather than this one."""
    try:
        return {"name": name, "ocr_text": ocr_route.get_text(name)}
    except FileNotFoundError as e:
        raise HTTPException(503, str(e))


@app.get("/status", summary="Còn thiếu file gì")
def status():
    return {**system_status(), "warmup": _warm, "ocr": ocr_route.status()}


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
                      "/trake-search", "/temporal-search-candidates",
                      "/trake-search-candidates", "/temporal-search-text",
                      "/trake-search-text", "/ocr-search", "/ocr-text/{name}",
                      "/status", "/health", "/docs"],
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)