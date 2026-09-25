# -*- coding: utf-8 -*-
"""
track_search.py — tìm keyframe bằng CÁCH VẬT DI CHUYỂN
========================================================

Route riêng lẻ trên dữ liệu track đã tính sẵn (IoU tracking giữa các keyframe
giám sát giao thông N-series, batch 2): mỗi track là MỘT vật thể thật quan sát
trên nhiều keyframe — xe hơi xám đi sang trái, xe tải đỏ chạy nhanh về phía
camera — kèm màu trích từ vùng box.

Vì sao tách khỏi route thị giác (giống ocr_search)
--------------------------------------------------
CLIP/BEiT3 mã hoá "một chiếc xe tải đỏ" khá tốt, nhưng KHÔNG mã hoá được
"đang sang trái", "đang dừng", "chạy nhanh" — chuyển động nằm NGOÀI ảnh
đơn lẻ. Track là nơi duy nhất giữ thông tin đó, nên tách hẳn một route thay
vì trộn điểm vào ensemble (trộn sẽ làm loãng đúng cái nó giỏi).

Vì sao scan tuyến tính
-----------------------
64.439 track, mỗi lần lọc là một vòng for thuần Python:
  load 26MB jsonl   ~0.4 s (một lần, lúc khởi động)
  lọc 1 truy vấn     ~5-15 ms
Đủ nhanh, không cần inverted index.

File nằm cạnh FAISS index (AIC_INDEX_DIR), không qua git — cùng đường deploy
`aws s3 sync` + ssm-sync-indexes.sh như ocr_clean.json. Xem ghi chú dài ở
ocr_search.py vì sao bám biến này.
"""

import json
import os
import re
import time
import unicodedata
from typing import Optional

TRACKS_DIR = os.environ.get("AIC_TRACK_DIR") or os.environ.get(
    "AIC_INDEX_DIR",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "indexes"))
# Chỉ N-series: camera tĩnh quay liên tục — điều kiện IoU tracking giả định.
# S-series đã loại (ảnh đua xe cắt cảnh liên tục, track vô nghĩa);
# M-series (tin tức, cũng cắt cảnh) CHƯA bật — đừng thêm cho đến khi có lọc shot.
TRACK_FILES = ["tracks_N.jsonl"]

# ── Từ vựng truy vấn (tiếng Việt + tiếng Anh, so khớp sau khi bỏ dấu) ──
# Nhóm theo ý; từ khoá multi-word khớp cả cụm. \b giữ "cam" không bám vào
# "camera", "đen" không bám vào "denbuon".
ENTITY_KEYWORDS = {
    "car":        ["ô tô", "oto", "xe hơi", "xe hoi", "xe con", "car"],
    "truck":      ["xe tải", "xe tai", "truck", "container", "xe cont"],
    "bus":        ["xe buýt", "xe buyt", "bus", "xe khách", "xe khach"],
    "van":        ["van", "xe van"],
    "motorcycle": ["xe máy", "xe may", "mô tô", "mo to", "motorcycle",
                    "motorbike", "moto"],
    "bicycle":    ["xe đạp", "xe dap", "bicycle", "bike"],
    "taxi":       ["taxi"],
    "person":     ["người", "nguoi", "person", "pedestrian",
                    "người đi bộ", "nguoi di bo"],
}
COLOR_KEYWORDS = {
    "red":    ["đỏ", "do", "red"],
    "blue":   ["xanh dương", "xanh duong", "blue", "xanh biển"],
    "green":  ["xanh lá", "xanh la", "green", "xanh lục"],
    "yellow": ["vàng", "vang", "yellow"],
    "white":  ["trắng", "trang", "white"],
    "black":  ["đen", "black"],
    "gray":   ["xám", "xam", "gray", "grey"],
    "silver": ["bạc", "bac", "silver"],
    "brown":  ["nâu", "nau", "brown"],
    "purple": ["tím", "tim", "purple"],
    "orange": ["cam", "orange"],
    "pink":   ["hồng", "hong", "pink"],
}
DIRECTION_KEYWORDS = {
    "left":       ["trái", "trai", "left", "sang trái"],
    "right":      ["phải", "phai", "right", "sang phải"],
    "toward":     ["lại gần", "lai gan", "toward", "về phía camera",
                    "ve phia camera"],
    "away":       ["xa dần", "xa dan", "away", "đi xa", "di xa"],
    "up":         ["lên", "len", "up", "đi lên"],
    "down":       ["xuống", "xuong", "down", "đi xuống"],
    # KHÔNG chứa "đỗ"/"đậu" đơn lẻ: bỏ dấu ra thành "do"/"dau" đụng "đỏ"
    # (màu) và "dau" — chấm nhau ảo, đã cắn 5 test một lúc.
    "stationary": ["đứng yên", "dung yen", "dừng lại", "dung lai",
                    "stationary", "stopped", "đang đỗ", "dang do",
                    "đang đậu", "dang dau"],
}
SPEED_KEYWORDS = {
    "fast":       ["nhanh", "fast"],
    "slow":       ["chậm", "cham", "slow"],
    "stationary": ["đứng yên", "dung yen", "dừng lại", "dung lai",
                    "stationary", "stopped", "đang đỗ", "dang do",
                    "đang đậu", "dang dau"],
}

