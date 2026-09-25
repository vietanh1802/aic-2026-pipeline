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
"""

import os, json, re, sys, time, subprocess as _sp
from typing import Optional
from urllib.parse import urlparse

import numpy as np
import faiss
import torch

# keyframe_metadata.json is 437 MB; json.load takes ~60s and blocks the process.
# orjson parses the same file in ~15s. Optional: without it we fall back to the
# stdlib and only startup gets slower.
try:
    import orjson as _orjson
except ImportError:
    _orjson = None


def _read_json(path: str):
    """Read JSON, preferring orjson. Returns exactly what json.load returns."""
    if _orjson is not None:
        with open(path, "rb") as f:
            return _orjson.loads(f.read())
    with open(path, encoding="utf-8") as f:
        return json.load(f)

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

# [siglip2] Model thứ 3. CỐ Ý tách riêng: siglip2_giant_mapping.json là json
# ĐỘC LẬP của SigLIP2 (faiss_id -> đường dẫn ảnh); keyframe_metadata.json
# KHÔNG bị thêm field nào, nên không phải sinh lại file 594MB đó.
SIGLIP2_IDX_PATH = os.path.join(INDEX_DIR, "siglip2_giant.index")
SIGLIP2_MAP_PATH = os.path.join(INDEX_DIR, "siglip2_giant_mapping.json")

# The five files that have to come from the same generation run. Kept in one
# place because /status reports on all of them three different ways.
INDEX_SET_FILES = (
    ("beit3.index",            BEIT3_IDX_PATH),
    ("clip.index",             CLIP_IDX_PATH),
    ("beit3_mapping.json",     BEIT3_MAP_PATH),
    ("clip_mapping.json",      CLIP_MAP_PATH),
    ("keyframe_metadata.json", META_PATH),
    # [siglip2] 2 file mới. Thiếu -> /status báo, backend vẫn chạy 2 model cũ.
    ("siglip2_giant.index",         SIGLIP2_IDX_PATH),
    ("siglip2_giant_mapping.json",  SIGLIP2_MAP_PATH),
)

# The notebook-generated mappings embed absolute localhost:8000 URLs. We keep
# only the path below /static/ and re-join it against this variable, so moving
# the images to S3 or a CDN is an env change rather than a re-index.
#
# This points at /static, not /static/images, because the relative path taken
# from the mapping already starts with "images/". Both mappings were checked
# (868,524 + 105,817 entries): a single "images" prefix, flat, no subdirectories.
# The S3 keys therefore mirror it as "images/<file>.jpg" and _image_url() needs
# no change when serving from a CDN.
IMAGE_BASE_URL = os.environ.get("AIC_IMAGE_BASE_URL",
                                "http://localhost:8000/static")

# Marker used to cut the relative path out of a mapping URL, e.g.
# "http://localhost:8000/static/images/K19_V001-0000-29.jpg"
# -> "images/K19_V001-0000-29.jpg"
_STATIC_MARKER = "/static/"

# On-disk image directory, used by _has_image to tell whether a frame is present.
IMAGES_DIR = os.environ.get("AIC_IMAGES_DIR", os.path.join(BASE_DIR, "static", "images"))

# Are images served by this process, or by an external store (S3 behind a CDN)?
# Derived from the host in IMAGE_BASE_URL: once it points outward we can no
# longer stat the files.
_LOCAL_HOSTS = {"", "localhost", "127.0.0.1", "::1", "0.0.0.0", "host.docker.internal"}
IMAGES_REMOTE = (urlparse(IMAGE_BASE_URL).hostname or "").lower() not in _LOCAL_HOSTS

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"

# ─── Model config ────────────────────────────────────────────────────────────
BEIT3_CKPT_URL   = "https://github.com/addf400/files/releases/download/beit3/beit3_large_patch16_384_coco_retrieval.pth"
BEIT3_SPM_URL    = "https://github.com/addf400/files/releases/download/beit3/beit3.spm"
BEIT3_MODEL_NAME = "beit3_large_patch16_384_retrieval"
BEIT3_REPO_DIR   = os.path.join(BASE_DIR, "unilm_beit3")
CLIP_MODEL_NAME  = "ViT-bigG-14"
CLIP_PRETRAINED  = "laion2b_s39b_b160k"

# Alg.3 — trọng số ensemble. Tổng chuẩn hoá về 1 lúc chạy (pseudocode dòng 2).
# [siglip2] Thêm entry thứ 3. _merge_ensemble() chuẩn hoá Σw=1 theo TẬP model
# thực sự có hit ở từng lần gọi, nên 3 trọng số bằng nhau vẫn co giãn đúng cho
# mọi tổ hợp checkbox (1, 2 hay cả 3 model).
ENSEMBLE_WEIGHTS = {"beit3": 0.5, "clip": 0.5, "siglip2": 0.5}

MODEL_NAMES = ("beit3", "clip", "siglip2")

# [siglip2] KHÔNG phải tên field trong keyframe_metadata.json — SigLIP2 dùng
# json riêng nên metadata không có field nào của nó. Đây là cờ nội bộ để
# _fid_of() biết phải tra qua _siglip2_name2id thay vì đọc thẳng metadata.
SIGLIP2_ID_FIELD = "__siglip2_own_json__"
SIGLIP2_MODEL_ID = "google/siglip2-giant-opt-patch16-384"
SIGLIP2_DIM      = 1536
# [siglip2] Weights nằm trong INDEX_DIR như beit3/clip — xem _ensure_siglip2_model().
SIGLIP2_LOCAL_DIR = os.path.join(INDEX_DIR, "siglip2_giant_model")

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

# [siglip2]
_siglip2_model = _siglip2_proc = None
_siglip2_index = None
_siglip2_map   = None                       # faiss_id (str) -> đường dẫn ảnh
_siglip2_name2id: dict[str, int] = {}       # basename ảnh -> faiss_id (tra ngược)

_meta: list[dict] = []
_meta_loaded  = False
_name2meta:   dict[str, dict] = {}
_clipid2meta: dict[int, dict] = {}
_video_frames: dict[str, list[dict]] = {}   # video → keyframe sắp theo frame_idx

# Bảng tra: basename → relative path dưới /static/
# Dùng để tái hiện URL đầy đủ (kể cả thư mục con) từ mapping gốc của notebook.
# Ví dụ: "file.jpg" → "AIC2026_frames_p5_016/file.jpg"
_name2relpath: dict[str, str] = {}

# Identity of each index file at the moment it was read into memory.
#
# /status used to report counts only, and counts cannot answer the question an
# operator actually has after publishing a new index set: is the process serving
# it yet? A regeneration that keeps the same keyframes reports the same counts,
# and those counts come from module globals, so a container that never restarted
# looks exactly like one that did. Size and mtime captured here, compared with
# the files on disk at request time, tell the two apart.
#
# mtime is meaningful because `aws s3 sync` stamps the object's LastModified
# onto the file it downloads (verified against s3://aic2026-artifacts/indexes/
# on 2026-08-19), so this value can be matched against S3 head-object.
_index_loaded: dict[str, dict] = {}


def _file_identity(path: str) -> Optional[dict]:
    """Size and mtime of one file, or None when it is not there."""
    try:
        st = os.stat(path)
    except OSError:
        return None
    return {
        "bytes": st.st_size,
        "mtime": time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime(st.st_mtime)),
    }


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


def _ensure_clip_checkpoint() -> str:
    """Tải checkpoint CLIP về INDEX_DIR (cùng pattern với BEiT3), CHỈ 1 LẦN —
    tránh phải tải lại toàn bộ ~10GB mỗi lần server khởi động.

    Root cause: open_clip.create_model_and_transforms(pretrained="laion2b_...")
    (tag string) tự tải qua cache hệ thống mặc định của huggingface_hub — cache
    đó không ổn định trong môi trường đang chạy (đổi ổ đĩa, venv mới, nhiều máy
    khác nhau...), nên liên tục tải lại và bị HuggingFace giới hạn tốc độ
    (rate limit) do quá nhiều request tải file lớn.

    Fix: tải tường minh 1 lần vào INDEX_DIR — cùng thư mục bền vững đã dùng
    cho beit3 checkpoint — rồi truyền THẲNG local path vào open_clip thay vì
    tag string. open_clip's create_model() có nhánh "elif os.path.exists(
    pretrained): checkpoint_path = pretrained" — dùng local path là cách dùng
    chính thức, không phải hack.

    Dùng huggingface_hub.hf_hub_download() (không phải curl thuần như BEiT3)
    vì file này lưu qua HF Xet storage (verify từ trang model chính thức:
    "Xet efficiently stores Large Files inside Git") — URL tĩnh đơn giản
    không tải đúng được, cần đúng client hf_hub_download để resolve.
    """
    os.makedirs(INDEX_DIR, exist_ok=True)
    ckpt_path = os.path.join(INDEX_DIR, "open_clip_model.safetensors")
    if not os.path.exists(ckpt_path):
        print("[preprocess] Downloading CLIP checkpoint (~10.2GB, chỉ 1 lần "
              f"vào {ckpt_path})...")
        from huggingface_hub import hf_hub_download
        downloaded = hf_hub_download(
            repo_id="laion/CLIP-ViT-bigG-14-laion2B-39B-b160k",
            filename="open_clip_model.safetensors",
            local_dir=INDEX_DIR,
        )
        # hf_hub_download có thể trả về path khác đôi chút tuỳ version (vd có
        # symlink vào cache trước rồi copy) — đảm bảo file cuối nằm đúng tên
        # đã khai báo ở ckpt_path để lần sau os.path.exists() check đúng chỗ.
        if os.path.abspath(downloaded) != os.path.abspath(ckpt_path) and os.path.exists(downloaded):
            os.replace(downloaded, ckpt_path)
        print(f"[preprocess] CLIP checkpoint đã lưu tại {ckpt_path}")
    return ckpt_path


def _load_clip():
    """Nạp OpenCLIP ViT-bigG-14 (ref [41], nhánh coarse-grained).

    Tải checkpoint tường minh vào INDEX_DIR qua _ensure_clip_checkpoint()
    thay vì để open_clip tự tải qua cache hệ thống mặc định — xem giải thích
    đầy đủ trong docstring hàm đó.
    """
    global _clip_model, _clip_proc, _clip_tokenizer
    if _clip_model is None:
        import open_clip
        ckpt_path = _ensure_clip_checkpoint()
        _clip_model, _, _clip_proc = open_clip.create_model_and_transforms(
            CLIP_MODEL_NAME, pretrained=ckpt_path, device=DEVICE)
        _clip_model.eval()
        _clip_tokenizer = open_clip.get_tokenizer(CLIP_MODEL_NAME)
        print(f"[preprocess] CLIP {CLIP_MODEL_NAME} loaded on {DEVICE} "
              f"(checkpoint local: {ckpt_path})")


def _build_relpath_from_map(mapping: dict) -> None:
    """Trích relative path dưới /static/ từ URL gốc trong mapping và lưu vào
    _name2relpath.  Cần chạy mỗi khi nạp mapping để _image_url() trả đúng
    URL kể cả khi ảnh nằm trong thư mục con (AIC2026_frames_p5_0XX/).

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





