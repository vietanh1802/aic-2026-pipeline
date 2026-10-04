# backend/tests/test_evaluation_text_measures.py
"""OCR and ASR annotation measures: loading, the silent-zero guard and the strict variant.

The first real run recorded "ASR flagged nothing" because the suite process never loaded the ASR text
index (asr_text.get_text() does not load by itself). These tests pin the three things that fix and
explain it: the loader reports what it read, coverage refuses to answer 0 for an unloaded index, and the
strict rule (every term of a source's cue present in the video) differs from the shipped OR rule exactly
where it should.
"""
from __future__ import annotations

import pytest

from app import asr_text, ocr_search, preprocess, text_signal
from app.evaluation import report, text_measures
from app.text_signal import RequestAnnotation

# video -> terms the fake corpus holds, per source. v1 holds both OCR terms, v2 one, v3 none.
OCR_TERMS = {"v1" : {"13", "2022"}, "v2" : {"13"}, "v3" : set()}
ASR_TERMS = {"v1" : {"lửa"}, "v2" : set(), "v3" : {"lửa", "nước"}}


def _fake_annotate_request(asr_filter, asr_filter_mode, ocr_filter, ocr_filter_mode, legacy_filter, legacy_mode, results) :
    """annotate_request over the fake corpus: a comma separated filter is an OR over its terms (the shipped rule)."""
    def matches(video : str, source : str, query : str) :
        held = (ASR_TERMS if source == "asr" else OCR_TERMS)[video]
        return bool(query.strip()) and any(t.strip() in held for t in query.split(","))

    annotations = {}
    for video in dict.fromkeys(r["video"] for r in results) :
        asr, ocr = matches(video, "asr", asr_filter), matches(video, "ocr", ocr_filter)
        annotations[video] = {
            "matched" : asr or ocr,
            "asr"     : {"location" : "here" if asr else "none", "match_frame" : f"{video}-0001-1.jpg" if asr else None},
            "ocr"     : {"location" : "here" if ocr else "none", "match_frame" : f"{video}-0002-2.jpg" if ocr else None},
        }
    return RequestAnnotation(annotations, True, "mixed", bool(asr_filter), bool(ocr_filter), None, None)


@pytest.fixture()
def fake_annotation(monkeypatch) :
    monkeypatch.setattr(text_signal, "annotate_request", _fake_annotate_request)


FRAMES = [{"video" : v, "name" : f"{v}-0001-1.jpg"} for v in ("v1", "v2", "v3")]


def _block(terms, variant, reference = "v1", asr_mode = "substring") :
    return text_measures.annotate_block(FRAMES, terms, variant, reference, None, 1, asr_mode)


def test_strict_needs_every_term_where_the_shipped_rule_needs_one(fake_annotation) :
    block = _block({"ocr" : ["13", "2022"], "asr" : []}, "ocr")
    assert block["n_flagged"] == 2                              # OR: v1 and v2 hold "13"
    assert block["strict"] == {"ref_flagged" : True, "n_flagged" : 1}   # AND: only v1 holds both
    other = _block({"ocr" : ["13", "2022"], "asr" : []}, "ocr", reference = "v2")
    assert other["ref_flagged"] is True and other["strict"]["ref_flagged"] is False


def test_strict_equals_the_plain_rule_for_single_term_cues(fake_annotation) :
    block = _block({"ocr" : ["13"], "asr" : ["lửa"]}, "both")
    assert block["n_flagged"] == 3 and block["strict"]["n_flagged"] == 3
    assert block["strict"]["ref_flagged"] == block["ref_flagged"]


def test_strict_is_and_over_the_terms_of_a_source_and_or_over_sources(fake_annotation) :
    terms = {"ocr" : ["13", "2022"], "asr" : ["lửa", "nước"]}
    both = _block(terms, "both")
    # OCR strict: v1. ASR strict: v3 (lửa and nước). Union: v1 and v3.
    assert both["strict"] == {"ref_flagged" : True, "n_flagged" : 2}
    assert _block(terms, "asr")["strict"] == {"ref_flagged" : False, "n_flagged" : 1}


