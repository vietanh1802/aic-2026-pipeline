# -*- coding: utf-8 -*-
"""
preprocess.py – Tái hiện pipeline từ arXiv 2504.08384
======================================================
Thuật toán:
  Alg.2 – Neighbor Score Aggregation (Reranking)  — chạy RIÊNG cho từng model
  Alg.3 – Ensemble Search (BEiT3-Large + CLIP ViT-bigG-14)
  Alg.4 – Bidirectional Temporal Frame Pair Selection

THỨ TỰ (đã chốt, khác bản trước):

    query ─┬─→ BEiT3 search top-M ─→ rerank lân cận (BEiT3) ─┐
           │                                                  ├─→ ENSEMBLE ─→ top-K
           └─→ CLIP  search top-M ─→ rerank lân cận (CLIP)  ─┘

  Bản trước làm ngược: ensemble trước rồi rerank danh sách đã gộp. Paper tự mâu
  thuẫn về thứ tự (Abstract xếp ensemble trước, Section 3.1 xếp reranking trước),
  nên đây là lựa chọn của nhóm: rerank trong không gian RIÊNG của từng model,
  vì điểm lân cận phải tính bằng chính embedding của model đó mới có nghĩa.

  Hệ quả kỹ thuật: sau rerank, điểm là TỔNG dot-product của các lân cận — thang
  đo hoàn toàn khác cosine gốc. Bước s/S_max của Alg.3 vẫn xử lý được, vì nó
  chuẩn hoá theo max của chính từng model.

Model — verify từ paper gốc:
  Fine-grained   (ref [51]): BEiT3-Large, beit3_large_patch16_384_coco_retrieval.pth
  Coarse-grained (ref [41]): OpenCLIP ViT-bigG-14 (laion2b_s39b_b160k)

CHẾ ĐỘ DEMO: khi chưa có file index/metadata, module tự sinh dữ liệu giả để
frontend chạy được. Xem phần DEMO_MODE ở cuối file.
"""

import os, json, sys, zlib, subprocess as _sp
from typing import Optional

import numpy as np
import faiss
import torch

# ─────────────────────────────────────────────────────────────────────────────
#  Paths — khớp cấu trúc Drive AIC2026/ đã chốt
#
#    AIC2026/
#    ├── indexes/
#    │   ├── beit3.index      beit3_mapping.json
#    │   ├── clip.index       clip_mapping.json
#    │   └── keyframe_metadata.json
#    └── zips/  progress.json
#
#  Đặt AIC_INDEX_DIR để trỏ sang chỗ khác (vd thư mục Drive đã sync về máy).
#  Mặc định: backend/app/indexes/
# ─────────────────────────────────────────────────────────────────────────────
BASE_DIR  = os.path.dirname(os.path.abspath(__file__))
INDEX_DIR = os.environ.get("AIC_INDEX_DIR", os.path.join(BASE_DIR, "indexes"))

BEIT3_IDX_PATH = os.path.join(INDEX_DIR, "beit3.index")
CLIP_IDX_PATH  = os.path.join(INDEX_DIR, "clip.index")
BEIT3_MAP_PATH = os.path.join(INDEX_DIR, "beit3_mapping.json")
CLIP_MAP_PATH  = os.path.join(INDEX_DIR, "clip_mapping.json")
META_PATH      = os.path.join(INDEX_DIR, "keyframe_metadata.json")

# Mapping json sinh từ notebook có URL tuyệt đối localhost:8000 nhúng cứng.
# Ta chỉ lấy TÊN FILE rồi ghép lại theo biến này → đổi chỗ lưu ảnh (Backblaze,
# CDN) chỉ cần đổi env, KHÔNG phải index lại 873 video.
IMAGE_BASE_URL = os.environ.get("AIC_IMAGE_BASE_URL",
                                "http://localhost:8000/static/images")

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"

