# backend/tests/test_text_lookup.py
import json

import numpy as np
import pytest

from app import ocr_search, preprocess, text_lookup, text_signal


@pytest.fixture(autouse=True)
def reset_module_state(monkeypatch) :
    """Every backing module keeps module-level cache state -- give each test a
    clean slate, same pattern as test_text_signal.py/test_asr_text.py."""
    monkeypatch.setattr(preprocess, "_video_frames", {})
    monkeypatch.setattr(ocr_search, "_loaded", True)
    monkeypatch.setattr(ocr_search, "_display", {})
    monkeypatch.setattr(ocr_search, "_haystack", {"with_marks" : {}, "no_marks" : {}})
    monkeypatch.setattr(text_signal, "_bm25_loaded", False)
    monkeypatch.setattr(text_signal, "_bm25_unavailable_reason", None)
    monkeypatch.setattr(text_signal, "_bm25_token_to_id", {})
    monkeypatch.setattr(text_signal, "_bm25_posting_offsets", None)
    monkeypatch.setattr(text_signal, "_bm25_posting_doc_ids", None)
    monkeypatch.setattr(text_signal, "_bm25_posting_term_freqs", None)
    monkeypatch.setattr(text_signal, "_bm25_document_lengths", None)
    monkeypatch.setattr(text_signal, "_bm25_avgdl", 0.0)
    monkeypatch.setattr(text_signal, "_bm25_doc_video_ids", [])
    monkeypatch.setattr(text_signal, "_bm25_doc_texts", [])
    monkeypatch.setattr(text_lookup, "_windows_cache", None)


def _meta(name : str, video : str, frame_idx : int, fps : float = 25.0) -> dict :
    return {"name" : name, "video" : video, "frame_idx" : frame_idx, "fps" : fps}


def _set_corpus(monkeypatch, videos : dict[str, list[dict]]) -> None :
    """videos: video_id -> list of frame metadata dicts (from _meta())."""
    monkeypatch.setattr(preprocess, "_video_frames", videos)


# ── preprocess.frames_for_video / fps_for_video ─────────────────────────────

def test_frames_for_video_returns_names_in_order(monkeypatch) :
    _set_corpus(monkeypatch, {"V1" : [_meta("V1-0000-100.jpg", "V1", 100),
                                       _meta("V1-0000-200.jpg", "V1", 200)]})
    assert preprocess.frames_for_video("V1") == ["V1-0000-100.jpg", "V1-0000-200.jpg"]


def test_frames_for_video_unknown_video_returns_empty(monkeypatch) :
    _set_corpus(monkeypatch, {})
    assert preprocess.frames_for_video("GHOST") == []


def test_fps_for_video_reads_from_first_frame(monkeypatch) :
    _set_corpus(monkeypatch, {"V1" : [_meta("V1-0000-100.jpg", "V1", 100, fps=30.0)]})
    assert preprocess.fps_for_video("V1") == 30.0


def test_fps_for_video_unknown_video_falls_back_to_25(monkeypatch) :
    _set_corpus(monkeypatch, {})
    assert preprocess.fps_for_video("GHOST") == 25.0


# ── OCR: exact vs. normalized tagging ────────────────────────────────────────

def test_ocr_exact_tag_when_query_matches_with_marks(monkeypatch) :
    _set_corpus(monkeypatch, {"V1" : [_meta("V1-0000-100.jpg", "V1", 100)]})
    ocr_search._display["V1-0000-100.jpg"] = "co tu khoa can tim"
    ocr_search._haystack["with_marks"]["V1-0000-100.jpg"] = "co tu khoa can tim"
    ocr_search._haystack["no_marks"]["V1-0000-100.jpg"] = "co tu khoa can tim"

    hits = text_lookup.lookup_text("tu khoa", source="ocr", scope="video", video_id="V1")
    assert len(hits) == 1
    assert hits[0].match_type == "exact"
    assert hits[0].video_id == "V1"
    assert hits[0].frame_name == "V1-0000-100.jpg"