def _is_siglip2_dir(d: str) -> bool:
    """[siglip2] Thư mục này có phải bản SigLIP2 giải nén phẳng không?

    Chỉ có config.json là chưa đủ: INDEX_DIR còn chứa index/mapping của 2 model
    kia, và về lý thuyết có thể có config.json của thứ khác. Đọc model_type /
    architectures để chắc chắn, thay vì đoán theo sự tồn tại của file.
    """
    cfg = os.path.join(d, "config.json")
    if not os.path.exists(cfg):
        return False
    try:
        with open(cfg, encoding="utf-8") as f:
            c = json.load(f)
    except Exception:
        return False
    blob = (str(c.get("model_type", "")) + " "
            + " ".join(c.get("architectures") or [])).lower()
    return "siglip" in blob

def _ensure_siglip2_model() -> str:
    """[siglip2] Trả về nguồn nạp SigLIP2, ưu tiên bản ĐÃ CÓ trong INDEX_DIR.

    Cùng pattern và CÙNG LÝ DO với _load_beit3() (checkpoint .pth + .spm trong
    INDEX_DIR) và _ensure_clip_checkpoint() (open_clip_model.safetensors trong
    INDEX_DIR): cache mặc định của huggingface_hub không ổn định trong môi
    trường đang chạy (đổi ổ đĩa, venv mới, nhiều máy khác nhau), nên để
    from_pretrained("google/...") tự xử lý là mở đường tải lại ~3.5GB mỗi lần
    và ăn rate-limit của HuggingFace. Tải tường minh 1 lần vào INDEX_DIR —
    cùng thư mục bền vững đã dùng cho 2 model kia.

    Chấp nhận cả 4 kiểu bố trí, vì tuỳ cách tải/copy mà file nằm khác nhau:
      0. PHẲNG ngay trong INDEX_DIR: config.json + model-*.safetensors +
         tokenizer* nằm chung với beit3.index/clip.index. Đây là kết quả của
         "tải HF xong copy toàn bộ vào indexes/" — kiểu hay gặp nhất.
      1. INDEX_DIR/siglip2_giant_model/config.json   (snapshot_download local_dir)
      2. INDEX_DIR/siglip2-giant-opt-patch16-384/    (copy tay, giữ tên repo)
      3. INDEX_DIR/models--google--siglip2-.../snapshots/<hash>/  (cache layout,
         tức copy nguyên thư mục ~/.cache/huggingface/hub qua)
    Không thấy kiểu nào thì mới tải, và tải vào (1).
    """
    # (0) Weights nằm PHẲNG ngay trong INDEX_DIR — kết quả của việc copy thẳng
    #     nội dung snapshot vào indexes/ (config.json + model-*.safetensors +
    #     tokenizer* nằm chung với beit3.index/clip.index). Phải kiểm model_type
    #     vì INDEX_DIR có thể chứa config.json của thứ khác.
    if _is_siglip2_dir(INDEX_DIR):
        return INDEX_DIR

    for cand in (SIGLIP2_LOCAL_DIR,
                 os.path.join(INDEX_DIR, SIGLIP2_MODEL_ID.split("/")[-1])):
        if os.path.exists(os.path.join(cand, "config.json")):
            return cand

    snap_root = os.path.join(INDEX_DIR,
                             "models--" + SIGLIP2_MODEL_ID.replace("/", "--"),
                             "snapshots")
    if os.path.isdir(snap_root):
        for s in sorted(os.listdir(snap_root)):
            p = os.path.join(snap_root, s)
            if os.path.exists(os.path.join(p, "config.json")):
                return p

    os.makedirs(INDEX_DIR, exist_ok=True)
    print(f"[preprocess] Downloading SigLIP2 (~3.5GB, chỉ 1 lần vào "
          f"{SIGLIP2_LOCAL_DIR})...")
    from huggingface_hub import snapshot_download
    snapshot_download(repo_id=SIGLIP2_MODEL_ID, local_dir=SIGLIP2_LOCAL_DIR)
    print(f"[preprocess] SigLIP2 model đã lưu tại {SIGLIP2_LOCAL_DIR}")
    return SIGLIP2_LOCAL_DIR