# ─── Model config ────────────────────────────────────────────────────────────
BEIT3_CKPT_URL   = "https://github.com/addf400/files/releases/download/beit3/beit3_large_patch16_384_coco_retrieval.pth"
BEIT3_SPM_URL    = "https://github.com/addf400/files/releases/download/beit3/beit3.spm"
BEIT3_MODEL_NAME = "beit3_large_patch16_384_retrieval"
BEIT3_REPO_DIR   = os.path.join(BASE_DIR, "unilm_beit3")
CLIP_MODEL_NAME  = "ViT-bigG-14"
CLIP_PRETRAINED  = "laion2b_s39b_b160k"

# Alg.3 — trọng số ensemble. Tổng chuẩn hoá về 1 lúc chạy (pseudocode dòng 2).
ENSEMBLE_WEIGHTS = {"beit3": 0.5, "clip": 0.5}

MODEL_NAMES = ("beit3", "clip")

# ─────────────────────────────────────────────────────────────────────────────
#  Lazy globals — chỉ nạp khi có request đầu tiên, để server khởi động nhanh
# ─────────────────────────────────────────────────────────────────────────────
_beit3_model = _beit3_tokenizer = None
_clip_model  = _clip_proc = _clip_tokenizer = None
_beit3_index = _clip_index = None
_beit3_map   = _clip_map   = None

_meta: list[dict] = []
_meta_loaded  = False
_name2meta:   dict[str, dict] = {}
_clipid2meta: dict[int, dict] = {}
_video_frames: dict[str, list[dict]] = {}   # video → keyframe sắp theo frame_idx


# ─────────────────────────────────────────────────────────────────────────────
#  Loaders
# ─────────────────────────────────────────────────────────────────────────────

def _load_beit3():
    """Nạp BEiT3-Large retrieval (ref [51], nhánh fine-grained).

    Backend cần model THẬT chứ không chỉ FAISS index: embedding ảnh đã tính sẵn
    lúc index, nhưng embedding TEXT phải tính mới cho mỗi truy vấn người dùng gõ.

    Các bước giống hệt notebook: clone microsoft/unilm (sparse, chỉ beit3/), vá
    torch._six (module đã bị xoá khỏi torch hiện đại), tải checkpoint 1.29GB +
    tokenizer nếu chưa có, dựng model qua timm registry, nạp state dict.
    """
    global _beit3_model, _beit3_tokenizer
    if _beit3_model is not None:
        return

    beit3_src = os.path.join(BEIT3_REPO_DIR, "beit3")
    if not os.path.exists(beit3_src):
        print("[preprocess] Cloning microsoft/unilm (sparse, beit3/ only)...")
        _sp.run(["git", "clone", "--depth", "1", "--filter=blob:none", "--sparse",
                 "https://github.com/microsoft/unilm.git", BEIT3_REPO_DIR],
                check=True, capture_output=True)
        _sp.run(["git", "-C", BEIT3_REPO_DIR, "sparse-checkout", "set", "beit3"],
                check=True, capture_output=True)

    _utils_py = os.path.join(beit3_src, "utils.py")
    with open(_utils_py, encoding="utf-8") as f:
        _content = f.read()
    if "from torch._six import inf" in _content:
        _content = _content.replace(
            "from torch._six import inf",
            "inf = float('inf')  # torch._six removed in modern torch — standard patch")
        with open(_utils_py, "w", encoding="utf-8") as f:
            f.write(_content)
        print("[preprocess] Patched torch._six trong utils.py")

    if beit3_src not in sys.path:
        sys.path.insert(0, beit3_src)

    os.makedirs(INDEX_DIR, exist_ok=True)
    ckpt_path = os.path.join(INDEX_DIR, "beit3_large_patch16_384_coco_retrieval.pth")
    spm_path  = os.path.join(INDEX_DIR, "beit3.spm")
    if not os.path.exists(ckpt_path):
        print("[preprocess] Downloading BEiT3 checkpoint (1.29GB)...")
        _sp.run(["curl", "-sL", "-o", ckpt_path, BEIT3_CKPT_URL], check=True)
    if not os.path.exists(spm_path):
        print("[preprocess] Downloading BEiT3 tokenizer...")
        _sp.run(["curl", "-sL", "-o", spm_path, BEIT3_SPM_URL], check=True)

    from timm.models import create_model
    import modeling_finetune  # noqa: F401 — kích hoạt @register_model
    from transformers import XLMRobertaTokenizer

    print(f"[preprocess] Loading {BEIT3_MODEL_NAME}...")
    model = create_model(BEIT3_MODEL_NAME, pretrained=False)
    ckpt  = torch.load(ckpt_path, map_location="cpu")
    sd    = ckpt["model"] if "model" in ckpt else ckpt
    missing, unexpected = model.load_state_dict(sd, strict=False)
    del ckpt, sd
    model.eval().to(DEVICE)

    _beit3_model     = model
    _beit3_tokenizer = XLMRobertaTokenizer(spm_path)
    print(f"[preprocess] BEiT3-Large loaded on {DEVICE} "
          f"(missing={len(missing)}, unexpected={len(unexpected)})")


