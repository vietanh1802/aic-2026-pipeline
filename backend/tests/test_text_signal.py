# backend/tests/test_text_signal.py
import json
import os

import numpy as np
import pytest

from app import ocr_search, preprocess, text_lookup, text_signal
from app.text_signal import TextMatchMode, annotate_videos


@pytest.fixture(autouse=True)
def reset_module_state(monkeypatch) :
    """Every backing module keeps module-level cache state -- give each test
    a clean slate, same pattern as test_asr_text.py / test_text_lookup.py."""
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
    monkeypatch.setattr(preprocess, "_video_frames", videos)


def _set_ocr_text(name : str, with_marks : str, no_marks : str | None = None) -> None :
    """Populate ocr_search's real backing dicts -- exercised through the real
    ocr_search.search()/get_text(), not mocked away."""
    ocr_search._display[name] = with_marks
    ocr_search._haystack["with_marks"][name] = with_marks
    ocr_search._haystack["no_marks"][name] = (no_marks or with_marks)


def _mock_asr_text(monkeypatch, texts : dict[str, str]) -> None :
    monkeypatch.setattr(text_signal.asr_text, "get_text", lambda name : texts.get(name, ""))


# ── substring mode: OCR side (via text_lookup) ──────────────────────────────

def test_substring_ocr_exact_match_here(monkeypatch) :
    _set_corpus(monkeypatch, {"V1" : [_meta("V1-0000-100.jpg", "V1", 100)]})
    _mock_asr_text(monkeypatch, {})
    _set_ocr_text("V1-0000-100.jpg", "co tu khoa can tim")

    result = annotate_videos(["V1"], "tu khoa", TextMatchMode.substring,
                              {"V1" : ["V1-0000-100.jpg"]})
    assert result["V1"].matched is True
    assert result["V1"].ocr.match_frame == "V1-0000-100.jpg"
    assert result["V1"].ocr.match_type == "exact"
    assert result["V1"].ocr.location == "here"


def test_substring_ocr_no_match(monkeypatch) :
    _set_corpus(monkeypatch, {"V1" : [_meta("V1-0000-100.jpg", "V1", 100)]})
    _mock_asr_text(monkeypatch, {})
    _set_ocr_text("V1-0000-100.jpg", "khong lien quan")

    result = annotate_videos(["V1"], "tu khoa", TextMatchMode.substring,
                              {"V1" : ["V1-0000-100.jpg"]})
    assert result["V1"].matched is False
    assert result["V1"].ocr.location == "none"
    assert result["V1"].ocr.match_frame is None


def test_substring_empty_query(monkeypatch) :
    _set_corpus(monkeypatch, {"V1" : [_meta("V1-0000-100.jpg", "V1", 100)]})
    result = annotate_videos(["V1"], "   ", TextMatchMode.substring, {})
    assert result["V1"].matched is False
    assert result["V1"].asr.location == "none"
    assert result["V1"].ocr.location == "none"


# ── substring mode: ASR side (own per-frame check, not via lookup_text) ────

def test_substring_asr_match(monkeypatch) :
    _set_corpus(monkeypatch, {"V1" : [_meta("V1-0000-100.jpg", "V1", 100)]})
    _mock_asr_text(monkeypatch, {"V1-0000-100.jpg" : "mot con cho dang chay ngoai san"})

    result = annotate_videos(["V1"], "cho", TextMatchMode.substring, {"V1" : ["V1-0000-100.jpg"]})
    assert result["V1"].matched is True
    assert result["V1"].asr.match_frame == "V1-0000-100.jpg"
    assert result["V1"].asr.match_type == "exact"


def test_substring_asr_diacritic_folding_is_normalized(monkeypatch) :
    # query has no diacritics, source text does -- must still match, tagged
    # "normalized" since it only matched after folding. (No "ngon" in the
    # text -- that word contains the literal, unfolded substring "ngo" and
    # would wrongly tag this "exact".)
    _set_corpus(monkeypatch, {"V1" : [_meta("V1-0000-100.jpg", "V1", 100)]})
    _mock_asr_text(monkeypatch, {"V1-0000-100.jpg" : "rau ngò rất tươi"})

    result = annotate_videos(["V1"], "ngo", TextMatchMode.substring, {"V1" : ["V1-0000-100.jpg"]})
    assert result["V1"].matched is True
    assert result["V1"].asr.match_type == "normalized"


# ── regex mode ───────────────────────────────────────────────────────────