def _load_siglip2():
    """[siglip2] Nạp SigLIP2-Giant — cùng khuôn _load_beit3()/_load_clip().

    Dùng transformers.AutoModel/AutoProcessor GIỐNG HỆT cell indexing đã tạo ra
    siglip2_giant.index, để embedding TEXT ở đây nằm cùng không gian vector với
    embedding ẢNH trong index — lệch processor/model version có thể sai lặng lẽ
    mà không báo lỗi gì.
    """
    global _siglip2_model, _siglip2_proc
    if _siglip2_model is not None:
        return
    from transformers import AutoProcessor, AutoModel

    src = _ensure_siglip2_model()
    dtype = torch.float16 if DEVICE == "cuda" else torch.float32
    _siglip2_proc = AutoProcessor.from_pretrained(src)
    # `dtype=` là kwarg MỚI; transformers < 4.56 chỉ nhận `torch_dtype=`.
    try:
        _siglip2_model = AutoModel.from_pretrained(src, dtype=dtype)
    except TypeError:
        _siglip2_model = AutoModel.from_pretrained(src, torch_dtype=dtype)
    _siglip2_model = _siglip2_model.to(DEVICE).eval()
    # In ra CLASS và model_type thật sự nạp được. INDEX_DIR có thể chứa
    # config.json/tokenizer* của nhiều model (CLIP cũng để file ở đó), nạp nhầm
    # thì embedding sai lặng lẽ — thà nói to ra ngay lúc khởi động.
    _mt = getattr(getattr(_siglip2_model, "config", None), "model_type", "?")
    print(f"[preprocess] SigLIP2 loaded on {DEVICE} (dtype={dtype}) từ {src}")
    print(f"[preprocess] SigLIP2 class={type(_siglip2_model).__name__} "
          f"model_type={_mt}")
    if "siglip" not in str(_mt).lower():
        print(f"[preprocess] ⚠ model_type={_mt!r} KHÔNG phải siglip — gần như "
              f"chắc chắn đã nạp nhầm model từ {src}. Tách weights SigLIP2 ra "
              f"thư mục riêng (INDEX_DIR/siglip2_giant_model/).")


def _load_indexes():
    global _beit3_index, _clip_index, _beit3_map, _clip_map
    global _siglip2_index, _siglip2_map, _siglip2_name2id
    if _beit3_index is None and os.path.exists(BEIT3_IDX_PATH):
        _beit3_index = faiss.read_index(BEIT3_IDX_PATH)
        _index_loaded["beit3.index"] = _file_identity(BEIT3_IDX_PATH)
        if os.path.exists(BEIT3_MAP_PATH):
            _beit3_map = _read_json(BEIT3_MAP_PATH)
            _index_loaded["beit3_mapping.json"] = _file_identity(BEIT3_MAP_PATH)
            _build_relpath_from_map(_beit3_map)
        print(f"[preprocess] BEiT3 FAISS: {_beit3_index.ntotal} vectors")
    if _clip_index is None and os.path.exists(CLIP_IDX_PATH):
        _clip_index = faiss.read_index(CLIP_IDX_PATH)
        _index_loaded["clip.index"] = _file_identity(CLIP_IDX_PATH)
        if os.path.exists(CLIP_MAP_PATH):
            _clip_map = _read_json(CLIP_MAP_PATH)
            _index_loaded["clip_mapping.json"] = _file_identity(CLIP_MAP_PATH)
            _build_relpath_from_map(_clip_map)
        print(f"[preprocess] CLIP FAISS: {_clip_index.ntotal} vectors")
    # [siglip2] Cùng khuôn 2 khối trên, KHÔNG sửa gì 2 khối cũ.
    #
    # Khác 1 điểm: dựng thêm _siglip2_name2id (basename -> faiss_id). Vì
    # keyframe_metadata.json không mang field nào của SigLIP2, mọi chỗ cần
    # "faiss_id SigLIP2 của keyframe này" đều đi qua bảng tra ngược này.
    if _siglip2_index is None and os.path.exists(SIGLIP2_IDX_PATH):
        _siglip2_index = faiss.read_index(SIGLIP2_IDX_PATH)
        _index_loaded["siglip2_giant.index"] = _file_identity(SIGLIP2_IDX_PATH)
        if os.path.exists(SIGLIP2_MAP_PATH):
            _siglip2_map = _read_json(SIGLIP2_MAP_PATH)
            _index_loaded["siglip2_giant_mapping.json"] = _file_identity(SIGLIP2_MAP_PATH)
            _build_relpath_from_map(_siglip2_map)
            _siglip2_name2id = {os.path.basename(p): int(i)
                                for i, p in _siglip2_map.items() if p}
            print(f"[preprocess] SigLIP2 mapping: {len(_siglip2_name2id)} keyframes")
        else:
            print("[preprocess] ⚠ SigLIP2: thiếu siglip2_giant_mapping.json -> "
                  "search được nhưng KHÔNG rerank/temporal/trake được")
        print(f"[preprocess] SigLIP2 FAISS: {_siglip2_index.ntotal} vectors")


def _load_meta():
    """Nạp keyframe_metadata.json và dựng sẵn 3 bảng tra dùng nhiều lần."""
    global _meta, _meta_loaded, _name2meta, _clipid2meta, _video_frames
    if _meta_loaded or not os.path.exists(META_PATH):
        return
    _meta = _read_json(META_PATH)
    _meta_loaded = True
    _index_loaded["keyframe_metadata.json"] = _file_identity(META_PATH)

    _name2meta   = {m["name"]: m for m in _meta}
    _clipid2meta = {int(m["faiss_id_clip"]): m
                    for m in _meta if m.get("faiss_id_clip", -1) >= 0}

    _video_frames = {}
    for m in _meta:
        _video_frames.setdefault(m.get("video", "?"), []).append(m)
    for v in _video_frames:
        _video_frames[v].sort(key=lambda m: m.get("frame_idx", 0))

    print(f"[preprocess] Metadata: {len(_meta)} keyframes · {len(_video_frames)} videos")