def _load_clip():
    """Nạp OpenCLIP ViT-bigG-14 (ref [41], nhánh coarse-grained)."""
    global _clip_model, _clip_proc, _clip_tokenizer
    if _clip_model is None:
        import open_clip
        _clip_model, _, _clip_proc = open_clip.create_model_and_transforms(
            CLIP_MODEL_NAME, pretrained=CLIP_PRETRAINED, device=DEVICE)
        _clip_model.eval()
        _clip_tokenizer = open_clip.get_tokenizer(CLIP_MODEL_NAME)
        print(f"[preprocess] CLIP {CLIP_MODEL_NAME} loaded on {DEVICE}")


def _load_indexes():
    global _beit3_index, _clip_index, _beit3_map, _clip_map
    if _beit3_index is None and os.path.exists(BEIT3_IDX_PATH):
        _beit3_index = faiss.read_index(BEIT3_IDX_PATH)
        if os.path.exists(BEIT3_MAP_PATH):
            with open(BEIT3_MAP_PATH, encoding="utf-8") as f:
                _beit3_map = json.load(f)
        print(f"[preprocess] BEiT3 FAISS: {_beit3_index.ntotal} vectors")
    if _clip_index is None and os.path.exists(CLIP_IDX_PATH):
        _clip_index = faiss.read_index(CLIP_IDX_PATH)
        if os.path.exists(CLIP_MAP_PATH):
            with open(CLIP_MAP_PATH, encoding="utf-8") as f:
                _clip_map = json.load(f)
        print(f"[preprocess] CLIP FAISS: {_clip_index.ntotal} vectors")


def _load_meta():
    """Nạp keyframe_metadata.json và dựng sẵn 3 bảng tra dùng nhiều lần."""
    global _meta, _meta_loaded, _name2meta, _clipid2meta, _video_frames
    if _meta_loaded or not os.path.exists(META_PATH):
        return
    with open(META_PATH, encoding="utf-8") as f:
        _meta = json.load(f)
    _meta_loaded = True

    _name2meta   = {m["name"]: m for m in _meta}
    _clipid2meta = {int(m["faiss_id_clip"]): m
                    for m in _meta if m.get("faiss_id_clip", -1) >= 0}

    _video_frames = {}
    for m in _meta:
        _video_frames.setdefault(m.get("video", "?"), []).append(m)
    for v in _video_frames:
        _video_frames[v].sort(key=lambda m: m.get("frame_idx", 0))

    print(f"[preprocess] Metadata: {len(_meta)} keyframes · {len(_video_frames)} videos")


def _model_parts(model_name: str):
    """Trả (index, mapping, hàm encode text, tên trường faiss_id) của 1 model."""
    if model_name == "beit3":
        return _beit3_index, _beit3_map, encode_text_beit3, "faiss_id_beit3"
    return _clip_index, _clip_map, encode_text_clip, "faiss_id_clip"


