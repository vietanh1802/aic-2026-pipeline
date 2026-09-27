# -*- coding: utf-8 -*-
"""Focused tests for scripts/build_asr_text_index.py (Phase 1 of the ASR+OCR
text-filter plan). Run with: python -m pytest scripts/tests/ from repo root."""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import build_asr_text_index as m


# ── URL / filename parsing ──────────────────────────────────────────────

def test_parse_real_mapping_url() :
    url = "http://localhost:8000/static/images/L25_V001-0001-118.jpg"
    assert m.basename_from_mapping_url(url) == "L25_V001-0001-118.jpg"


def test_extract_basename_from_url() :
    url = "http://localhost:8000/static/images/L26_V194-0012-004707.jpg"
    assert m.basename_from_mapping_url(url) == "L26_V194-0012-004707.jpg"


def test_basename_from_url_rejects_urls_with_no_path() :
    assert m.basename_from_mapping_url("not-a-url-at-all") is None


def test_parse_frame_name_extracts_video_id() :
    video_id, frame_idx = m.parse_frame_name("L24_V010-0031-8228.jpg")
    assert video_id == "L24_V010"


def test_parse_frame_name_extracts_final_frame_index() :
    # "0031" is a scene id, not a frame number -- 8228 (the LAST "-"-separated
    # numeric component) is the frame index, per backend/app/main.py's own
    # _frame_idx_from_name() convention that this script mirrors.
    video_id, frame_idx = m.parse_frame_name("L24_V010-0031-8228.jpg")
    assert frame_idx == 8228


def test_parse_frame_name_malformed_returns_none() :
    assert m.parse_frame_name("not_a_valid_name.jpg") is None
    assert m.parse_frame_name("L24_V010-0031-abc.jpg") is None
    assert m.parse_frame_name("noimagehere") is None


def test_frame_timestamp_seconds() :
    assert m.frame_timestamp_seconds(1234, 25.0) == 1234 / 25.0


# ── window matching ──────────────────────────────────────────────────────

def _window(start : float, end : float, text : str) -> m.WindowRecord :
    return m.WindowRecord(video_id="V1", start_s=start, end_s=end, retrieval_text=text)


def test_exact_overlap_no_padding() :
    windows = [_window(0.0, 60.0, "a"), _window(100.0, 160.0, "b")]
    starts, ends = m.padded_arrays(windows, padding=0.0)
    assert [w.retrieval_text for w in m.match_windows(30.0, windows, starts, ends)] == ["a"]
    assert m.match_windows(80.0, windows, starts, ends) == []  # in the gap between windows


def test_padded_overlap_catches_frame_just_outside_window() :
    windows = [_window(10.0, 60.0, "a")]
    starts, ends = m.padded_arrays(windows, padding=5.0)
    # 8.0s is before the window (10.0) but within the 5s padding tolerance
    assert [w.retrieval_text for w in m.match_windows(8.0, windows, starts, ends)] == ["a"]
    # 3.0s is outside even the padded range
    assert m.match_windows(3.0, windows, starts, ends) == []


def test_multiple_overlapping_windows_returned_chronologically() :
    windows = [_window(0.0, 60.0, "first"), _window(45.0, 105.0, "second")]
    starts, ends = m.padded_arrays(windows, padding=0.0)
    hits = m.match_windows(50.0, windows, starts, ends)
    assert [w.retrieval_text for w in hits] == ["first", "second"]


def test_frame_with_no_matching_window_yields_empty_text() :
    windows = [_window(0.0, 60.0, "a")]
    starts, ends = m.padded_arrays(windows, padding=0.0)
    hits = m.match_windows(500.0, windows, starts, ends)
    assert hits == []
    assert m.dedupe_concat([w.retrieval_text for w in hits]) == ""


# ── dedup / concatenation ────────────────────────────────────────────────

def test_dedupe_concat_removes_exact_duplicates_keeps_first_order() :
    assert m.dedupe_concat(["hello", "world", "hello"]) == "hello world"


def test_dedupe_concat_skips_empty_and_none() :
    assert m.dedupe_concat(["", None, "  ", "text"]) == "text"