def frames_for_video(video_id : str) -> list[str] :
    """Every frame name belonging to one video, in frame_idx order.

    Thin read-only view over _video_frames (already built by _load_meta() at
    startup from keyframe_metadata.json's own "video" field -- no new preload
    step, no extra memory beyond the dict wrapper itself, since these are the
    same metadata objects _meta already holds). Exists so other modules (e.g.
    text_lookup.py) never reach into _video_frames directly. An empty list
    means the video has no keyframes in the visual corpus -- see /status's
    "videos" count, which is exactly len(_video_frames)."""
    return [m["name"] for m in _video_frames.get(video_id, [])]


def fps_for_video(video_id : str) -> float :
    """fps of one video, read off its own keyframe metadata. 25.0 fallback
    matches temporal_search()'s own default when a record has no fps."""
    frames = _video_frames.get(video_id, [])
    return float(frames[0]["fps"]) if frames else 25.0


def _model_parts(model_name: str):
    """Trả (index, mapping, hàm encode text, tên trường faiss_id) của 1 model."""
    if model_name == "beit3":
        return _beit3_index, _beit3_map, encode_text_beit3, "faiss_id_beit3"
    # [siglip2] id_field là CỜ NỘI BỘ, không phải field metadata — xem _fid_of().
    if model_name == "siglip2":
        return _siglip2_index, _siglip2_map, encode_text_siglip2, SIGLIP2_ID_FIELD
    return _clip_index, _clip_map, encode_text_clip, "faiss_id_clip"


def _fid_of(m: dict, id_field: str) -> int:
    """faiss_id của 1 bản ghi metadata, trong không gian id của model đang xét.

    [siglip2] beit3/clip đọc thẳng field trong keyframe_metadata.json. SigLIP2
    KHÔNG có field nào ở đó (dùng json riêng), nên tra ngược theo tên file qua
    _siglip2_name2id — dựng từ siglip2_giant_mapping.json lúc _load_indexes().

    Trả -1 khi không tra được: mọi nơi gọi đều đã lọc `>= 0` sẵn, nên keyframe
    nào SigLIP2 chưa index (index mới chạy một phần) tự bị bỏ qua thay vì làm
    hỏng cả lượt tìm.
    """
    if id_field == SIGLIP2_ID_FIELD:
        return int(_siglip2_name2id.get(m.get("name", ""), -1))
    return int(m.get(id_field, -1))


def _image_url(name: str) -> str:
    """Tạo URL phục vụ ảnh.

    Tra _name2relpath để lấy lại đường dẫn đầy đủ dưới /static/ (kể cả thư
    mục con).  Nếu không có trong bảng tra (ảnh không qua mapping), dùng name
    trực tiếp — fallback an toàn.

    Example:
      name      = "K19_V001-0000-29.jpg"
      rel_path  = "images/K19_V001-0000-29.jpg"
      local URL = "http://localhost:8000/static/images/K19_V001-0000-29.jpg"
      S3 URL    = "https://aic-frames.umaga.fun/images/K19_V001-0000-29.jpg"
    """
    rel = _name2relpath.get(name, name)
    return f"{IMAGE_BASE_URL.rstrip('/')}/{rel}"


def _has_image(name: str) -> bool:
    """Whether this result has an image the UI can display.

    Served locally, we stat each file: the index covers all 868,524 frames but
    the images arrive separately as tens of gigabytes of ZIPs, so most results
    point at a file that is not there yet and the UI needs to know. We stat
    rather than cache a listing so the answer stays correct while a ZIP is being
    extracted underneath a running server.

    Served remotely, stat is impossible and unnecessary: FrameDisplay already
    falls back to a placeholder on image error. Carrying an 868k-name manifest
    here just to predict what the browser discovers on its own is not worth it,
    least of all for the few hours the seed job is running.
    """
    if IMAGES_REMOTE:
        return True
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



def _siglip2_features(outputs, kind: str):
    """[siglip2] Lấy tensor feature từ output của get_text_features()/
    get_image_features(), chịu được mọi kiểu trả về của các bản transformers.

    KHỚP CHÍNH XÁC extract_siglip2_features() trong cell indexing đã tạo ra
    siglip2_giant.index — cùng THỨ TỰ ƯU TIÊN, nên text và ảnh chắc chắn nằm
    cùng một không gian vector:
        1. Tensor trực tiếp
        2. .pooler_output      <- transformers 5.x trả cái này
        3. .text_embeds / .image_embeds
        4. tensor 2D đầu tiên trong tuple/list

    Docstring gốc của cell indexing: "For current Transformers 5.x in the
    user's environment, it returns BaseModelOutputWithPooling. We extract
    pooler_output first." Index đã build bằng pooler_output, nên nhánh text
    PHẢI theo đúng thứ tự này, không được đổi.
    """
    embeds_attr = "text_embeds" if kind == "text" else "image_embeds"

    if torch.is_tensor(outputs):
        feats = outputs
    elif hasattr(outputs, "pooler_output") and outputs.pooler_output is not None:
        feats = outputs.pooler_output
    elif hasattr(outputs, embeds_attr) and getattr(outputs, embeds_attr) is not None:
        feats = getattr(outputs, embeds_attr)
    elif isinstance(outputs, (tuple, list)):
        feats = next((x for x in outputs if torch.is_tensor(x) and x.ndim == 2), None)
        if feats is None:
            raise RuntimeError(f"Không tìm thấy tensor 2D trong output SigLIP2 ({kind})")
    else:
        raise TypeError(f"Kiểu output SigLIP2 không hỗ trợ ({kind}): {type(outputs)}")

    if not torch.is_tensor(feats):
        raise TypeError(f"Feature SigLIP2 không phải tensor ({kind}): {type(feats)}")
    if feats.ndim != 2 or feats.shape[-1] != SIGLIP2_DIM:
        raise RuntimeError(
            f"Feature SigLIP2 sai shape ({kind}): {tuple(feats.shape)}, "
            f"mong đợi (batch, {SIGLIP2_DIM}). Nhiều khả năng nạp nhầm model — "
            f"kiểm tra config.json trong INDEX_DIR có bị lẫn của model khác không.")
    return feats