def test_regex_valid_match(monkeypatch) :
    _set_corpus(monkeypatch, {"V1" : [_meta("V1-0000-100.jpg", "V1", 100)]})
    _mock_asr_text(monkeypatch, {"V1-0000-100.jpg" : "gia ve la hai trieu dong"})
    monkeypatch.setattr(ocr_search, "get_text", lambda name : "")

    result = annotate_videos(["V1"], r"hai\s+trieu", TextMatchMode.regex, {"V1" : ["V1-0000-100.jpg"]})
    assert result["V1"].matched is True
    assert result["V1"].asr.match_type == "exact"  # regex has no folded tier


def test_regex_valid_no_match(monkeypatch) :
    _set_corpus(monkeypatch, {"V1" : [_meta("V1-0000-100.jpg", "V1", 100)]})
    _mock_asr_text(monkeypatch, {"V1-0000-100.jpg" : "gia ve la hai trieu dong"})
    monkeypatch.setattr(ocr_search, "get_text", lambda name : "")

    result = annotate_videos(["V1"], r"\d{4}", TextMatchMode.regex, {"V1" : ["V1-0000-100.jpg"]})
    assert result["V1"].matched is False


def test_regex_invalid_pattern_returns_gracefully(monkeypatch) :
    _set_corpus(monkeypatch, {"V1" : [_meta("V1-0000-100.jpg", "V1", 100)],
                              "V2" : [_meta("V2-0000-100.jpg", "V2", 100)]})
    result = annotate_videos(["V1", "V2"], "(unclosed", TextMatchMode.regex, {})
    assert result["V1"].matched is False
    assert result["V1"].asr.location == "none"
    # same (non-)result for every requested video, not just the first
    assert result["V2"].matched is False


def test_regex_not_diacritic_folded(monkeypatch) :
    """Old substring-mode guarantee, still true for regex: querying without
    diacritics must NOT match text that only has the accented form."""
    _set_corpus(monkeypatch, {"V1" : [_meta("V1-0000-100.jpg", "V1", 100)]})
    _mock_asr_text(monkeypatch, {"V1-0000-100.jpg" : "rau ngò rất tươi"})
    monkeypatch.setattr(ocr_search, "get_text", lambda name : "")

    result = annotate_videos(["V1"], "ngo", TextMatchMode.regex, {"V1" : ["V1-0000-100.jpg"]})
    assert result["V1"].matched is False


# ── never raises ─────────────────────────────────────────────────────────

def test_no_exception_propagates_when_get_text_raises(monkeypatch) :
    _set_corpus(monkeypatch, {"V1" : [_meta("V1-0000-100.jpg", "V1", 100)]})
    def boom(name) :
        raise RuntimeError("simulated failure")
    monkeypatch.setattr(text_signal.asr_text, "get_text", boom)
    monkeypatch.setattr(ocr_search, "search", boom)

    result = annotate_videos(["V1"], "anything", TextMatchMode.substring, {})
    assert result["V1"].matched is False
    assert result["V1"].asr.location == "none"


def test_no_exception_propagates_for_unknown_video(monkeypatch) :
    _set_corpus(monkeypatch, {})
    result = annotate_videos(["GHOST_VIDEO"], "anything", TextMatchMode.substring, {})
    assert result["GHOST_VIDEO"].matched is False


# ── here vs. elsewhere ───────────────────────────────────────────────────

def test_location_here_when_match_frame_is_in_result_set(monkeypatch) :
    _set_corpus(monkeypatch, {"V1" : [_meta("V1-0000-100.jpg", "V1", 100)]})
    _mock_asr_text(monkeypatch, {})
    _set_ocr_text("V1-0000-100.jpg", "tu khoa")

    result = annotate_videos(["V1"], "tu khoa", TextMatchMode.substring,
                              {"V1" : ["V1-0000-100.jpg"]})
    assert result["V1"].ocr.location == "here"


def test_location_elsewhere_when_match_frame_is_not_in_result_set(monkeypatch) :
    # The matching frame (100) exists in the video's real frame list but was
    # not one of the frames the visual search actually retrieved (200 was).
    _set_corpus(monkeypatch, {"V1" : [_meta("V1-0000-100.jpg", "V1", 100),
                                       _meta("V1-0000-200.jpg", "V1", 200)]})
    _mock_asr_text(monkeypatch, {})
    _set_ocr_text("V1-0000-100.jpg", "tu khoa")
    _set_ocr_text("V1-0000-200.jpg", "khong lien quan")

    result = annotate_videos(["V1"], "tu khoa", TextMatchMode.substring,
                              {"V1" : ["V1-0000-200.jpg"]})
    assert result["V1"].matched is True
    assert result["V1"].ocr.match_frame == "V1-0000-100.jpg"
    assert result["V1"].ocr.location == "elsewhere"