# ── build_index: missing FPS / malformed mapping / CLIP-BEiT3 union ──────

def _write_json(path, obj) :
    with open(path, "w", encoding="utf-8") as f :
        json.dump(obj, f)


def _write_jsonl(path, rows) :
    with open(path, "w", encoding="utf-8") as f :
        for row in rows :
            f.write(json.dumps(row) + "\n")


def test_build_index_skips_frames_with_missing_fps(tmp_path) :
    windows_path, fps_path = tmp_path / "windows.jsonl", tmp_path / "fps_map.json"
    clip_path, beit3_path = tmp_path / "clip_mapping.json", tmp_path / "beit3_mapping.json"

    _write_jsonl(windows_path, [
        {"video_id" : "V1", "sample_start" : 0, "sample_end" : 960000, "sample_rate" : 16000,
         "eligible" : True, "retrieval_text" : "hello"},
    ])
    _write_json(fps_path, {})  # V1 deliberately missing
    _write_json(clip_path, {"0" : "http://x/static/images/V1-0000-100.jpg"})
    _write_json(beit3_path, {})

    index, stats = m.build_index(str(windows_path), str(fps_path), str(clip_path), str(beit3_path), padding_seconds=5.0)
    assert index == {}
    assert stats["frames_skipped_missing_fps"] == 1
    assert stats["videos_missing_fps"] == ["V1"]


def test_build_index_malformed_mapping_url_counted(tmp_path) :
    windows_path, fps_path = tmp_path / "windows.jsonl", tmp_path / "fps_map.json"
    clip_path, beit3_path = tmp_path / "clip_mapping.json", tmp_path / "beit3_mapping.json"

    _write_jsonl(windows_path, [])
    _write_json(fps_path, {})
    _write_json(clip_path, {"0" : "not-a-url-at-all"})
    _write_json(beit3_path, {})

    index, stats = m.build_index(str(windows_path), str(fps_path), str(clip_path), str(beit3_path), padding_seconds=5.0)
    assert stats["clip_malformed_urls"] == 1
    assert stats["retrievable_frames"] == 0


def test_build_index_union_of_clip_and_beit3(tmp_path) :
    windows_path, fps_path = tmp_path / "windows.jsonl", tmp_path / "fps_map.json"
    clip_path, beit3_path = tmp_path / "clip_mapping.json", tmp_path / "beit3_mapping.json"

    _write_jsonl(windows_path, [])
    _write_json(fps_path, {"V1" : 25.0})
    _write_json(clip_path, {"0" : "http://x/static/images/V1-0000-100.jpg"})
    _write_json(beit3_path, {"0" : "http://x/static/images/V1-0000-200.jpg"})

    index, stats = m.build_index(str(windows_path), str(fps_path), str(clip_path), str(beit3_path), padding_seconds=5.0)
    assert stats["retrievable_frames"] == 2  # union, not each file's own count
    assert stats["clip_only_frames"] == 1
    assert stats["beit3_only_frames"] == 1
    assert stats["frames_in_both"] == 0


def test_build_index_end_to_end_matches_asr_text(tmp_path) :
    windows_path, fps_path = tmp_path / "windows.jsonl", tmp_path / "fps_map.json"
    clip_path, beit3_path = tmp_path / "clip_mapping.json", tmp_path / "beit3_mapping.json"

    _write_jsonl(windows_path, [
        {"video_id" : "V1", "sample_start" : 0, "sample_end" : 960000, "sample_rate" : 16000,
         "eligible" : True, "retrieval_text" : "xin chao"},
    ])
    _write_json(fps_path, {"V1" : 25.0})
    # frame_idx 500 -> 20.0s, inside the 0-60s window
    _write_json(clip_path, {"0" : "http://x/static/images/V1-0000-500.jpg"})
    _write_json(beit3_path, {})

    index, stats = m.build_index(str(windows_path), str(fps_path), str(clip_path), str(beit3_path), padding_seconds=5.0)
    assert index == {"V1-0000-500.jpg" : "xin chao"}
    assert stats["frames_matched"] == 1
    assert stats["frames_no_asr"] == 0