def test_strict_is_not_computed_for_bm25(fake_annotation) :
    assert _block({"ocr" : [], "asr" : ["lửa", "nước"]}, "asr", asr_mode = "bm25")["strict"] is None


def test_per_term_scans_are_shared_between_variants(fake_annotation, monkeypatch) :
    calls = []
    real = text_measures._videos_with_term
    monkeypatch.setattr(text_measures, "_videos_with_term", lambda *a : calls.append(a[1 : 3]) or real(*a))
    blocks = text_measures.annotate_query(FRAMES, {"confirmed" : {"ocr" : ["13", "2022"], "asr" : ["lửa", "nước"]}}, "v1", None, 1)
    assert set(blocks["confirmed"]) == {"ocr", "asr", "both"}
    assert sorted(calls) == [("asr", "lửa"), ("asr", "nước"), ("ocr", "13"), ("ocr", "2022")]   # each term once, not once per variant


def test_text_metrics_report_strict_columns_and_blank_for_old_blocks() :
    new = {"ref_flagged" : True, "ref_location" : "here", "ref_in_interval" : None, "n_flagged" : 4, "n_videos" : 8, "ref_rank" : 1,
           "strict" : {"ref_flagged" : True, "n_flagged" : 1}}
    miss = {"ref_flagged" : False, "ref_location" : "none", "ref_in_interval" : None, "n_flagged" : 6, "n_videos" : 8, "ref_rank" : 3,
            "strict" : {"ref_flagged" : False, "n_flagged" : 0}}
    metrics = report._text_signal_metrics([new, miss])
    assert metrics["precision"] == pytest.approx(1 / 10) and metrics["base_rate"] == pytest.approx((4 / 8 + 6 / 8) / 2)
    assert metrics["strict_flag_rate_ref"] == pytest.approx(1 / 2)
    assert metrics["strict_precision"] == pytest.approx(1 / 1)       # one flagged reference of one flagged video
    assert metrics["strict_base_rate"] == pytest.approx((1 / 8 + 0) / 2)
    old = {k : v for k, v in new.items() if k != "strict"}
    assert report._text_signal_metrics([old])["strict_flag_rate_ref"] is None


def test_coverage_refuses_to_report_zero_for_an_unloaded_asr_index(monkeypatch) :
    monkeypatch.setattr(preprocess, "frames_for_video", lambda video : [f"{video}-0001-1.jpg"])
    monkeypatch.setattr(ocr_search, "get_text", lambda name : "text")
    monkeypatch.setattr(asr_text, "get_text", lambda name : "")
    monkeypatch.setattr(asr_text, "status", lambda : {"ready" : False})
    errors : list = []
    coverage = text_measures.coverage_for_video("L01_V001", errors)
    assert coverage == {"keyframes" : 1, "ocr" : 1, "asr" : None}          # None, not 0
    assert [(e["part"], e["source"]) for e in errors] == [("coverage", "asr")]
    monkeypatch.setattr(asr_text, "status", lambda : {"ready" : True})
    assert text_measures.coverage_for_video("L01_V001", [])["asr"] == 0     # a loaded index with no text is a real 0


def test_load_text_artifacts_reports_each_source_and_never_hides_an_error(monkeypatch) :
    def missing() :
        raise FileNotFoundError("Missing ASR text file: /nowhere/asr_text_index.json.gz")

    monkeypatch.setattr(ocr_search, "_load", lambda : None)
    monkeypatch.setattr(ocr_search, "status", lambda : {"ready" : True, "frames_with_text" : 7, "with_marks_path" : "/idx/ocr_clean.json"})
    monkeypatch.setattr(asr_text, "_load", missing)
    monkeypatch.setattr(asr_text, "status", lambda : {"ready" : False, "file_path" : "/nowhere/asr_text_index.json.gz", "entries_loaded" : 0})
    report_ = text_measures.load_text_artifacts()
    assert report_["ocr"] == {"ready" : True, "entries" : 7, "path" : "/idx/ocr_clean.json", "error" : None}
    assert report_["asr"]["ready"] is False and report_["asr"]["entries"] == 0
    assert report_["asr"]["error"].startswith("FileNotFoundError: Missing ASR text file")