def test_ocr_normalized_tag_when_query_only_matches_after_folding(monkeypatch) :
    _set_corpus(monkeypatch, {"V2" : [_meta("V2-0000-100.jpg", "V2", 100)]})
    # with_marks keeps real diacritics -- "tu khoa" (typed with no accents) will
    # not substring-match "từ khóa" there; no_marks is the pre-folded form.
    ocr_search._display["V2-0000-100.jpg"] = "co từ khóa can tim"
    ocr_search._haystack["with_marks"]["V2-0000-100.jpg"] = "co từ khóa can tim"
    ocr_search._haystack["no_marks"]["V2-0000-100.jpg"] = "co tu khoa can tim"

    hits = text_lookup.lookup_text("tu khoa", source="ocr", scope="video", video_id="V2")
    assert len(hits) == 1
    assert hits[0].match_type == "normalized"


def test_ocr_exact_wins_when_hit_found_both_ways(monkeypatch) :
    _set_corpus(monkeypatch, {"V1" : [_meta("V1-0000-100.jpg", "V1", 100)]})
    ocr_search._display["V1-0000-100.jpg"] = "tu khoa"
    ocr_search._haystack["with_marks"]["V1-0000-100.jpg"] = "tu khoa"
    ocr_search._haystack["no_marks"]["V1-0000-100.jpg"] = "tu khoa"

    hits = text_lookup.lookup_text("tu khoa", source="ocr", scope="video", video_id="V1")
    assert len(hits) == 1  # not reported twice
    assert hits[0].match_type == "exact"


# ── OCR: video-scope vs. corpus-scope ────────────────────────────────────────

def test_ocr_video_scope_excludes_other_videos(monkeypatch) :
    _set_corpus(monkeypatch, {
        "V1" : [_meta("V1-0000-100.jpg", "V1", 100)],
        "V2" : [_meta("V2-0000-100.jpg", "V2", 100)],
    })
    for name in ("V1-0000-100.jpg", "V2-0000-100.jpg") :
        ocr_search._display[name] = "tu khoa"
        ocr_search._haystack["with_marks"][name] = "tu khoa"
        ocr_search._haystack["no_marks"][name] = "tu khoa"

    hits = text_lookup.lookup_text("tu khoa", source="ocr", scope="video", video_id="V1")
    assert {h.video_id for h in hits} == {"V1"}


def test_ocr_corpus_scope_returns_every_indexed_video(monkeypatch) :
    _set_corpus(monkeypatch, {
        "V1" : [_meta("V1-0000-100.jpg", "V1", 100)],
        "V2" : [_meta("V2-0000-100.jpg", "V2", 100)],
    })
    for name in ("V1-0000-100.jpg", "V2-0000-100.jpg") :
        ocr_search._display[name] = "tu khoa"
        ocr_search._haystack["with_marks"][name] = "tu khoa"
        ocr_search._haystack["no_marks"][name] = "tu khoa"

    hits = text_lookup.lookup_text("tu khoa", source="ocr", scope="corpus")
    assert {h.video_id for h in hits} == {"V1", "V2"}


# ── OCR: the 873-video exclusion ─────────────────────────────────────────────

def test_ocr_corpus_scope_excludes_video_outside_visual_corpus(monkeypatch) :
    """K01_V001 stands in for the confirmed K01-K20 gap: real ASR/OCR text
    exists for it, but it was never keyframe-extracted, so it has no entry in
    preprocess._video_frames -- frames_for_video() returns [] for it."""
    _set_corpus(monkeypatch, {"L21_V001" : [_meta("L21_V001-0000-100.jpg", "L21_V001", 100)]})
    for name in ("L21_V001-0000-100.jpg", "K01_V001-0000-50.jpg") :
        ocr_search._display[name] = "tu khoa"
        ocr_search._haystack["with_marks"][name] = "tu khoa"
        ocr_search._haystack["no_marks"][name] = "tu khoa"

    hits = text_lookup.lookup_text("tu khoa", source="ocr", scope="corpus")
    assert "K01_V001" not in {h.video_id for h in hits}
    assert {h.video_id for h in hits} == {"L21_V001"}