def _image_url(name: str) -> str:
    return f"{IMAGE_BASE_URL.rstrip('/')}/{name}"


# ─────────────────────────────────────────────────────────────────────────────
#  Text encoding
# ─────────────────────────────────────────────────────────────────────────────

@torch.no_grad()
def encode_text_beit3(text: str) -> np.ndarray:
    """BEiT3-Large → (1, 1024) float32, đã L2-normalize sẵn trong model.

    API verify từ BEiT3ForRetrieval.forward() (modeling_finetune.py):
      forward(text_description=ids, padding_mask=..., only_infer=True)
      → (None, language_cls), language_cls đã qua F.normalize().

    padding_mask=None an toàn cho encode 1 câu (không batch nhiều câu khác độ
    dài nên không cần padding).
    """
    _load_beit3()
    tokens = _beit3_tokenizer(text, return_tensors="pt")["input_ids"].to(DEVICE)
    _, language_cls = _beit3_model(text_description=tokens, padding_mask=None,
                                   only_infer=True)
    return language_cls.cpu().numpy().astype("float32")


@torch.no_grad()
def encode_text_clip(text: str) -> np.ndarray:
    """OpenCLIP ViT-bigG-14 → (1, 1280) float32 L2-normalized."""
    _load_clip()
    tokens = _clip_tokenizer([text]).to(DEVICE)
    feats  = _clip_model.encode_text(tokens)
    feats  = feats / feats.norm(dim=-1, keepdim=True)
    return feats.cpu().numpy().astype("float32")


# ─────────────────────────────────────────────────────────────────────────────
#  Bước 1 — tìm thô trên MỘT model
# ─────────────────────────────────────────────────────────────────────────────

def _search_one(model_name: str, query: str, top_m: int) -> list[dict]:
    index, mapping, encode_fn, _ = _model_parts(model_name)
    if index is None:
        return []

    q_emb = encode_fn(query)
    M     = min(top_m, index.ntotal)
    D, I  = index.search(q_emb, M)

    hits = []
    for fid, score in zip(I[0], D[0]):
        if fid < 0:
            continue
        url  = (mapping or {}).get(str(int(fid)), "")
        name = os.path.basename(url) if url else ""
        if not name:
            continue
        meta = _name2meta.get(name, {})
        hits.append({
            "name":      name,
            "faiss_id":  int(fid),
            "score":     float(score),   # bị rerank ghi đè
            "raw_score": float(score),   # giữ cosine gốc để soi lỗi
            "video":     meta.get("video", name.split("-")[0]),
            "frame_idx": meta.get("frame_idx"),
            "timestamp": meta.get("timestamp_str", ""),
        })
    return hits


# ─────────────────────────────────────────────────────────────────────────────
#  Bước 2 — Algorithm 2: Neighbor Score Aggregation, RIÊNG từng model
#
#  Pseudocode (Sec 3.3):
#    1: Initialize dictionary aggregated_score A
#    2: for each idx in I do
#    3:     key ← Convert idx to integer
#    4:     neighbors ← GetNeighbors(key)
#    5:     total_score ← 0
#    6:     for each neighbor N in neighbors do
#    7:          score ← ComputeScore(N, Q)
#    8:          if score != None then total_score += score
#    9:     end for
#   10:    UpdateScores(A, key, total_score)
#   11: end for
#   12: sorted_scores ← Sort(A, descending)
#
#  Hai điểm bám sát paper:
#   · total_score CHỈ cộng điểm các lân cận — KHÔNG cộng điểm gốc của chính nó.
#   · ComputeScore dùng index.reconstruct(N) → dot product: chính xác tuyệt đối,
#     không xấp xỉ, không phụ thuộc phạm vi của một lần search rộng.
# ─────────────────────────────────────────────────────────────────────────────

