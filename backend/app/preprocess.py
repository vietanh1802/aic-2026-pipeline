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

Nếu chưa có file index/metadata, các hàm search trả về danh sách rỗng — không
sinh dữ liệu giả. Xem GET /status (system_status()) để biết còn thiếu file gì.
"""

import os, json, sys, subprocess as _sp
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
#
# FIX: trỏ về /static (root) thay vì /static/images vì ảnh nằm trong các thư
# mục con AIC2026_frames_p5_0XX/ — _image_url() dùng _name2relpath để giữ đủ
# cấu trúc thư mục con đó.
IMAGE_BASE_URL = os.environ.get("AIC_IMAGE_BASE_URL",
                                "http://localhost:8000/static")

# Marker dùng để trích relative path từ URL mapping (e.g.
# "http://localhost:8000/static/AIC2026_frames_p5_016/file.jpg"
# → "AIC2026_frames_p5_016/file.jpg")
_STATIC_MARKER = "/static/"

# Thư mục ảnh trên đĩa — để biết keyframe đã có file jpg chưa (xem _has_image).
IMAGES_DIR = os.environ.get("AIC_IMAGES_DIR", os.path.join(BASE_DIR, "static", "images"))

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

# Model chạy khi caller không chỉ định. AIC_MODELS=beit3 để chạy một nhánh khi
# chưa tải weights CLIP ViT-bigG-14 (~10GB). Lọc theo MODEL_NAMES để tên gõ sai
# không lọt vào.
ACTIVE_MODELS = tuple(
    n for n in (m.strip() for m in os.environ.get("AIC_MODELS", "").split(","))
    if n in MODEL_NAMES
) or MODEL_NAMES

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

# Bảng tra: basename → relative path dưới /static/
# Dùng để tái hiện URL đầy đủ (kể cả thư mục con) từ mapping gốc của notebook.
# Ví dụ: "file.jpg" → "AIC2026_frames_p5_016/file.jpg"
_name2relpath: dict[str, str] = {}


# ─────────────────────────────────────────────────────────────────────────────
#  Loaders
# ─────────────────────────────────────────────────────────────────────────────
class _Beit3Tokenizer:
    """Port trực tiếp thuật toán XLMRobertaTokenizer (transformers 4.0.1,
    Apache 2.0 License — https://huggingface.co/transformers/v4.0.1/_modules/
    transformers/models/xlm_roberta/tokenization_xlm_roberta.html) bằng
    sentencepiece thuần, KHÔNG qua transformers.XLMRobertaTokenizer.

    Lý do: transformers mới nhất đổi API constructor (vocab_file → vocab),
    còn các bản cũ đủ để giữ API cũ thì kéo theo tokenizers không có wheel
    Windows Python 3.12 (cần Rust compiler để build từ source). Port thẳng
    logic đã verify, tự chủ hoàn toàn, không phụ thuộc version transformers.

    Interface giống hệt XLMRobertaTokenizer(text, return_tensors="pt")
    ["input_ids"] — encode_text_beit3() KHÔNG cần đổi gì cả.
    """

    def __init__(self, spm_path: str):
        import sentencepiece as spm
        self.sp = spm.SentencePieceProcessor()
        self.sp.Load(spm_path)
        # fairseq special tokens: <s>=0 <pad>=1 </s>=2 <unk>=3 — verify từ
        # chính source 4.0.1: "self.fairseq_tokens_to_ids = {'<s>': 0,
        # '<pad>': 1, '</s>': 2, '<unk>': 3}", "self.fairseq_offset = 1"
        self.bos_id, self.pad_id, self.eos_id, self.unk_id = 0, 1, 2, 3
        self.fairseq_offset = 1

    def _convert_token_to_id(self, token: str) -> int:
        """Verify từ 4.0.1: 'spm_id = self.sp_model.PieceToId(token);
        return spm_id + self.fairseq_offset if spm_id else self.unk_token_id'"""
        spm_id = self.sp.PieceToId(token)
        return spm_id + self.fairseq_offset if spm_id else self.unk_id

    def __call__(self, text: str, return_tensors: str = "pt") -> dict:
        """Verify từ 4.0.1 build_inputs_with_special_tokens (single sequence):
        '[self.cls_token_id] + token_ids_0 + [self.sep_token_id]'
        cls_token_id = bos_id = 0, sep_token_id = eos_id = 2."""
        pieces = self.sp.EncodeAsPieces(text)
        ids = [self._convert_token_to_id(p) for p in pieces]
        input_ids = [self.bos_id] + ids + [self.eos_id]
        if return_tensors == "pt":
            import torch
            return {"input_ids": torch.tensor([input_ids], dtype=torch.long)}
        return {"input_ids": [input_ids]}


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

    print(f"[preprocess] Loading {BEIT3_MODEL_NAME}...")
    model = create_model(BEIT3_MODEL_NAME, pretrained=False)
    ckpt  = torch.load(ckpt_path, map_location="cpu")
    sd    = ckpt["model"] if "model" in ckpt else ckpt
    missing, unexpected = model.load_state_dict(sd, strict=False)
    del ckpt, sd
    model.eval().to(DEVICE)

    _beit3_model     = model
    _beit3_tokenizer = _Beit3Tokenizer(spm_path)
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