# ── ASR: window-to-frame mapping ─────────────────────────────────────────────

def _write_bm25_and_windows(tmp_path) :
    """Synthetic BM25 index (schema matches test_text_signal.py's own helper)
    plus a windows.jsonl carrying real sample_start/sample_end/sample_rate, so
    _windows_by_video() has a genuine time range to convert to a frame."""
    release_dir = tmp_path / "asr_release"
    bm25_dir = release_dir / "bm25"
    bm25_dir.mkdir(parents=True)

    rows = [
        {"video_id" : "V_A", "eligible" : True, "retrieval_text" : "con meo ngoi tren tham",
         "sample_start" : 4000, "sample_end" : 8000, "sample_rate" : 1000},
        {"video_id" : "V_A", "eligible" : True, "retrieval_text" : "con cho chay ngoai san",
         "sample_start" : 16000, "sample_end" : 20000, "sample_rate" : 1000},
    ]
    with open(release_dir / "windows.jsonl", "w", encoding="utf-8") as f :
        for row in rows :
            f.write(json.dumps(row) + "\n")

    tokens = ["cho", "meo"]
    with open(bm25_dir / "vocabulary.json", "w", encoding="utf-8") as f :
        json.dump({"format_version" : "1.0", "tokens" : tokens}, f)

    posting_doc_ids = np.array([1, 0], dtype=np.uint32)          # "cho"->doc1, "meo"->doc0
    posting_term_frequencies = np.array([1, 1], dtype=np.uint32)
    posting_offsets = np.array([0, 1, 2], dtype=np.uint64)
    document_lengths = np.array([5, 5], dtype=np.uint32)

    np.save(bm25_dir / "posting_doc_ids.npy", posting_doc_ids)
    np.save(bm25_dir / "posting_term_frequencies.npy", posting_term_frequencies)
    np.save(bm25_dir / "posting_offsets.npy", posting_offsets)
    np.save(bm25_dir / "document_lengths.npy", document_lengths)

    return str(release_dir)


def test_asr_maps_matching_window_to_nearest_keyframe(monkeypatch, tmp_path) :
    release_dir = _write_bm25_and_windows(tmp_path)
    monkeypatch.setattr(text_signal, "ASR_RELEASE_DIR", release_dir)
    # doc0 ("meo") starts at 4000/1000 = 4.0s; at 25fps that is frame_idx 100 --
    # an exact hit on one of V_A's own real keyframes.
    _set_corpus(monkeypatch, {"V_A" : [_meta("V_A-0000-100.jpg", "V_A", 100),
                                        _meta("V_A-0000-400.jpg", "V_A", 400)]})

    hits = text_lookup.lookup_text("meo", source="asr", scope="video", video_id="V_A")
    assert len(hits) == 1
    assert hits[0].frame_name == "V_A-0000-100.jpg"
    assert hits[0].match_type == "exact"
    assert hits[0].video_id == "V_A"


def test_asr_picks_second_window_when_only_it_matches(monkeypatch, tmp_path) :
    release_dir = _write_bm25_and_windows(tmp_path)
    monkeypatch.setattr(text_signal, "ASR_RELEASE_DIR", release_dir)
    # doc1 ("cho") starts at 16000/1000 = 16.0s; at 25fps that is frame_idx 400.
    _set_corpus(monkeypatch, {"V_A" : [_meta("V_A-0000-100.jpg", "V_A", 100),
                                        _meta("V_A-0000-400.jpg", "V_A", 400)]})

    hits = text_lookup.lookup_text("cho", source="asr", scope="video", video_id="V_A")
    assert len(hits) == 1
    assert hits[0].frame_name == "V_A-0000-400.jpg"