def _neighbor_faiss_ids(meta: dict, model_name: str) -> list[int]:
    """Lấy faiss_id các lân cận, quy về không gian id của model đang xét.

    keyframe_metadata.json chỉ lưu `neighbors_clip` (faiss_id của CLIP). Với
    BEiT3 phải đổi hệ: clip_id → bản ghi metadata → faiss_id_beit3.

    Nếu metadata không có neighbors_clip (notebook bản cũ), tự suy lân cận từ
    thứ tự thời gian trong cùng video, cửa sổ ±2 keyframe. Không có bước dự
    phòng này thì rerank im lặng trở thành không-làm-gì.
    """
    id_field = "faiss_id_beit3" if model_name == "beit3" else "faiss_id_clip"

    raw = meta.get("neighbors_clip") or []
    if raw:
        if model_name == "clip":
            return [int(i) for i in raw if int(i) >= 0]
        out = []
        for cid in raw:
            nb = _clipid2meta.get(int(cid))
            if nb and nb.get(id_field, -1) >= 0:
                out.append(int(nb[id_field]))
        return out

    frames = _video_frames.get(meta.get("video", ""), [])
    if not frames:
        return []
    try:
        pos = next(i for i, m in enumerate(frames) if m["name"] == meta["name"])
    except StopIteration:
        return []
    lo, hi = max(0, pos - 2), min(len(frames), pos + 3)
    return [int(frames[i][id_field]) for i in range(lo, hi)
            if frames[i].get(id_field, -1) >= 0]


def rerank_one_model(hits: list[dict], query: str, model_name: str) -> list[dict]:
    """Alg.2 áp cho danh sách kết quả của MỘT model.

    Điểm mới thay hẳn điểm cũ: score = Σ dot(q, vector từng lân cận).
    Thang đo khác cosine gốc — chấp nhận được vì Alg.3 chuẩn hoá theo S_max.
    """
    _load_meta()
    index, _, encode_fn, _ = _model_parts(model_name)
    if index is None or not hits or not _meta:
        return hits

    q_emb = encode_fn(query).ravel()

    def compute_score(nid: int):
        """ComputeScore(N, Q). Trả None nếu không dựng lại được vector — đúng
        nghĩa 'score != None' của paper: không xác định được, chứ không phải 0."""
        try:
            vec = index.reconstruct(int(nid)).astype("float32").ravel()
            return float(np.dot(q_emb, vec))
        except Exception:
            return None

    for h in hits:
        meta = _name2meta.get(h["name"])
        if not meta:
            h["score"], h["n_neighbors"] = 0.0, 0
            continue
        total, used = 0.0, 0
        for nid in _neighbor_faiss_ids(meta, model_name):
            s = compute_score(nid)
            if s is not None:
                total += s
                used  += 1
        h["score"], h["n_neighbors"] = total, used

    hits.sort(key=lambda h: -h["score"])
    return hits


# ─────────────────────────────────────────────────────────────────────────────
#  Bước 3 — Algorithm 3: Ensemble Search
#
#  Pseudocode (Sec 3.4):
#    1: Initialize score_dict as empty dictionary
#    2: Normalize weights: Σwi = 1 for selected models
#    3: for all (model_name, w, use_flag) ∈ model_configs do
#    4:     if use_flag then
#    5:          Load model and processor
#    6:          e ← EncodeText(model_name, query)
#    7:          I, S ← Search(model_name_idx, e, M = 50)
#    8:          Smax ← max(S)
#    9:          for all (i, s) ∈ (I, S) do score_dict[i] += (s/Smax) × w
#   10:     end if
#   11: end for
#   12: ranked_results ← Sort(score_dict, descending)
#
#  Dòng 5-7 đã tách ra _search_one, và có thêm rerank chèn vào giữa. Hàm này
#  chỉ còn lo phần gộp — dòng 8..12.
# ─────────────────────────────────────────────────────────────────────────────