_tracks: list[dict] = []
_loaded = False
_load_info: dict = {}


def _strip_marks(text: str) -> str:
    """Bỏ dấu tiếng Việt — áp cho CẢ query lẫn từ khoá nên hai phía lệch nhau
    thì vẫn khớp (người gõ "xe may", dữ liệu "xe máy")."""
    text = unicodedata.normalize("NFD", text).replace("đ", "d").replace("Đ", "D")
    return "".join(c for c in text if unicodedata.category(c) != "Mn")


def _kw_regex(keywords: list[str]) -> re.Pattern:
    """Pattern khớp từ khoá như TỪ HOÀN CHỈNH trong chuỗi đã bỏ dấu."""
    parts = sorted((_strip_marks(k).lower() for k in keywords), key=len, reverse=True)
    return re.compile(r"\b(?:" + "|".join(re.escape(p) for p in parts) + r")\b")


_ENTITY_RE = {g: _kw_regex(kws) for g, kws in ENTITY_KEYWORDS.items()}
_COLOR_RE = {c: _kw_regex(kws) for c, kws in COLOR_KEYWORDS.items()}
_DIRECTION_RE = {d: _kw_regex(kws) for d, kws in DIRECTION_KEYWORDS.items()}
_SPEED_RE = {s: _kw_regex(kws) for s, kws in SPEED_KEYWORDS.items()}