def _build_relpath_from_map(mapping: dict) -> None:
    """Trích relative path dưới /static/ từ URL gốc trong mapping và lưu vào
    _name2relpath.  Cần chạy mỗi khi nạp mapping để _image_url() trả đúng
    URL kể cả khi ảnh nằm trong thư mục con (AIC2026_frames_p5_0XX/).

    Ví dụ URL gốc (notebook sinh ra):
      "http://localhost:8000/static/AIC2026_frames_p5_016/file.jpg"
    → rel_path = "AIC2026_frames_p5_016/file.jpg"
    → _name2relpath["file.jpg"] = "AIC2026_frames_p5_016/file.jpg"

    setdefault: nếu cùng tên file xuất hiện ở cả 2 mapping (beit3 + clip),
    giữ entry đầu tiên — chúng phải trỏ cùng file nên không quan trọng thứ tự.
    """
    for url in mapping.values():
        if not url:
            continue
        fname = os.path.basename(url)
        if not fname:
            continue
        idx = url.find(_STATIC_MARKER)
        rel = url[idx + len(_STATIC_MARKER):] if idx >= 0 else fname
        _name2relpath.setdefault(fname, rel)


def _load_indexes():
    global _beit3_index, _clip_index, _beit3_map, _clip_map
    if _beit3_index is None and os.path.exists(BEIT3_IDX_PATH):
        _beit3_index = faiss.read_index(BEIT3_IDX_PATH)
        if os.path.exists(BEIT3_MAP_PATH):
            with open(BEIT3_MAP_PATH, encoding="utf-8") as f:
                _beit3_map = json.load(f)
            _build_relpath_from_map(_beit3_map)
        print(f"[preprocess] BEiT3 FAISS: {_beit3_index.ntotal} vectors")
    if _clip_index is None and os.path.exists(CLIP_IDX_PATH):
        _clip_index = faiss.read_index(CLIP_IDX_PATH)
        if os.path.exists(CLIP_MAP_PATH):
            with open(CLIP_MAP_PATH, encoding="utf-8") as f:
                _clip_map = json.load(f)
            _build_relpath_from_map(_clip_map)
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
    """Tạo URL phục vụ ảnh.

    Tra _name2relpath để lấy lại đường dẫn đầy đủ dưới /static/ (kể cả thư
    mục con).  Nếu không có trong bảng tra (ảnh không qua mapping), dùng name
    trực tiếp — fallback an toàn.

    Ví dụ:
      name     = "L21_V015-0042-003729.jpg"
      rel_path = "AIC2026_frames_p5_016/L21_V015-0042-003729.jpg"
      URL      = "http://localhost:8000/static/AIC2026_frames_p5_016/L21_V015-0042-003729.jpg"
    """
    rel = _name2relpath.get(name, name)
    return f"{IMAGE_BASE_URL.rstrip('/')}/{rel}"


def _has_image(name: str) -> bool:
    """Keyframe này đã có file jpg trên đĩa chưa.

    Index phủ đủ 868,524 frame nhưng ảnh tải riêng theo ZIP hàng chục GB, nên
    phần lớn kết quả trỏ tới ảnh chưa có — UI cần biết để vẽ placeholder.
    Stat từng file (≤500 lần/query) thay vì cache danh sách, để đúng cả khi ZIP
    đang được giải nén lúc server chạy.
    """
    # rel tính từ gốc /static/ (vd "images/x.jpg"), còn IMAGES_DIR = <static>/images.
    rel = _name2relpath.get(name, name)
    static_root = os.path.dirname(IMAGES_DIR)
    return os.path.exists(os.path.join(static_root, rel.replace("/", os.sep)))


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
            "has_image": _has_image(key),
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

    Nếu chưa có index nào, per_model rỗng → trả về [] (không sinh dữ liệu giả).
    """
    _load_indexes()
    _load_meta()

    per_model: dict[str, list[dict]] = {}
    for name in (models or list(ACTIVE_MODELS)):
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


def system_status() -> dict:
    """Tình trạng từng thành phần — dùng cho /status, để biết còn thiếu gì."""
    _load_indexes()
    _load_meta()
    # Số ảnh thật trên đĩa — cho biết vì sao nhiều kết quả có has_image=false.
    try:
        n_images = sum(1 for _ in os.scandir(IMAGES_DIR)
                       if _.is_file() and _.name.lower().endswith(".jpg"))
    except OSError:
        n_images = 0

    return {
        "device":          DEVICE,
        "index_dir":       INDEX_DIR,
        "images_dir":      IMAGES_DIR,
        "image_base_url":  IMAGE_BASE_URL,
        "pipeline_order":  "search → rerank (per-model) → ensemble",
        "active_models":   list(ACTIVE_MODELS),
        "images_on_disk":  n_images,
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
        "keyframes":   len(_meta),
        "videos":      len(_video_frames),
        "relpath_map": len(_name2relpath),
        "models": {
            "fine_grained":   f"BEiT3-Large coco_retrieval 1024-dim "
                              f"({'loaded' if _beit3_model else 'lazy'})",
            "coarse_grained": f"OpenCLIP {CLIP_MODEL_NAME} 1280-dim "
                              f"({'loaded' if _clip_model else 'lazy'})",
        },
        "ensemble_weights": ENSEMBLE_WEIGHTS,
    }