def _merge_ensemble(per_model: dict[str, list[dict]], top_k: int) -> list[dict]:
    active = [n for n, hits in per_model.items() if hits]
    if not active:
        return []

    raw    = [ENSEMBLE_WEIGHTS.get(n, 0.5) for n in active]
    tot    = sum(raw) or 1.0
    norm_w = {n: w / tot for n, w in zip(active, raw)}      # Σwi = 1

    agg:    dict[str, float] = {}
    detail: dict[str, dict]  = {}

    for name in active:
        hits  = per_model[name]
        s_max = max(h["score"] for h in hits) or 1.0
        if s_max <= 0:
            s_max = 1.0
        w = norm_w[name]
        for rank, h in enumerate(hits, 1):
            key = h["name"]
            agg[key] = agg.get(key, 0.0) + (h["score"] / s_max) * w
            d = detail.setdefault(key, {"_ref": h, "routes": {}})
            d["routes"][name] = {"rank": rank, "score": round(h["raw_score"], 4)}

    ordered = sorted(agg.items(), key=lambda kv: -kv[1])[:top_k]

    results = []
    for key, score in ordered:
        ref = detail[key]["_ref"]
        results.append({
            "frame":     key,
            "name":      key,
            "url":       _image_url(key),
            "distance":  round(score * 100, 2),      # scale % cho UI
            "video":     ref.get("video"),
            "frame_idx": ref.get("frame_idx"),
            "timestamp": ref.get("timestamp", ""),
            "routes":    detail[key]["routes"],
        })
    return results


# ─────────────────────────────────────────────────────────────────────────────
#  API chính
# ─────────────────────────────────────────────────────────────────────────────

def ensemble_search(query: str, top_k: int = 100, top_m: int = 50,
                    use_rerank: bool = True,
                    models: Optional[list[str]] = None) -> list[dict]:
    """Chuỗi đầy đủ: search từng model → rerank từng model → ensemble.

    models=None dùng mọi model có index. Truyền ["beit3"] hoặc ["clip"] để chạy
    một model duy nhất — phục vụ Q4 (so model đơn với ensemble).
    """
    _load_indexes()
    _load_meta()

    if DEMO_MODE:
        return _demo_results(query, top_k, models)

    per_model: dict[str, list[dict]] = {}
    for name in (models or list(MODEL_NAMES)):
        if name not in MODEL_NAMES:
            continue
        hits = _search_one(name, query, top_m)
        if not hits:
            continue
        if use_rerank:
            hits = rerank_one_model(hits, query, name)
        per_model[name] = hits

    return _merge_ensemble(per_model, top_k)


def single_model_search(query: str, model_name: str, top_k: int = 100,
                        top_m: int = 50, use_rerank: bool = True) -> list[dict]:
    """Chạy đúng một model. Dùng cho Q4: beit3 đơn / clip đơn / ensemble."""
    return ensemble_search(query, top_k=top_k, top_m=top_m,
                           use_rerank=use_rerank, models=[model_name])


# ─────────────────────────────────────────────────────────────────────────────
#  Algorithm 4 – Bidirectional Temporal Frame Pair Selection (Sec 3.5)
#
#  "we conduct a bidirectional search, extending to the left of the input frame
#   index until either 20 relevant frames are identified or the similarity score
#   falls below an acceptable threshold... determine the optimal frame pair by
#   selecting two frames that exhibit the highest similarity scores with the
#   respective queries while ensuring that their temporal distance does not
#   exceed a predefined constraint gap_C"
# ─────────────────────────────────────────────────────────────────────────────

