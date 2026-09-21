import json

import numpy as np
import pytest

from app import text_signal
from app.text_signal import TextMatchMode, annotate_videos


@pytest.fixture(autouse=True)
def reset_bm25_state(monkeypatch) :
    """text_signal's BM25 cache is module-level global state -- give every
    test a clean slate, same pattern as test_asr_text.py."""
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


def _mock_text(monkeypatch, ocr : dict, asr : dict) -> None :
    monkeypatch.setattr(text_signal.ocr_search, "get_text", lambda name : ocr.get(name, ""))
    monkeypatch.setattr(text_signal.asr_text, "get_text", lambda name : asr.get(name, ""))


FRAME_NAMES = {
    "V1" : ["V1-0000-100.jpg", "V1-0000-200.jpg"],
    "V2" : ["V2-0000-100.jpg"],
    "V3" : ["V3-0000-100.jpg"],
}


# ── substring mode ───────────────────────────────────────────────────────

def test_substring_match(monkeypatch) :
    _mock_text(monkeypatch, ocr={}, asr={"V1-0000-100.jpg" : "mot con cho dang chay ngoai san"})
    result = annotate_videos(["V1"], "cho", TextMatchMode.substring, FRAME_NAMES)
    assert result["V1"].matched is True
    assert result["V1"].score == 1.0
    assert "asr" in result["V1"].sources


def test_substring_no_match(monkeypatch) :
    _mock_text(monkeypatch, ocr={}, asr={"V1-0000-100.jpg" : "mot con cho dang chay ngoai san"})
    result = annotate_videos(["V1"], "con meo", TextMatchMode.substring, FRAME_NAMES)
    assert result["V1"].matched is False
    assert result["V1"].score == 0.0
    assert result["V1"].sources == []


def test_substring_diacritic_folding(monkeypatch) :
    # query has no diacritics, source text does -- must still match
    _mock_text(monkeypatch, ocr={}, asr={"V1-0000-100.jpg" : "rau ngò tươi ngon"})
    result = annotate_videos(["V1"], "ngo", TextMatchMode.substring, FRAME_NAMES)
    assert result["V1"].matched is True
    assert "ngò" in result["V1"].snippets[0]  # original diacritics preserved in the snippet


def test_substring_empty_query(monkeypatch) :
    _mock_text(monkeypatch, ocr={}, asr={"V1-0000-100.jpg" : "anything at all"})
    result = annotate_videos(["V1"], "   ", TextMatchMode.substring, FRAME_NAMES)
    assert result["V1"].matched is False
    assert result["V1"].score == 0.0
    assert result["V1"].snippets == []


# ── regex mode ───────────────────────────────────────────────────────────

def test_regex_valid_match(monkeypatch) :
    _mock_text(monkeypatch, ocr={}, asr={"V1-0000-100.jpg" : "gia ve la hai trieu dong"})
    result = annotate_videos(["V1"], r"hai\s+trieu", TextMatchMode.regex, FRAME_NAMES)
    assert result["V1"].matched is True
    assert "asr" in result["V1"].sources


def test_regex_valid_no_match(monkeypatch) :
    _mock_text(monkeypatch, ocr={}, asr={"V1-0000-100.jpg" : "gia ve la hai trieu dong"})
    result = annotate_videos(["V1"], r"\d{4}", TextMatchMode.regex, FRAME_NAMES)
    assert result["V1"].matched is False


def test_regex_invalid_pattern_returns_gracefully(monkeypatch) :
    _mock_text(monkeypatch, ocr={}, asr={"V1-0000-100.jpg" : "text"})
    result = annotate_videos(["V1", "V2"], "(unclosed", TextMatchMode.regex, FRAME_NAMES)
    assert result["V1"].matched is False
    assert result["V1"].score == 0.0
    assert result["V1"].snippets[0].startswith("Invalid regex")
    # same error annotation for every requested video, not just the first
    assert result["V2"].snippets[0].startswith("Invalid regex")


# ── snippet formatting ──────────────────────────────────────────────────

def test_snippet_contains_match_wrapped_in_asterisks(monkeypatch) :
    _mock_text(monkeypatch, ocr={}, asr={"V1-0000-100.jpg" : "hom nay troi rat dep va nang"})
    result = annotate_videos(["V1"], "dep", TextMatchMode.substring, FRAME_NAMES)
    assert "**dep**" in result["V1"].snippets[0]


# ── sources: asr vs ocr vs both ──────────────────────────────────────────

def test_sources_identifies_asr_only(monkeypatch) :
    _mock_text(monkeypatch, ocr={}, asr={"V2-0000-100.jpg" : "chi co asr noi tu khoa"})
    result = annotate_videos(["V2"], "tu khoa", TextMatchMode.substring, FRAME_NAMES)
    assert result["V2"].sources == ["asr"]


def test_sources_identifies_ocr_only(monkeypatch) :
    _mock_text(monkeypatch, ocr={"V3-0000-100.jpg" : "CHI CO OCR CO TU KHOA"}, asr={})
    result = annotate_videos(["V3"], "tu khoa", TextMatchMode.substring, FRAME_NAMES)
    assert result["V3"].sources == ["ocr"]


def test_sources_identifies_both(monkeypatch) :
    _mock_text(monkeypatch,
               ocr={"V1-0000-100.jpg" : "man hinh hien tu khoa"},
               asr={"V1-0000-200.jpg" : "loi noi cung co tu khoa"})
    result = annotate_videos(["V1"], "tu khoa", TextMatchMode.substring, FRAME_NAMES)
    assert result["V1"].sources == ["asr", "ocr"]
    assert len(result["V1"].snippets) == 2