# ── exact vs. normalized preference ─────────────────────────────────────

def test_exact_preferred_over_normalized_even_when_normalized_is_here(monkeypatch) :
    """frame A: "here", matches only after diacritic folding ("normalized").
    frame B: "elsewhere", matches with real diacritics intact ("exact").
    match_type takes priority over location -- B wins."""
    _set_corpus(monkeypatch, {"V1" : [_meta("V1-0000-100.jpg", "V1", 100),
                                       _meta("V1-0000-200.jpg", "V1", 200)]})
    _mock_asr_text(monkeypatch, {})
    _set_ocr_text("V1-0000-100.jpg", with_marks="khong co dau day du", no_marks="tu khoa day day")
    _set_ocr_text("V1-0000-200.jpg", with_marks="tu khoa", no_marks="tu khoa")

    result = annotate_videos(["V1"], "tu khoa", TextMatchMode.substring,
                              {"V1" : ["V1-0000-100.jpg"]})  # only A is "here"
    assert result["V1"].ocr.match_frame == "V1-0000-200.jpg"
    assert result["V1"].ocr.match_type == "exact"
    assert result["V1"].ocr.location == "elsewhere"


def test_here_preferred_over_elsewhere_when_match_type_ties(monkeypatch) :
    _set_corpus(monkeypatch, {"V1" : [_meta("V1-0000-100.jpg", "V1", 100),
                                       _meta("V1-0000-200.jpg", "V1", 200)]})
    _mock_asr_text(monkeypatch, {})
    _set_ocr_text("V1-0000-100.jpg", "tu khoa")   # here, exact
    _set_ocr_text("V1-0000-200.jpg", "tu khoa")   # elsewhere, also exact

    result = annotate_videos(["V1"], "tu khoa", TextMatchMode.substring,
                              {"V1" : ["V1-0000-100.jpg"]})
    assert result["V1"].ocr.match_frame == "V1-0000-100.jpg"
    assert result["V1"].ocr.location == "here"


# ── regression: the two confirmed bugs this rewrite fixes ─────────────────

def test_regression_match_not_misattributed_to_a_different_frame(monkeypatch) :
    """The "2018" bug: a genuine match on one frame must never be reported
    against a different, unrelated frame of the same video. Frame 100 (the
    one actually retrieved by visual search) does NOT contain "2018"; frame
    200 (not retrieved) does. The old blob-concatenation code could not tell
    them apart; this must report frame 200 by name, as "elsewhere"."""
    _set_corpus(monkeypatch, {"V1" : [_meta("V1-0000-100.jpg", "V1", 100),
                                       _meta("V1-0000-200.jpg", "V1", 200)]})
    _mock_asr_text(monkeypatch, {})
    _set_ocr_text("V1-0000-100.jpg", "de thi nam hoc truoc")   # no "2018" here
    _set_ocr_text("V1-0000-200.jpg", "de thi THPTQG 2018")     # "2018" is here

    result = annotate_videos(["V1"], "2018", TextMatchMode.substring,
                              {"V1" : ["V1-0000-100.jpg"]})  # only frame 100 was retrieved
    assert result["V1"].matched is True
    assert result["V1"].ocr.match_frame == "V1-0000-200.jpg"  # not the retrieved frame
    assert result["V1"].ocr.location == "elsewhere"


def test_regression_match_outside_result_set_is_not_invisible(monkeypatch) :
    """The "nghêu" bug: a real match must be found even when none of the
    frames the visual search happened to retrieve for this video contain it
    -- as long as SOME frame of the video's real, full frame list does."""
    video_frames = [_meta(f"V2-0000-{i}.jpg", "V2", i) for i in range(1, 17)]
    _set_corpus(monkeypatch, {"V2" : video_frames})
    _mock_asr_text(monkeypatch, {})
    for frame in video_frames :
        _set_ocr_text(frame["name"], "khong lien quan")
    _set_ocr_text("V2-0000-5.jpg", "mon nghêu hap sa")  # the one real hit, frame 5

    # Visual search only retrieved frame 1 -- frame 5 was never in the top-100.
    result = annotate_videos(["V2"], "nghêu", TextMatchMode.substring,
                              {"V2" : ["V2-0000-1.jpg"]})
    assert result["V2"].matched is True
    assert result["V2"].ocr.match_frame == "V2-0000-5.jpg"
    assert result["V2"].ocr.location == "elsewhere"