def temporal_search(query_start: str, query_end: str, anchor_name: str,
                    gap_c: int = 20, max_frames: int = 20,
                    sim_thr: float = 0.10, model_name: str = "clip") -> dict:
    """Trả cặp (frame bắt đầu, frame kết thúc) quanh keyframe neo."""
    _load_indexes()
    _load_meta()

    if DEMO_MODE:
        return _demo_temporal(query_start, anchor_name)

    index, _, encode_fn, id_field = _model_parts(model_name)
    if index is None or not _meta:
        return {"error": "Chưa nạp được index hoặc metadata"}

    anchor = _name2meta.get(anchor_name)
    if anchor is None:
        return {"error": f"Không tìm thấy keyframe neo {anchor_name} trong metadata"}

    video     = anchor.get("video", "")
    anchor_fi = anchor.get("frame_idx", 0)
    fps       = float(anchor.get("fps", 25.0))

    frames = [m for m in _video_frames.get(video, []) if m.get(id_field, -1) >= 0]
    if not frames:
        return {"error": f"Video {video} chưa có frame nào được index"}

    pos = next((i for i, m in enumerate(frames) if m["frame_idx"] == anchor_fi), None)
    if pos is None:
        pos = min(range(len(frames)),
                  key=lambda i: abs(frames[i]["frame_idx"] - anchor_fi))

    q_start = encode_fn(query_start).ravel()
    q_end   = encode_fn(query_end).ravel()

    def score_frame(fid: int, q: np.ndarray) -> float:
        """Paper coi ComputeSimilarity là hộp đen. Dùng reconstruct() → dot,
        chính xác tuyệt đối; IndexFlatIP luôn hỗ trợ."""
        try:
            vec = index.reconstruct(int(fid)).astype("float32").ravel()
            return float(np.dot(q, vec))
        except Exception:
            return 0.0

    # Mở sang trái bằng query_start
    left = []
    for i in range(pos, max(-1, pos - max_frames - 1), -1):
        m = frames[i]
        s = score_frame(m[id_field], q_start)
        if s < sim_thr:
            break
        left.append((m, s))

    # Mở sang phải bằng query_end
    right = []
    for i in range(pos, min(len(frames), pos + max_frames + 1)):
        m = frames[i]
        s = score_frame(m[id_field], q_end)
        if s < sim_thr:
            break
        right.append((m, s))

    gap_frames = gap_c * fps
    start_pool = left  or [(anchor, 0.0)]
    end_pool   = right or [(anchor, 0.0)]

    best, best_score = None, -1.0
    for m1, s1 in start_pool:
        for m2, s2 in end_pool:
            fi1, fi2 = m1.get("frame_idx", 0), m2.get("frame_idx", 0)
            if fi2 >= fi1 and (fi2 - fi1) <= gap_frames and (s1 + s2) > best_score:
                best, best_score = (m1, m2), s1 + s2

    if best is None:
        best, best_score = (anchor, anchor), 0.0

    m1, m2 = best
    return {
        "video":           video,
        "start_frame":     m1["name"],
        "end_frame":       m2["name"],
        "start_ts":        m1.get("timestamp_str", ""),
        "end_ts":          m2.get("timestamp_str", ""),
        "start_frame_idx": m1.get("frame_idx"),
        "end_frame_idx":   m2.get("frame_idx"),
        "combined_score":  round(best_score * 100, 2),
        "start_url":       _image_url(m1["name"]),
        "end_url":         _image_url(m2["name"]),
        "n_left":          len(left),
        "n_right":         len(right),
    }


# ─────────────────────────────────────────────────────────────────────────────
#  CHẾ ĐỘ DEMO — chạy frontend khi chưa có index
#
#  Bật khi:  AIC_DEMO=1  HOẶC  không tìm thấy file index nào.
#  Sinh dữ liệu giả TẤT ĐỊNH theo truy vấn (cùng query → cùng kết quả), để
#  frontend test phân trang / sắp xếp / chọn frame mà không cần 1.29GB model.
# ─────────────────────────────────────────────────────────────────────────────

def _indexes_exist() -> bool:
    return os.path.exists(BEIT3_IDX_PATH) or os.path.exists(CLIP_IDX_PATH)


DEMO_MODE = (os.environ.get("AIC_DEMO", "").strip() in ("1", "true", "True")
             or not _indexes_exist())