def test_asr_no_hit_when_video_has_no_keyframes(monkeypatch, tmp_path) :
    release_dir = _write_bm25_and_windows(tmp_path)
    monkeypatch.setattr(text_signal, "ASR_RELEASE_DIR", release_dir)
    _set_corpus(monkeypatch, {})  # V_A matches on BM25 but was never keyframe-extracted

    hits = text_lookup.lookup_text("meo", source="asr", scope="video", video_id="V_A")
    assert hits == []


def test_asr_corpus_scope_excludes_video_outside_visual_corpus(monkeypatch, tmp_path) :
    release_dir = _write_bm25_and_windows(tmp_path)
    monkeypatch.setattr(text_signal, "ASR_RELEASE_DIR", release_dir)
    _set_corpus(monkeypatch, {})  # V_A has ASR data but no keyframes at all

    hits = text_lookup.lookup_text("meo", source="asr", scope="corpus")
    assert hits == []


def test_asr_rank_and_total_matched_are_per_video(monkeypatch, tmp_path) :
    """"meo" only ever appears in V_A's doc0 -- one matching video, rank 1."""
    release_dir = _write_bm25_and_windows(tmp_path)
    monkeypatch.setattr(text_signal, "ASR_RELEASE_DIR", release_dir)
    _set_corpus(monkeypatch, {"V_A" : [_meta("V_A-0000-100.jpg", "V_A", 100)]})

    hits = text_lookup.lookup_text("meo", source="asr", scope="corpus")
    assert len(hits) == 1
    assert hits[0].rank == 1
    assert hits[0].total_matched == 1


# ── lookup_text() argument validation and safety ─────────────────────────────

def test_scope_video_without_video_id_raises() :
    with pytest.raises(ValueError) :
        text_lookup.lookup_text("anything", source="ocr", scope="video")


def test_never_raises_on_internal_error(monkeypatch) :
    def boom(*args, **kwargs) :
        raise RuntimeError("simulated failure")
    monkeypatch.setattr(ocr_search, "search", boom)
    assert text_lookup.lookup_text("anything", source="ocr", scope="corpus") == []


# ── preload() ──────────────────────────────────────────────────────────────

def test_preload_warms_the_windows_cache_without_a_lookup_call(monkeypatch, tmp_path) :
    """The whole point: _windows_cache must be populated by preload() alone,
    before any lookup_text() call ever touches it -- same contract as
    asr_text.preload()/ocr_search.preload()/text_signal.preload()."""
    release_dir = _write_bm25_and_windows(tmp_path)
    monkeypatch.setattr(text_signal, "ASR_RELEASE_DIR", release_dir)

    assert text_lookup._windows_cache is None
    text_lookup.preload()
    assert text_lookup._windows_cache is not None
    assert "V_A" in text_lookup._windows_cache


def test_preload_is_idempotent(monkeypatch, tmp_path) :
    release_dir = _write_bm25_and_windows(tmp_path)
    monkeypatch.setattr(text_signal, "ASR_RELEASE_DIR", release_dir)

    text_lookup.preload()
    first = text_lookup._windows_cache
    text_lookup.preload()
    assert text_lookup._windows_cache is first  # not rebuilt


def test_preload_does_not_raise_when_windows_jsonl_is_missing(monkeypatch, tmp_path) :
    monkeypatch.setattr(text_signal, "ASR_RELEASE_DIR", str(tmp_path / "does_not_exist"))
    text_lookup.preload()  # must not raise
    assert text_lookup._windows_cache == {}


def test_preload_does_not_raise_on_a_corrupt_windows_jsonl(monkeypatch, tmp_path) :
    release_dir = tmp_path / "asr_release"
    release_dir.mkdir()
    (release_dir / "windows.jsonl").write_text("{not valid json", encoding="utf-8")
    monkeypatch.setattr(text_signal, "ASR_RELEASE_DIR", str(release_dir))

    text_lookup.preload()  # must not raise
    # _windows_by_video() sets the cache to {} before it starts reading lines,
    # so a mid-parse failure leaves it cached empty rather than unset -- same
    # "fail once, don't retry every call" shape as text_signal's own
    # _bm25_unavailable_reason latch.
    assert text_lookup._windows_cache == {}