# ── bm25 mode ────────────────────────────────────────────────────────────

def _write_bm25_index(tmp_path) :
    """Synthetic BM25 index + windows.jsonl carrying real sample_start/
    sample_rate, so lookup_text()'s window-to-frame mapping has a genuine
    time range to convert (same schema as test_text_lookup.py's helper).

    doc0 (V_A, "meo"): starts at 4000/1000 = 4.0s -> frame_idx 100 @ 25fps
    doc1 (V_A, "cho"): starts at 16000/1000 = 16.0s -> frame_idx 400 @ 25fps
    doc2 (V_B, "meo" x2): starts at 0s -> frame_idx 0
    """
    release_dir = tmp_path / "asr_release"
    bm25_dir = release_dir / "bm25"
    bm25_dir.mkdir(parents=True)

    rows = [
        {"video_id" : "V_A", "eligible" : True, "retrieval_text" : "con meo ngoi tren tham",
         "sample_start" : 4000, "sample_end" : 8000, "sample_rate" : 1000},
        {"video_id" : "V_A", "eligible" : True, "retrieval_text" : "con cho chay ngoai san",
         "sample_start" : 16000, "sample_end" : 20000, "sample_rate" : 1000},
        {"video_id" : "V_B", "eligible" : True, "retrieval_text" : "con meo con meo rat dep",
         "sample_start" : 0, "sample_end" : 4000, "sample_rate" : 1000},
    ]
    with open(release_dir / "windows.jsonl", "w", encoding="utf-8") as f :
        for row in rows :
            f.write(json.dumps(row) + "\n")

    tokens = ["cho", "meo"]
    with open(bm25_dir / "vocabulary.json", "w", encoding="utf-8") as f :
        json.dump({"format_version" : "1.0", "tokens" : tokens}, f)

    # "cho" -> doc1(tf1); "meo" -> doc0(tf1), doc2(tf2)
    posting_doc_ids = np.array([1, 0, 2], dtype=np.uint32)
    posting_term_frequencies = np.array([1, 1, 2], dtype=np.uint32)
    posting_offsets = np.array([0, 1, 3], dtype=np.uint64)
    document_lengths = np.array([5, 5, 6], dtype=np.uint32)

    np.save(bm25_dir / "posting_doc_ids.npy", posting_doc_ids)
    np.save(bm25_dir / "posting_term_frequencies.npy", posting_term_frequencies)
    np.save(bm25_dir / "posting_offsets.npy", posting_offsets)
    np.save(bm25_dir / "document_lengths.npy", document_lengths)

    return str(release_dir)


def test_bm25_scores_and_attributes_to_the_matching_window_frame(monkeypatch, tmp_path) :
    """VideoAnnotation.score is binary (1.0 matched / 0.0 not) in every mode
    since Stage C, bm25 included -- continuous BM25 relevance (V_B's doc has
    "meo" twice, a genuinely higher raw score than V_A's once, confirmed via
    text_lookup's own rank/total_matched) is available at that finer layer,
    not surfaced on VideoAnnotation itself. See Stage C's report."""
    release_dir = _write_bm25_index(tmp_path)
    monkeypatch.setattr(text_signal, "ASR_RELEASE_DIR", release_dir)
    _set_corpus(monkeypatch, {
        "V_A" : [_meta("V_A-0000-100.jpg", "V_A", 100), _meta("V_A-0000-400.jpg", "V_A", 400)],
        "V_B" : [_meta("V_B-0000-0.jpg", "V_B", 0)],
    })

    result = annotate_videos(["V_A", "V_B"], "meo", TextMatchMode.bm25, {})
    assert result["V_B"].matched is True
    assert result["V_B"].score == 1.0
    assert result["V_B"].asr.match_frame == "V_B-0000-0.jpg"
    assert result["V_A"].matched is True
    assert result["V_A"].asr.match_frame == "V_A-0000-100.jpg"
    assert result["V_A"].ocr.location == "none"  # bm25 mode never checks ocr