# ── never raises ─────────────────────────────────────────────────────────

def test_no_exception_propagates_when_get_text_raises(monkeypatch) :
    def boom(name) :
        raise RuntimeError("simulated failure")
    monkeypatch.setattr(text_signal.ocr_search, "get_text", boom)
    monkeypatch.setattr(text_signal.asr_text, "get_text", boom)
    result = annotate_videos(["V1"], "anything", TextMatchMode.substring, FRAME_NAMES)
    assert result["V1"].matched is False
    assert result["V1"].snippets[0].startswith("Error:")


def test_no_exception_propagates_for_unknown_video(monkeypatch) :
    _mock_text(monkeypatch, ocr={}, asr={})
    # video_id with no entry in frame_names at all
    result = annotate_videos(["GHOST_VIDEO"], "anything", TextMatchMode.substring, {})
    assert result["GHOST_VIDEO"].matched is False


# ── bm25 mode ────────────────────────────────────────────────────────────

def _write_synthetic_bm25_index(tmp_path) :
    """A tiny, hand-built BM25 index matching the REAL artifact's confirmed
    schema: vocabulary.json = {format_version, tokens}, CSR postings as
    uint64/uint32 .npy files, document_lengths.npy sized to the ELIGIBLE
    window count. 4 documents across 2 videos.

    doc 0 (V_A): "meo" x1   doc 1 (V_A): "cho" x1
    doc 2 (V_B): "meo" x2   doc 3 (V_B): "ga" x1

    Query "meo" should score V_B higher than V_A (two hits vs one), and
    query "ga" should match only V_B, leaving V_A unmatched.
    """
    release_dir = tmp_path / "asr_release"
    bm25_dir = release_dir / "bm25"
    bm25_dir.mkdir(parents=True)

    with open(release_dir / "windows.jsonl", "w", encoding="utf-8") as f :
        rows = [
            {"video_id" : "V_A", "eligible" : True, "retrieval_text" : "con meo ngoi tren tham"},
            {"video_id" : "V_A", "eligible" : True, "retrieval_text" : "con cho chay ngoai san"},
            {"video_id" : "V_B", "eligible" : True, "retrieval_text" : "con meo con meo rat dep"},
            {"video_id" : "V_B", "eligible" : True, "retrieval_text" : "trang trai co nhieu ga"},
        ]
        for row in rows :
            f.write(json.dumps(row) + "\n")

    tokens = ["cho", "ga", "meo"]  # term_id 0, 1, 2
    with open(bm25_dir / "vocabulary.json", "w", encoding="utf-8") as f :
        json.dump({"format_version" : "1.0", "tokens" : tokens}, f)

    # grouped by term_id: "cho" -> doc1(tf1); "ga" -> doc3(tf1); "meo" -> doc0(tf1), doc2(tf2)
    posting_doc_ids = np.array([1, 3, 0, 2], dtype=np.uint32)
    posting_term_frequencies = np.array([1, 1, 1, 2], dtype=np.uint32)
    posting_offsets = np.array([0, 1, 2, 4], dtype=np.uint64)
    document_lengths = np.array([5, 5, 6, 5], dtype=np.uint32)

    np.save(bm25_dir / "posting_doc_ids.npy", posting_doc_ids)
    np.save(bm25_dir / "posting_term_frequencies.npy", posting_term_frequencies)
    np.save(bm25_dir / "posting_offsets.npy", posting_offsets)
    np.save(bm25_dir / "document_lengths.npy", document_lengths)

    return str(release_dir)


def test_bm25_scores_normalized_0_to_1_and_ranks_relevance(tmp_path, monkeypatch) :
    release_dir = _write_synthetic_bm25_index(tmp_path)
    monkeypatch.setattr(text_signal, "ASR_RELEASE_DIR", release_dir)

    result = annotate_videos(["V_A", "V_B"], "meo", TextMatchMode.bm25, {})

    assert 0.0 <= result["V_A"].score <= 1.0
    assert 0.0 <= result["V_B"].score <= 1.0
    # V_B's document has "meo" twice -- higher BM25 relevance than V_A's once
    assert result["V_B"].score > result["V_A"].score
    assert result["V_B"].score == 1.0  # the top scorer normalizes to exactly 1.0
    assert result["V_B"].matched is True
    assert result["V_B"].sources == ["asr"]


def test_bm25_query_matching_only_one_video_leaves_other_unmatched(tmp_path, monkeypatch) :
    release_dir = _write_synthetic_bm25_index(tmp_path)
    monkeypatch.setattr(text_signal, "ASR_RELEASE_DIR", release_dir)

    result = annotate_videos(["V_A", "V_B"], "ga", TextMatchMode.bm25, {})
    assert result["V_B"].matched is True
    assert result["V_A"].matched is False
    assert result["V_A"].score == 0.0


def test_bm25_missing_index_falls_back_to_substring_gracefully(tmp_path, monkeypatch) :
    monkeypatch.setattr(text_signal, "ASR_RELEASE_DIR", str(tmp_path / "does_not_exist"))
    _mock_text(monkeypatch, ocr={}, asr={"V1-0000-100.jpg" : "con meo dang ngu"})

    result = annotate_videos(["V1"], "meo", TextMatchMode.bm25, FRAME_NAMES)
    assert result["V1"].matched is True  # substring fallback still finds it
    assert any("BM25 unavailable" in s for s in result["V1"].snippets)