@torch.no_grad()
def encode_text_siglip2(text: str) -> np.ndarray:
    """SigLIP2-Giant -> (1, 1536) float32 L2-normalized.

    [siglip2] CHƯA KIỂM CHỨNG bằng thực nghiệm: cell indexing chỉ gọi
    get_image_features() để build index, chưa bao giờ chạy nhánh TEXT.
    padding="max_length" theo đúng khuyến nghị của dòng SigLIP/SigLIP2 (train
    theo độ dài cố định; câu ngắn không pad sẽ lệch phân bố so với lúc train).
    Chạy verify_siglip2.py trước khi tin dùng trong ensemble.
    """
    _load_siglip2()
    inputs = _siglip2_proc(text=[text], padding="max_length", truncation=True,
                           return_tensors="pt")
    inputs = {k: v.to(DEVICE) for k, v in inputs.items()}
    out    = _siglip2_model.get_text_features(**inputs)
    feats  = _siglip2_features(out, "text")
    feats  = feats.float()
    feats  = feats / feats.norm(dim=-1, keepdim=True).clamp_min(1e-12)
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
    # [siglip2] Lấy id_field qua _model_parts để model thứ 3 nhận đúng cờ
    # SIGLIP2_ID_FIELD, thay cho ternary 2 nhánh cũ.
    _, _, _, id_field = _model_parts(model_name)

    raw = meta.get("neighbors_clip") or []
    if raw:
        if model_name == "clip":
            return [int(i) for i in raw if int(i) >= 0]
        out = []
        for cid in raw:
            nb = _clipid2meta.get(int(cid))
            if nb is None:
                continue
            fid = _fid_of(nb, id_field)          # [siglip2]
            if fid >= 0:
                out.append(fid)
        return out

    frames = _video_frames.get(meta.get("video", ""), [])
    if not frames:
        return []
    try:
        pos = next(i for i, m in enumerate(frames) if m["name"] == meta["name"])
    except StopIteration:
        return []
    lo, hi = max(0, pos - 2), min(len(frames), pos + 3)
    out = [_fid_of(frames[i], id_field) for i in range(lo, hi)]   # [siglip2]
    return [f for f in out if f >= 0]


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

    frames = [m for m in _video_frames.get(video, []) if _fid_of(m, id_field) >= 0]
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
        s = score_frame(_fid_of(m, id_field), q_start)
        if s < sim_thr:
            break
        left.append((m, s))

    # Mở sang phải bằng query_end
    right = []
    for i in range(pos, min(len(frames), pos + max_frames + 1)):
        m = frames[i]
        s = score_frame(_fid_of(m, id_field), q_end)
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

    # Paper Section 3.6.1, Figure 4c ("Boundary Selection"): "Users can review
    # these suggestions and adjust them if necessary to refine the moment
    # boundaries." — trả thêm danh sách ứng viên trái/phải (không chỉ đếm số
    # lượng như trước) để UI dựng được bước review/điều chỉnh này. left/right
    # đã có sẵn đủ dữ liệu từ vòng lặp mở rộng phía trên, chỉ thêm bước đóng
    # gói — KHÔNG đổi thuật toán chọn cặp tốt nhất, KHÔNG bớt field cũ nào.
    def _candidate(m: dict, s: float) -> dict:
        return {
            "name":      m["name"],
            "url":       _image_url(m["name"]),
            "frame_idx": m.get("frame_idx"),
            "timestamp": m.get("timestamp_str", ""),
            "score":     round(s * 100, 2),
        }

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
        "left_candidates":  [_candidate(m, s) for m, s in left],
        "right_candidates": [_candidate(m, s) for m, s in right],
    }


def preload() -> None:
    """Load indexes, metadata and the models named in ACTIVE_MODELS up front.

    All of this is otherwise lazy-loaded on the first request: roughly 16 GB of
    disk reads plus JSON parsing, several minutes in total. On a machine that is
    stopped and started daily, that cost lands on whichever user searches first,
    with no feedback. Calling this from the lifespan hook moves the wait off the
    request path.

    Idempotent: every _load_* helper already checks whether it has run.
    """
    _load_indexes()
    _load_meta()
    for name in ACTIVE_MODELS:
        # [siglip2] Model chưa có index thì ĐỪNG nạp weights. SigLIP2-Giant
        # nặng ~3.5GB: khi index chưa build xong, không có nhánh này thì boot
        # vẫn tải đủ 3.5GB về ngồi không — chậm boot, tốn RAM/VRAM, mà
        # _search_one() vẫn trả [] ngay vì index is None.
        _idx, _, _, _ = _model_parts(name)
        if _idx is None:
            print(f"[preprocess] {name}: chưa có index -> bỏ qua preload weights")
            continue
        if name == "beit3":
            _load_beit3()
        elif name == "clip":
            _load_clip()
        elif name == "siglip2":
            _load_siglip2()


# ─────────────────────────────────────────────────────────────────────────────
#  TRAKE — tổng quát hóa Alg.4 từ 2 điểm (start/end) lên N sự kiện tuần tự.
#  KHÔNG sửa temporal_search() ở trên (2 điểm, giữ nguyên) — đây là hàm MỚI,
#  dùng cho câu hỏi TRAKE (N mốc thời gian trong CÙNG 1 video, theo thứ tự).
#
#  Merge lại sau khi nhánh bạn cùng team tách trước lúc hàm này được thêm —
#  nguyên văn logic cũ, chỉ đổi MODEL_NAMES → ACTIVE_MODELS cho khớp quy ước
#  mới (AIC_MODELS env var, phòng khi CLIP chưa tải xong vẫn chạy được BEiT3).
#
#  Thiết kế theo đúng đề xuất: chấm điểm ĐỘC LẬP từng event lên toàn bộ frame
#  của video (không mở rộng 2 chiều từ 1 anchor như Alg.4 gốc — cách đó chỉ tự
#  nhiên cho đúng 2 điểm), rồi post-processing bằng DP để chọn 1 frame/event
#  sao cho frame_idx tăng dần đúng thứ tự VÀ tổng điểm N frame lớn nhất.
#
#  Complexity: brute-force thử mọi tổ hợp là O(F^N) — bùng nổ tổ hợp với F~vài
#  trăm frame/video, N=4-5 event. DP giảm xuống O(N × F²): dp[i][j] = tổng
#  điểm tốt nhất nếu event i chọn frame j, với ràng buộc có 1 chuỗi frame
#  trước đó (event 0..i-1) đều đứng TRƯỚC frame j về thời gian.
# ─────────────────────────────────────────────────────────────────────────────