def _load() -> None:
    """Đọc các file jsonl track vào bộ nhớ. Gọi nhiều lần vẫn chỉ load một lần."""
    global _loaded
    if _loaded:
        return
    started = time.time()
    missing = [f for f in TRACK_FILES if not os.path.exists(os.path.join(TRACKS_DIR, f))]
    if missing:
        raise FileNotFoundError(
            "Thiếu file track: " + ", ".join(missing)
            + f" tại {TRACKS_DIR} — copy từ gdrive:annv-batch_2-extract/"
              "tracks_v001/ vào cùng thư mục FAISS index (xem docs/"
              "huong-dan-cap-nhat-index.md), hoặc đặt AIC_TRACK_DIR.")
    _tracks.clear()
    for fname in TRACK_FILES:
        with open(os.path.join(TRACKS_DIR, fname), encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    _tracks.append(json.loads(line))
    _loaded = True
    _load_info.update({
        "total_tracks": len(_tracks),
        "files": list(TRACK_FILES),
        "load_seconds": round(time.time() - started, 2),
        "path": TRACKS_DIR,
    })
    print(f"[track_search] {_load_info['total_tracks']:,} track · "
          f"loaded in {_load_info['load_seconds']}s")


def parse_query(query: str) -> dict:
    """Rút các bộ lọc ra khỏi câu truy vấn tự nhiên.

    Trả về {"groups": [...], "colors": [...], "directions": [...],
    "speeds": [...]} — mỗi loại là OR trong nội bộ (ô tô HOẶC xe máy),
    các loại kết hợp AND với nhau. Câu không chứa yếu tố nào nhận ra được
    thì raise ValueError để endpoint trả 400 kèm gợi ý.
    """
    q = _strip_marks(query).lower()
    if not q.strip():
        raise ValueError("Câu truy vấn rỗng.")
    parsed = {}
    for name, table in (("groups", _ENTITY_RE), ("colors", _COLOR_RE),
                        ("directions", _DIRECTION_RE), ("speeds", _SPEED_RE)):
        hits = [k for k, rx in table.items() if rx.search(q)]
        if hits:
            parsed[name] = hits
    # "xanh" trơ trọi là lưỡng nghĩa (dương/lá): không khớp cụ thể nào thì
    # nới ra cho cả hai xanh, kẻo mất toàn bộ xe màu xanh vì người gõ thiếu chữ.
    if "colors" not in parsed and re.search(r"\bxanh\b", q):
        parsed["colors"] = ["blue", "green"]
    if not parsed:
        raise ValueError(
            "Không nhận ra yếu tố nào. Route này lọc theo: đối tượng "
            "(ô tô/xe tải/xe buýt/xe máy/xe đạp/người...), màu (đỏ/xanh/"
            "trắng/đen...), hướng (trái/phải/lại gần/xa dần...), tốc độ "
            "(nhanh/chậm/đứng yên...).")
    return parsed


def search(query: str, limit: int = 100, video: Optional[str] = None) -> dict:
    """Lọc track theo các yếu tố trong câu, trả keyframe rõ nhất mỗi track.

    Thứ hạng chỉ phụ thuộc dữ liệu track, không có model nào tham gia:
      1. best_score — độ tin cậy detector của lần quan sát rõ nhất
      2. cộng thưởng theo độ dài track (nhiều frame = chắc chắn vật thật,
         không phải phát hiện rời rạc một lần)
    Mỗi track chỉ trả MỘT dòng — keyframe best_frame, đúng frame người
    xem muốn thấy vật thể.
    """
    parsed = parse_query(query)
    _load()
    started = time.time()

    groups = set(parsed.get("groups", []))
    colors = set(parsed.get("colors", []))
    directions = set(parsed.get("directions", []))
    speeds = set(parsed.get("speeds", []))

    scored = []
    for t in _tracks:
        if video and not t["video"].startswith(video):
            continue
        if groups and t["group"] not in groups:
            continue
        # Màu chưa trích được (None) bị loại khi truy vấn hỏi màu — không
        # giả định "không màu" là khớp. "dark_gray" của extract_colors không
        # có từ khoá riêng: gộp vào gray khi so (hiển thị giữ nguyên).
        if colors:
            tcolor = t.get("color")
            if tcolor == "dark_gray":
                tcolor = "gray"
            if tcolor not in colors:
                continue
        if directions and t["direction"] not in directions:
            continue
        if speeds and t["speed"] not in speeds:
            continue
        # Thứ hạng: độ tin cậy detector của frame được chọn, NHÂN với độ nhìn
        # thấy rõ của vật thể trong frame đó. Bài học N044-V002: vật lết mép
        # khung ảnh có conf cao nhất đúng lúc bị cắt nhiều nhất — hiện frame đó
        # đứng hạng 1 khiến người vận hành bác kết quả ĐÚNG. Ưu tiên vật nhìn
        # thấy trọn vẹn; cộng thưởng nhỏ theo độ dài track như cũ.
        margin = t.get("visibility", 1.0)
        score = t["best_score"] * (0.3 + 0.7 * margin) \
            + 0.005 * min(t["n_obs"], 20)
        scored.append((score, t))
    # Điểm giảm dần, rồi theo video/track_id để cùng một truy vấn luôn
    # trả cùng một thứ tự (lý do như ocr_search).
    scored.sort(key=lambda s: (-s[0], s[1]["video"], s[1]["track_id"]))

    rows = []
    for rank, (score, t) in enumerate(scored[:limit], 1):
        name = f"{t['video']}-{t['best_frame']:05d}.jpg"
        rows.append({
            "name": name,
            "score": round(score, 4),
            "rank": rank,
            "entity": t["entity"],
            "group": t["group"],
            "color": t.get("color"),
            "direction": t["direction"],
            "speed": t["speed"],
            "visibility": t.get("visibility"),
            "n_obs": t["n_obs"],
            "frame_start": t["frame_start"],
            "frame_end": t["frame_end"],
            "video": t["video"],
            "track_id": t["track_id"],
        })

    return {
        "results": rows,
        "parsed": parsed,
        "total_matches": len(scored),
        "searched_tracks": len(_tracks),
        "processing_time": round(time.time() - started, 4),
    }


def status() -> dict:
    """Báo /status route này sẵn sàng hay chưa, không để nó làm gãy endpoint."""
    present = all(os.path.exists(os.path.join(TRACKS_DIR, f)) for f in TRACK_FILES)
    out = {"ready": bool(_loaded), "files_present": present, "path": TRACKS_DIR}
    out.update(_load_info)
    return out


def preload() -> None:
    """Nạp lúc khởi động để người tìm đầu tiên không đợi 0.4s. Nuốt lỗi như
    ocr_search: thiếu file không được làm chết server."""
    try:
        _load()
    except Exception as e:
        print(f"[track_search] not loaded ({e}) — /track-search will report the error")