_DEMO_VIDEOS = [f"L{g:02d}_V{v:03d}" for g in range(21, 31) for v in (1, 15, 42)]


def _demo_rng(seed_text: str):
    import random
    return random.Random(zlib.crc32(seed_text.encode("utf-8")))


def _demo_results(query: str, top_k: int, models: Optional[list[str]]) -> list[dict]:
    rng   = _demo_rng(query)
    names = models or list(MODEL_NAMES)
    out   = []
    for i in range(min(top_k, 100)):
        video = rng.choice(_DEMO_VIDEOS)
        shot  = rng.randint(1, 300)
        fidx  = rng.randint(100, 39000)
        name  = f"{video}-{shot:04d}-{fidx:06d}.jpg"
        secs  = fidx / 25.0
        routes = {n: {"rank": rng.randint(1, 50),
                      "score": round(rng.uniform(0.15, 0.45), 4)}
                  for n in names if rng.random() > 0.3}
        out.append({
            "frame":     name,
            "name":      name,
            "url":       _image_url(name),
            "distance":  round(95.0 - i * 0.7 + rng.random(), 2),
            "video":     video,
            "frame_idx": fidx,
            "timestamp": f"{int(secs // 60):02d}:{int(secs % 60):02d}",
            "routes":    routes or {names[0]: {"rank": i + 1, "score": 0.3}},
            "demo":      True,
        })
    return out


def _demo_temporal(query_start: str, anchor_name: str) -> dict:
    rng   = _demo_rng(anchor_name + query_start)
    video = anchor_name.split("-")[0]
    fi1   = rng.randint(100, 30000)
    fi2   = fi1 + rng.randint(30, 400)
    n1    = f"{video}-0001-{fi1:06d}.jpg"
    n2    = f"{video}-0001-{fi2:06d}.jpg"
    return {
        "video":           video,
        "start_frame":     n1,
        "end_frame":       n2,
        "start_ts":        f"{fi1 // 25 // 60:02d}:{fi1 // 25 % 60:02d}",
        "end_ts":          f"{fi2 // 25 // 60:02d}:{fi2 // 25 % 60:02d}",
        "start_frame_idx": fi1,
        "end_frame_idx":   fi2,
        "combined_score":  round(rng.uniform(40, 90), 2),
        "start_url":       _image_url(n1),
        "end_url":         _image_url(n2),
        "n_left":          rng.randint(1, 20),
        "n_right":         rng.randint(1, 20),
        "demo":            True,
    }


def system_status() -> dict:
    """Tình trạng từng thành phần — dùng cho /status, để biết còn thiếu gì."""
    _load_indexes()
    _load_meta()
    return {
        "demo_mode":       DEMO_MODE,
        "device":          DEVICE,
        "index_dir":       INDEX_DIR,
        "image_base_url":  IMAGE_BASE_URL,
        "pipeline_order":  "search → rerank (per-model) → ensemble",
        "files": {
            "beit3.index":            os.path.exists(BEIT3_IDX_PATH),
            "clip.index":             os.path.exists(CLIP_IDX_PATH),
            "beit3_mapping.json":     os.path.exists(BEIT3_MAP_PATH),
            "clip_mapping.json":      os.path.exists(CLIP_MAP_PATH),
            "keyframe_metadata.json": os.path.exists(META_PATH),
        },
        "vectors": {
            "beit3": _beit3_index.ntotal if _beit3_index is not None else 0,
            "clip":  _clip_index.ntotal  if _clip_index  is not None else 0,
        },
        "keyframes": len(_meta),
        "videos":    len(_video_frames),
        "models": {
            "fine_grained":   f"BEiT3-Large coco_retrieval 1024-dim "
                              f"({'loaded' if _beit3_model else 'lazy'})",
            "coarse_grained": f"OpenCLIP {CLIP_MODEL_NAME} 1280-dim "
                              f"({'loaded' if _clip_model else 'lazy'})",
        },
        "ensemble_weights": ENSEMBLE_WEIGHTS,
    }