def trake_search(queries: list[str], anchor_name: str, gap_c: int = 60,
                 model_name: str = "clip") -> dict:
    """N query tuần tự (E1, E2, ..., EN) → N frame theo đúng thứ tự thời gian
    trong video của anchor, tổng điểm lớn nhất.

    gap_c: khoảng cách tối đa (giây) giữa 2 event LIÊN TIẾP (áp theo từng cặp
    kề nhau trong DP, không phải tổng toàn chuỗi — tránh 1 cặp bị giãn quá xa
    trong khi các cặp khác vẫn hợp lý).
    """
    _load_indexes()
    _load_meta()

    index, _, encode_fn, id_field = _model_parts(model_name)
    if index is None or not _meta:
        return {"error": "Chưa nạp được index hoặc metadata"}

    n = len(queries)
    if n < 2:
        return {"error": "Cần ít nhất 2 query cho TRAKE (nếu chỉ 2, dùng /temporal-search cũng được)"}

    anchor = _name2meta.get(anchor_name)
    if anchor is None:
        return {"error": f"Không tìm thấy keyframe neo {anchor_name} trong metadata"}

    video = anchor.get("video", "")
    fps   = float(anchor.get("fps", 25.0))

    frames = [m for m in _video_frames.get(video, []) if _fid_of(m, id_field) >= 0]
    F = len(frames)
    if F == 0:
        return {"error": f"Video {video} chưa có frame nào được index"}

    # Bước 1 — chấm điểm ĐỘC LẬP từng event lên MỌI frame trong video.
    q_embs = [encode_fn(q).ravel() for q in queries]

    def score_frame(fid: int, q: np.ndarray) -> float:
        """Giống hệt score_frame trong temporal_search() — reconstruct() rồi
        dot product, chính xác tuyệt đối, không xấp xỉ."""
        try:
            vec = index.reconstruct(int(fid)).astype("float32").ravel()
            return float(np.dot(q, vec))
        except Exception:
            return -1.0

    scores = [[score_frame(_fid_of(frames[j], id_field), q_embs[i]) for j in range(F)]
             for i in range(n)]

    # Bước 2 — DP: dp[i][j] = tổng điểm tốt nhất nếu event i chọn frame j.
    NEG = float("-inf")
    dp   = [[NEG] * F for _ in range(n)]
    back = [[-1]  * F for _ in range(n)]
    for j in range(F):
        dp[0][j] = scores[0][j]

    gap_frames = gap_c * fps if gap_c else None

    for i in range(1, n):
        for j in range(F):
            best_prev, best_val = -1, NEG
            for k in range(j):   # k phải đứng TRƯỚC j — đảm bảo frame_idx tăng dần
                if dp[i - 1][k] == NEG:
                    continue
                if gap_frames is not None and \
                   (frames[j]["frame_idx"] - frames[k]["frame_idx"]) > gap_frames:
                    continue
                if dp[i - 1][k] > best_val:
                    best_val, best_prev = dp[i - 1][k], k
            if best_prev >= 0:
                dp[i][j] = best_val + scores[i][j]
                back[i][j] = best_prev

    # Bước 3 — truy vết chuỗi tốt nhất.
    last_j = max(range(F), key=lambda j: dp[n - 1][j])
    if dp[n - 1][last_j] == NEG:
        return {"error": "Không tìm được chuỗi frame hợp lệ theo đúng thứ tự "
                         "trong ràng buộc gap_c — thử tăng gap_c."}

    chosen_idx = [0] * n
    j = last_j
    for i in range(n - 1, -1, -1):
        chosen_idx[i] = j
        j = back[i][j]

    # Candidate list mỗi event — top-10, để UI cho review/đổi (đúng tinh thần
    # Figure 4c "Boundary Selection" đã áp dụng ở temporal_search()).
    def top_candidates(i: int, k: int = 10) -> list[dict]:
        order = sorted(range(F), key=lambda j: -scores[i][j])[:k]
        return [{
            "name": frames[j]["name"], "url": _image_url(frames[j]["name"]),
            "frame_idx": frames[j].get("frame_idx"),
            "timestamp": frames[j].get("timestamp_str", ""),
            "score": round(scores[i][j] * 100, 2),
        } for j in order]

    events = []
    for i in range(n):
        j = chosen_idx[i]
        events.append({
            "name":      frames[j]["name"],
            "url":       _image_url(frames[j]["name"]),
            "frame_idx": frames[j].get("frame_idx"),
            "timestamp": frames[j].get("timestamp_str", ""),
            "score":     round(scores[i][j] * 100, 2),
            "candidates": top_candidates(i),
        })

    return {
        "video":          video,
        "events":         events,
        "combined_score": round(dp[n - 1][last_j] * 100, 2),
    }


# ─────────────────────────────────────────────────────────────────────────────
#  Auto-discovery candidate video — lớp NGOÀI, không đụng temporal_search()/
#  trake_search() ở trên (2 hàm đó vẫn nguyên vẹn, được GỌI LẠI y nguyên bên
#  dưới, không sửa dòng nào bên trong).
#
#  Paper (Sec 3.5) coi anchor là input CHO SẴN: "We assume that the initially
#  retrieved and reranked input frame corresponds to the correct reference
#  frame" — tức là bước chọn anchor vốn là giả định đơn giản hóa của paper,
#  KHÔNG được paper tự động hóa. Phần dưới đây tự động hóa đúng bước đó, dựa
#  trên nhận xét: cả temporal_search() lẫn trake_search() chỉ cần biết ĐÚNG
#  VIDEO (anchor.get("video")/get("fps")) — trake_search() không hề dùng vị
#  trí frame cụ thể của anchor cho việc tính DP, chỉ cần 1 frame bất kỳ thuộc
#  đúng video đó.
# ─────────────────────────────────────────────────────────────────────────────

def _discover_candidate_videos(queries: list[str], model_name: str,
                               top_m: int, min_score: float = 0.10) -> list[dict]:
    """Chạy _search_one() (đã có, dùng chung với ensemble_search) cho TỪNG
    query trong `queries`, group theo video.

    ĐIỂM = TẦN SUẤT (frequency), không phải MAX cosine score qua các query —
    mỗi video được +1 cho MỖI query có ÍT NHẤT 1 frame trong video đó đạt
    điểm >= min_score (ngưỡng dùng chung khái niệm sim_thr đã có ở
    temporal_search()/trake_search()).

    Lý do đổi từ MAX sang frequency: 1 video có thể được xếp hạng cao chỉ vì
    1 query khớp rất mạnh, trong khi các query còn lại hoàn toàn không khớp
    — dấu hiệu cho thấy video đó nhiều khả năng KHÔNG chứa đủ chuỗi sự kiện,
    chỉ tình cờ giống 1 khoảnh khắc. Frequency (bao nhiêu query có match đạt
    ngưỡng) phản ánh đúng "video này có khả năng chứa đủ chuỗi hay không"
    hơn hẳn 1 con số MAX đơn lẻ dễ bị đánh lừa.

    Trả về list [{video, anchor_name, discovery_score, discovery_score_sum}],
    sort giảm dần theo discovery_score (tần suất, số nguyên 0..N), tie-break
    bằng discovery_score_sum (tổng điểm các query đã khớp — video khớp nhiều
    VÀ điểm cao hơn xếp trên video khớp nhiều nhưng điểm sát ngưỡng).
    anchor_name là frame có điểm cao nhất trong số các query đã khớp video đó
    (chỉ cần đúng video khi gọi lại temporal_search()/trake_search(), như đã
    giải thích ở trên).
    """
    video_hits: dict[str, list[dict]] = {}
    for q in queries:
        hits = _search_one(model_name, q, top_m)
        seen_this_query: set[str] = set()
        for h in hits:
            if h["score"] < min_score:
                continue
            v = h["video"]
            if v in seen_this_query:
                continue   # 1 video chỉ tính +1 tần suất / query, dù có nhiều frame khớp
            seen_this_query.add(v)
            video_hits.setdefault(v, []).append(h)

    candidates = []
    for v, hits in video_hits.items():
        best_hit = max(hits, key=lambda h: h["score"])
        candidates.append({
            "video":               v,
            "anchor_name":         best_hit["name"],
            "discovery_score":     len(hits),                       # tần suất — số query đã khớp
            "discovery_score_sum": round(sum(h["score"] for h in hits), 4),  # tie-break
        })

    candidates.sort(key=lambda c: (-c["discovery_score"], -c["discovery_score_sum"]))
    return candidates