def test_bm25_query_matching_only_one_video_leaves_other_unmatched(monkeypatch, tmp_path) :
    release_dir = _write_bm25_index(tmp_path)
    monkeypatch.setattr(text_signal, "ASR_RELEASE_DIR", release_dir)
    _set_corpus(monkeypatch, {
        "V_A" : [_meta("V_A-0000-100.jpg", "V_A", 100), _meta("V_A-0000-400.jpg", "V_A", 400)],
        "V_B" : [_meta("V_B-0000-0.jpg", "V_B", 0)],
    })

    result = annotate_videos(["V_A", "V_B"], "cho", TextMatchMode.bm25, {})
    assert result["V_A"].matched is True
    assert result["V_A"].asr.match_frame == "V_A-0000-400.jpg"
    assert result["V_B"].matched is False


def test_bm25_missing_index_reports_no_match(monkeypatch, tmp_path) :
    """Stage C dropped the old "fall back to substring" behavior for bm25
    mode (text_lookup.lookup_text() has no such fallback) -- an unavailable
    BM25 index now simply means no ASR hits, not a silent mode switch."""
    monkeypatch.setattr(text_signal, "ASR_RELEASE_DIR", str(tmp_path / "does_not_exist"))
    _set_corpus(monkeypatch, {"V1" : [_meta("V1-0000-100.jpg", "V1", 100)]})
    _mock_asr_text(monkeypatch, {"V1-0000-100.jpg" : "con meo dang ngu"})

    result = annotate_videos(["V1"], "meo", TextMatchMode.bm25, {})
    assert result["V1"].matched is False
    assert result["V1"].asr.location == "none"


# ── status() reports BM25 unavailability with a real reason ──────────────

def test_status_reports_bm25_unavailable_reason(tmp_path, monkeypatch) :
    """Regression for the production sighting: bm25_ready=false but
    bm25_unavailable_reason=null. That combination meant _load_bm25() had
    never been ATTEMPTED (lazy load, nobody had run a bm25-mode query yet)
    -- not that the reason was being lost on a real failure. Once a load is
    attempted, a real failure must always leave a reason string behind."""
    monkeypatch.setattr(text_signal, "ASR_RELEASE_DIR", str(tmp_path / "does_not_exist"))

    before = text_signal.status()
    assert before["bm25_ready"] is False
    assert before["bm25_unavailable_reason"] is None  # not attempted yet

    annotate_videos(["V1"], "meo", TextMatchMode.bm25, {})  # triggers _load_bm25()

    after = text_signal.status()
    assert after["bm25_ready"] is False
    assert after["bm25_unavailable_reason"] is not None
    assert "FileNotFoundError" in after["bm25_unavailable_reason"]
    assert after["bm25_documents"] == 0


def test_preload_loads_bm25_eagerly(monkeypatch, tmp_path) :
    """preload() (called from main.py's warm-up, same as
    ocr_route.preload()/_asr_text.preload()) must populate status() WITHOUT
    a bm25-mode request ever having been made -- that is the whole point of
    moving BM25 off its old lazy-load path."""
    release_dir = _write_bm25_index(tmp_path)
    monkeypatch.setattr(text_signal, "ASR_RELEASE_DIR", release_dir)

    assert text_signal.status()["bm25_ready"] is False  # nothing has loaded yet
    text_signal.preload()
    status = text_signal.status()
    assert status["bm25_ready"] is True
    assert status["bm25_documents"] == 3
    assert status["bm25_unavailable_reason"] is None


# ── ASR_RELEASE_DIR resolution against AIC_INDEX_DIR ──────────────────────

def test_asr_release_dir_resolves_under_aic_index_dir(monkeypatch) :
    monkeypatch.setenv("AIC_INDEX_DIR", os.path.join("opt", "aic", "indexes"))
    monkeypatch.delenv("AIC_ASR_RELEASE_DIR", raising=False)
    resolved = text_signal._resolve_asr_release_dir()
    assert resolved == os.path.join("opt", "aic", "indexes", "asr")


def test_asr_release_dir_explicit_override_wins(monkeypatch) :
    monkeypatch.setenv("AIC_INDEX_DIR", os.path.join("opt", "aic", "indexes"))
    monkeypatch.setenv("AIC_ASR_RELEASE_DIR", os.path.join("custom", "path"))
    resolved = text_signal._resolve_asr_release_dir()
    assert resolved == os.path.join("custom", "path")


def test_asr_release_dir_falls_back_to_local_indexes_dir_without_aic_index_dir(monkeypatch) :
    monkeypatch.delenv("AIC_INDEX_DIR", raising=False)
    monkeypatch.delenv("AIC_ASR_RELEASE_DIR", raising=False)
    resolved = text_signal._resolve_asr_release_dir()
    expected = os.path.join(
        os.path.dirname(os.path.abspath(text_signal.__file__)), "indexes", "asr")
    assert resolved == expected
