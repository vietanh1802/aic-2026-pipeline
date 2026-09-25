# -*- coding: utf-8 -*-
"""Test track_search: parse từ khoá VN/EN + lọc + xếp hạng track."""
import json

import pytest

from app import track_search as ts


@pytest.fixture()
def tracks_file(tmp_path, monkeypatch):
    """6 track nhỏ phủ đủ các nhánh lọc: group, color, direction, speed."""
    rows = [
        # xe tải đỏ, đi trái, chậm — candidate cho "xe tải đỏ sang trái"
        {"video": "N001-V001", "track_id": 0, "entity": "Truck", "group": "truck",
         "n_obs": 10, "frame_start": 5, "frame_end": 18, "direction": "left",
         "speed": "slow", "color": "red", "best_frame": 9,
         "best_box": [0.1, 0.1, 0.2, 0.2], "best_score": 0.9,
         "dx": -0.1, "dy": 0.0, "path_len": 0.1, "area_ratio": 1.0},
        # xe máy xám, đi phải, nhanh
        {"video": "N001-V001", "track_id": 1, "entity": "Motorcycle", "group": "motorcycle",
         "n_obs": 4, "frame_start": 100, "frame_end": 110, "direction": "right",
         "speed": "fast", "color": "gray", "best_frame": 104,
         "best_box": [0.5, 0.5, 0.6, 0.6], "best_score": 0.7,
         "dx": 0.2, "dy": 0.0, "path_len": 0.2, "area_ratio": 1.0},
        # người, không màu, đứng yên
        {"video": "N002-V001", "track_id": 2, "entity": "Person", "group": "person",
         "n_obs": 20, "frame_start": 1, "frame_end": 22, "direction": "stationary",
         "speed": "stationary", "color": None, "best_frame": 2,
         "best_box": [0.0, 0.0, 0.1, 0.1], "best_score": 0.8,
         "dx": 0.0, "dy": 0.0, "path_len": 0.01, "area_ratio": 1.0},
        # xe hơi trắng, lại gần camera
        {"video": "N002-V001", "track_id": 3, "entity": "Car", "group": "car",
         "n_obs": 8, "frame_start": 50, "frame_end": 60, "direction": "toward",
         "speed": "slow", "color": "white", "best_frame": 55,
         "best_box": [0.3, 0.3, 0.4, 0.4], "best_score": 0.85,
         "dx": 0.0, "dy": 0.05, "path_len": 0.05, "area_ratio": 1.5},
        # xe đạp xanh (blue)
        {"video": "N003-V001", "track_id": 4, "entity": "Bicycle", "group": "bicycle",
         "n_obs": 6, "frame_start": 7, "frame_end": 14, "direction": "left",
         "speed": "slow", "color": "blue", "best_frame": 10,
         "best_box": [0.7, 0.7, 0.8, 0.8], "best_score": 0.6,
         "dx": -0.05, "dy": 0.0, "path_len": 0.05, "area_ratio": 1.0},
        # xe hơi đỏ khác video — kiểm tra lọc video prefix
        {"video": "N003-V002", "track_id": 5, "entity": "Car", "group": "car",
         "n_obs": 5, "frame_start": 30, "frame_end": 36, "direction": "right",
         "speed": "fast", "color": "red", "best_frame": 33,
         "best_box": [0.2, 0.2, 0.3, 0.3], "best_score": 0.75,
         "dx": 0.1, "dy": 0.0, "path_len": 0.1, "area_ratio": 1.0},
        # xe tải dark_gray (giá trị thật của extract_colors) — truy vấn
        # "xám" phải khớp được
        {"video": "N004-V001", "track_id": 6, "entity": "Truck", "group": "truck",
         "n_obs": 7, "frame_start": 40, "frame_end": 50, "direction": "right",
         "speed": "slow", "color": "dark_gray", "best_frame": 45,
         "best_box": [0.4, 0.4, 0.5, 0.5], "best_score": 0.8,
         "dx": 0.1, "dy": 0.0, "path_len": 0.1, "area_ratio": 1.0},
    ]
    path = tmp_path / "tracks_N.jsonl"
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    monkeypatch.setattr(ts, "TRACKS_DIR", str(tmp_path))
    monkeypatch.setattr(ts, "_loaded", False)
    ts._tracks.clear()
    return path


# ── parse_query ─────────────────────────────────────────────────────────────

def test_parse_vietnamese_full(tracks_file):
    parsed = ts.parse_query("xe tải màu đỏ đang chạy sang trái")
    assert parsed["groups"] == ["truck"]
    assert parsed["colors"] == ["red"]
    assert parsed["directions"] == ["left"]