# ─────────────────────────────────────────────────────────────────────────────
#  Tách 1 chuỗi query duy nhất (người dùng gõ trong 1 ô, cách nhau bằng dấu
#  chấm) thành list các đoạn — phục vụ UI: khung nhập giữ nguyên 1 ô, không
#  thêm field nào ở frontend.
#
#  Tách theo dấu "." + khoảng trắng theo sau (\.\s+), KHÔNG tách theo mọi dấu
#  "." — để không cắt nhầm số thập phân ("3.5 giây" không có space ngay sau
#  "." nên không bị tách) hay viết tắt liền số ("TP.HCM"). Đánh đổi: viết tắt
#  CÓ space sau dấu chấm ("TP. Hồ Chí Minh") vẫn bị tách nhầm — chấp nhận được
#  vì câu query mô tả cảnh hiếm khi dùng dạng viết tắt này.
# ─────────────────────────────────────────────────────────────────────────────

def _split_query_text(text: str) -> list[str]:
    """'A. B.  C' -> ['A', 'B', 'C'] — trim khoảng trắng, bỏ đoạn rỗng."""
    parts = re.split(r"\.\s+", text.strip())
    return [p.strip().rstrip(".").strip() for p in parts if p.strip()]


def temporal_search_candidates(query_start: str, query_end: str,
                               top_m: int = 50, top_videos: int = 5,
                               gap_c: int = 20, max_frames: int = 20,
                               sim_thr: float = 0.10,
                               model_name: str = "clip") -> list[dict]:
    """Tự động khám phá top_videos video ứng viên (từ query_start + query_end
    gộp lại), rồi gọi temporal_search() ĐÃ CÓ — y nguyên, không đổi — cho MỖI
    video ứng viên. Trả về list kết quả, sort theo combined_score giảm dần.

    Đây là bản KHÔNG CẦN anchor_name thủ công — bổ sung thêm bên cạnh
    temporal_search() (vẫn giữ nguyên, endpoint /temporal-search cũ không đổi
    gì), phục vụ trường hợp muốn tự động hóa thay vì bắt người dùng bấm chọn
    1 frame trước.

    Dùng lại sim_thr (đã có sẵn cho temporal_search() phía dưới) làm min_score
    lúc khám phá video — cùng 1 khái niệm "đủ tốt", không cần thêm tham số
    riêng.
    """
    _load_indexes()
    _load_meta()

    candidates = _discover_candidate_videos([query_start, query_end],
                                            model_name, top_m,
                                            min_score=sim_thr)[:top_videos]
    results = []
    for c in candidates:
        r = temporal_search(query_start, query_end, anchor_name=c["anchor_name"],
                            gap_c=gap_c, max_frames=max_frames, sim_thr=sim_thr,
                            model_name=model_name)
        if "error" not in r:
            # discovery_score = tần suất (bao nhiêu query khớp video này, số
            # nguyên 0..N) — KHÔNG nhân 100 (không còn là cosine score 0..1).
            r["discovery_score"]     = c["discovery_score"]
            r["discovery_score_sum"] = c["discovery_score_sum"]
            results.append(r)

    results.sort(key=lambda r: -(r.get("combined_score") or 0))
    return results


def trake_search_candidates(queries: list[str], top_m: int = 50,
                            top_videos: int = 5, gap_c: int = 60,
                            min_score: float = 0.10,
                            model_name: str = "clip") -> list[dict]:
    """[VIẾT LẠI — đơn giản hóa, thay hoàn toàn cách cũ]

    KHÔNG còn gọi trake_search()/_discover_candidate_videos() — tự chứa toàn
    bộ logic mới, để không đụng 2 hàm đó (trake_search() vẫn dùng cho
    /trake-search thủ công có anchor_name; _discover_candidate_videos() vẫn
    dùng cho temporal_search_candidates()).

    Flow mới, theo đúng ý tưởng đã thống nhất:
      1. N query (đã tách sẵn bởi _split_query_text()) → search ĐỘC LẬP N lần
         bằng ensemble_search() ĐẦY ĐỦ (Alg.2 rerank + Alg.3 ensemble BEiT3+
         CLIP) trên TOÀN BỘ index — không giới hạn 1 video.
      2. Đếm TẦN SUẤT: video nào xuất hiện trong kết quả của bao nhiêu trong
         N lần search đó. Lọc lấy top_videos video tần suất cao nhất.
      3. Encode N câu query CHỈ 1 LẦN (single model, đúng tham số model_name
         hiện có) — dùng lại cho MỌI video ứng viên. Bản cũ encode lại N câu
         này mỗi lần gọi trake_search() cho từng video (N × top_videos lần
         encode) — đây mới là nguồn chậm thật sự (encode chạy CPU), không
         phải độ phức tạp DP (DP chỉ là numpy thuần, rẻ).
      4. Với MỖI video ứng viên: chấm điểm N query lên mọi frame video đó,
         chọn theo GREEDY TUẦN TỰ — mỗi event chọn frame điểm cao nhất trong
         số frame ĐỨNG SAU frame đã chọn của event trước (trong gap_c) —
         O(N×F)/video, không phải O(N×F²) như DP cũ.

    LƯU Ý — 1 điều chỉnh so với đề xuất "chọn độc lập, không ràng buộc thứ
    tự": rủi ro thật với hành động lặp lại (nấu ăn lặp thao tác, đua xe lặp
    vòng — phổ biến ở TRAKE) là event sau vô tình chọn trúng frame đứng
    TRƯỚC event trước về thời gian → sai bản chất TRAKE (yêu cầu đúng thứ
    tự). Greedy tuần tự vẫn O(N×F) — gần như y hệt chi phí ý tưởng gốc, chỉ
    thêm 1 điều kiện lọc — nhưng đảm bảo đúng thứ tự.

    Response format GIỮ NGUYÊN 100% — UI không cần đổi gì:
      [{"video", "events": [{"name","url","frame_idx","timestamp","score",
        "candidates"}, ...], "combined_score", "discovery_score",
        "discovery_score_sum"}, ...]
    """
    _load_indexes()
    _load_meta()

    n = len(queries)
    if n < 2:
        return []

    # ── Bước 1+2: discovery bằng ensemble_search() thật + đếm tần suất video ──
    video_hits: dict[str, list[dict]] = {}
    for q in queries:
        hits = ensemble_search(q, top_k=top_m, use_rerank=True)
        seen_this_query: set[str] = set()
        for h in hits:
            v = h.get("video")
            if not v or v in seen_this_query:
                continue
            seen_this_query.add(v)
            video_hits.setdefault(v, []).append(h)

    ranked_videos = sorted(
        video_hits.items(),
        key=lambda kv: (-len(kv[1]), -sum(h["distance"] for h in kv[1])),
    )[:top_videos]
    if not ranked_videos:
        return []

    # ── Bước 3: encode N query CHỈ 1 LẦN, dùng lại cho mọi video ────────────
    index, _, encode_fn, id_field = _model_parts(model_name)
    if index is None or not _meta:
        return []
    q_embs = [encode_fn(q).ravel() for q in queries]

    def score_frame(fid: int, q: np.ndarray) -> float:
        """Giống hệt score_frame trong trake_search()/temporal_search() —
        reconstruct() rồi dot product, chính xác tuyệt đối."""
        try:
            vec = index.reconstruct(int(fid)).astype("float32").ravel()
            return float(np.dot(q, vec))
        except Exception:
            return -1.0

    results = []
    for video, hits in ranked_videos:
        frames = [m for m in _video_frames.get(video, [])
                 if _fid_of(m, id_field) >= 0]
        F = len(frames)
        if F == 0:
            continue

        scores = [[score_frame(_fid_of(frames[j], id_field), q_embs[i]) for j in range(F)]
                 for i in range(n)]

        fps = float(frames[0].get("fps", 25.0))
        gap_frames = gap_c * fps if gap_c else None

        # ── Bước 4: GREEDY TUẦN TỰ — mỗi event chọn max trong số frame đứng
        # SAU frame đã chọn của event trước (và trong gap_c) ────────────────
        chosen_idx: list[int] = []
        lower = -1
        ok = True
        for i in range(n):
            best_j, best_s = -1, float("-inf")
            for j in range(F):
                if j <= lower:
                    continue
                if gap_frames is not None and chosen_idx:
                    prev_fi = frames[chosen_idx[-1]]["frame_idx"]
                    if (frames[j]["frame_idx"] - prev_fi) > gap_frames:
                        continue
                if scores[i][j] > best_s:
                    best_s, best_j = scores[i][j], j
            if best_j < 0:
                ok = False
                break
            chosen_idx.append(best_j)
            lower = best_j
        if not ok:
            continue

        # Candidate list mỗi event — top-10, để UI review/đổi (Figure 4c),
        # y nguyên logic top_candidates() cũ trong trake_search().
        def top_candidates(i: int, k: int = 10) -> list[dict]:
            order = sorted(range(F), key=lambda j: -scores[i][j])[:k]
            return [{
                "name": frames[j]["name"], "url": _image_url(frames[j]["name"]),
                "frame_idx": frames[j].get("frame_idx"),
                "timestamp": frames[j].get("timestamp_str", ""),
                "score": round(scores[i][j] * 100, 2),
            } for j in order]

        events = []
        for i in range(n):
            j = chosen_idx[i]
            events.append({
                "name":      frames[j]["name"],
                "url":       _image_url(frames[j]["name"]),
                "frame_idx": frames[j].get("frame_idx"),
                "timestamp": frames[j].get("timestamp_str", ""),
                "score":     round(scores[i][j] * 100, 2),
                "candidates": top_candidates(i),
            })

        results.append({
            "video":               video,
            "events":              events,
            "combined_score":      round(
                sum(scores[i][chosen_idx[i]] for i in range(n)) * 100, 2),
            "discovery_score":     len(hits),
            "discovery_score_sum": round(sum(h["distance"] for h in hits), 4),
        })

    results.sort(key=lambda r: -(r.get("combined_score") or 0))
    return results