def test_parse_english(tracks_file):
    parsed = ts.parse_query("a red truck moving left fast")
    assert parsed["groups"] == ["truck"]
    assert parsed["colors"] == ["red"]
    assert parsed["directions"] == ["left"]
    assert parsed["speeds"] == ["fast"]


def test_parse_no_diacritics(tracks_file):
    """Người gõ không dấu vẫn phải khớp từ khoá có dấu."""
    parsed = ts.parse_query("xe may do chay sang trai")
    assert parsed["groups"] == ["motorcycle"]
    assert "red" in parsed["colors"]
    assert parsed["directions"] == ["left"]


def test_parse_xanh_alone_is_both_blues(tracks_file):
    """"xanh" trơ trọi phải nới ra cả blue lẫn green, không phải rỗng."""
    parsed = ts.parse_query("một chiếc xe màu xanh")
    assert parsed["colors"] == ["blue", "green"]


def test_parse_camera_is_not_orange(tracks_file):
    """"cam" trong "camera" không được tính là màu cam."""
    parsed = ts.parse_query("người đứng trước camera giám sát")
    assert "colors" not in parsed
    assert parsed["groups"] == ["person"]


def test_parse_unrecognized_raises(tracks_file):
    with pytest.raises(ValueError):
        ts.parse_query("một khung cảnh đẹp tuyệt vời")


def test_parse_stationary(tracks_file):
    parsed = ts.parse_query("người đứng yên trên vỉa hè")
    assert parsed["groups"] == ["person"]
    assert "stationary" in parsed.get("speeds", [])
    assert "stationary" in parsed.get("directions", [])


# ── search ──────────────────────────────────────────────────────────────────

def test_search_filters_and_ranks(tracks_file):
    out = ts.search("xe tải màu đỏ sang trái")
    assert out["total_matches"] == 1
    row = out["results"][0]
    assert row["video"] == "N001-V001"
    assert row["name"] == "N001-V001-00009.jpg"
    assert row["entity"] == "Truck"
    assert row["color"] == "red"


def test_search_entity_or_semantics(tracks_file):
    """Hai nhóm trong câu là OR: 'xe hơi hoặc xe máy' phải ra cả hai."""
    out = ts.search("xe hơi hoặc xe máy")
    groups = {r["group"] for r in out["results"]}
    assert groups == {"car", "motorcycle"}


def test_search_color_excludes_none(tracks_file):
    """Track không có màu (color=None) bị loại khi truy vấn hỏi màu."""
    out = ts.search("người màu trắng")
    # person duy nhất có color=None -> không khớp
    assert out["total_matches"] == 0


def test_search_color_no_color_query_keeps_none(tracks_file):
    """Không hỏi màu thì track màu None vẫn ra."""
    out = ts.search("người đang đứng yên")
    assert out["total_matches"] == 1
    assert out["results"][0]["entity"] == "Person"


def test_search_video_prefix_filter(tracks_file):
    out = ts.search("xe hơi đỏ", video="N003")
    assert out["total_matches"] == 1
    assert out["results"][0]["video"] == "N003-V002"


def test_search_rank_prefers_score_then_track_length(tracks_file):
    """best_score cao hơn phải xếp trên; độ dài track là cộng thưởng nhỏ."""
    out = ts.search("xe hơi")  # car tracks: N002-V001 (0.85+0.04), N003-V002 (0.75+0.025)
    assert out["results"][0]["video"] == "N002-V001"
    assert out["results"][1]["video"] == "N003-V002"


def test_search_deterministic_order(tracks_file):
    a = ts.search("xe hơi")
    b = ts.search("xe hơi")
    assert [r["name"] for r in a["results"]] == [r["name"] for r in b["results"]]


def test_search_dark_gray_matches_gray_query(tracks_file):
    """extract_colors trả cả 'dark_gray' — truy vấn 'xám' phải bắt được,
    không có từ khoá riêng cho nó."""
    out = ts.search("xe tải xám")
    videos = {r["video"] for r in out["results"]}
    assert "N004-V001" in videos


def test_search_parsed_echo(tracks_file):
    out = ts.search("xe buýt trắng")
    assert out["parsed"]["groups"] == ["bus"]
    assert out["parsed"]["colors"] == ["white"]


# ── status / preload ────────────────────────────────────────────────────────

def test_preload_swallows_missing_files(tmp_path, monkeypatch):
    monkeypatch.setattr(ts, "TRACKS_DIR", str(tmp_path))
    monkeypatch.setattr(ts, "_loaded", False)
    ts._tracks.clear()
    ts.preload()  # không raise dù thư mục rỗng
    assert ts.status()["ready"] is False