# ─────────────────────────────────────────────────────────────────────────────
#  Bản "1 ô nhập" — tách chuỗi rồi GỌI LẠI temporal_search_candidates()/
#  trake_search_candidates() Ở TRÊN, KHÔNG ĐỔI GÌ bên trong 2 hàm đó. Phục vụ
#  UI: người dùng gõ "A. B" (temporal) hoặc "A. B. C. D" (trake) trong 1 ô
#  input duy nhất, không cần thêm field nào ở frontend.
# ─────────────────────────────────────────────────────────────────────────────

def temporal_search_text(query: str, **kwargs) -> dict:
    """Tách `query` thành đúng 2 đoạn (start, end) rồi gọi
    temporal_search_candidates() y nguyên. Lỗi rõ ràng nếu không tách được
    đúng 2 đoạn — không đoán/tự ghép nếu thiếu."""
    parts = _split_query_text(query)
    if len(parts) != 2:
        return {"error": f"Cần đúng 2 đoạn cách nhau bằng dấu '.' cho temporal "
                         f"search (start. end) — tách được {len(parts)} đoạn: {parts}"}
    return {"results": temporal_search_candidates(parts[0], parts[1], **kwargs)}


def trake_search_text(query: str, **kwargs) -> dict:
    """Tách `query` thành N đoạn (N>=2) rồi gọi trake_search_candidates() y
    nguyên. Lỗi rõ ràng nếu tách được ít hơn 2 đoạn."""
    parts = _split_query_text(query)
    if len(parts) < 2:
        return {"error": f"Cần ít nhất 2 đoạn cách nhau bằng dấu '.' cho TRAKE "
                         f"— tách được {len(parts)} đoạn: {parts}"}
    return {"results": trake_search_candidates(parts, **kwargs)}


def system_status() -> dict:
    """Tình trạng từng thành phần — dùng cho /status, để biết còn thiếu gì."""
    _load_indexes()
    _load_meta()
    # How many images are actually on disk, which explains has_image=false runs.
    # Meaningless once images live in an external store, so skip the scan.
    if IMAGES_REMOTE:
        n_images = None
    else:
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
        "images_remote":   IMAGES_REMOTE,
        "json_parser":     "orjson" if _orjson is not None else "json",
        "pipeline_order":  "search → rerank (per-model) → ensemble",
        "active_models":   list(ACTIVE_MODELS),
        "images_on_disk":  n_images,
        "files": {name: os.path.exists(path) for name, path in INDEX_SET_FILES},
        "vectors": {
            "beit3": _beit3_index.ntotal if _beit3_index is not None else 0,
            "clip":  _clip_index.ntotal  if _clip_index  is not None else 0,
            # [siglip2] 0 = chưa có index. Frontend đọc đúng số này để quyết
            # định có cho tick checkbox SigLIP2 hay không.
            "siglip2": _siglip2_index.ntotal if _siglip2_index is not None else 0,
        },
        # Which build of the index set this process is actually serving, and
        # whether the files underneath it have moved since. `stale_files` being
        # non-empty means the disk was updated but the container was not
        # restarted, so the answers still come from the previous index set.
        "index_files": {
            name: {"loaded": _index_loaded.get(name), "on_disk": _file_identity(path)}
            for name, path in INDEX_SET_FILES
        },
        "stale_files": sorted(
            name for name, path in INDEX_SET_FILES
            if _index_loaded.get(name) is not None
            and _index_loaded.get(name) != _file_identity(path)
        ),
        "keyframes": len(_meta),
        "videos":    len(_video_frames),
        "relpath_map": len(_name2relpath),
        "models": {
            "fine_grained":   f"BEiT3-Large coco_retrieval 1024-dim "
                              f"({'loaded' if _beit3_model else 'lazy'})",
            "coarse_grained": f"OpenCLIP {CLIP_MODEL_NAME} 1280-dim "
                              f"({'loaded' if _clip_model else 'lazy'})",
            "siglip2":        f"SigLIP2-Giant {SIGLIP2_DIM}-dim "
                              f"({'loaded' if _siglip2_model else 'lazy'})",
        },
        "ensemble_weights": ENSEMBLE_WEIGHTS,
    }