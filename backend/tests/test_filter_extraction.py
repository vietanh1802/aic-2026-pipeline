from __future__ import annotations

import io
import json

import pytest

import app.filter_extraction as filter_extraction
import app.translation as translation
from app.filter_extraction import FilterTerms, _parse_filter_json, extract_filter_terms


@pytest.fixture(autouse=True)
def reset_module_state(monkeypatch) :
    """filter_extraction's cache and translation's pacing clock are both
    module-level global state -- give every test a clean slate, same pattern
    as test_translation.py's fake_clock fixture."""
    monkeypatch.setattr(filter_extraction, "_FILTER_CACHE", {})
    monkeypatch.setattr(translation, "_last_call_started_at", {})


def _gemini_body(text : str) -> bytes :
    return json.dumps({"candidates" : [{"content" : {"parts" : [{"text" : text}]}}]}).encode("utf-8")


# ── _parse_filter_json: pure function, operates on the model's TEXT output ──

def test_valid_response_parsed_correctly() :
    raw = json.dumps({
        "asr_terms" : ["bún gà", "sả"],
        "ocr_terms" : ["37.05"],
        "confidence" : "medium",
        "reasoning" : "Dish name and displayed number are distinctive.",
    })
    result = _parse_filter_json(raw)
    assert result.asr_terms == ["bún gà", "sả"]
    assert result.ocr_terms == ["37.05"]
    assert result.confidence == "medium"
    assert result.reasoning == "Dish name and displayed number are distinctive."


def test_empty_lists_returned_when_confidence_is_none() :
    raw = json.dumps({
        "asr_terms" : [], "ocr_terms" : [], "confidence" : "none",
        "reasoning" : "Purely visual query, no spoken/text signal expected.",
    })
    result = _parse_filter_json(raw)
    assert result.asr_terms == []
    assert result.ocr_terms == []
    assert result.confidence == "none"


def test_malformed_json_response_handled_gracefully() :
    result = _parse_filter_json("this is not json at all")
    assert result.asr_terms == []
    assert result.ocr_terms == []
    assert result.confidence == "none"
    assert result.reasoning == "parse error"


def test_missing_fields_handled_gracefully() :
    result = _parse_filter_json(json.dumps({"asr_terms" : ["a"]}))
    assert result.asr_terms == ["a"]
    assert result.ocr_terms == []
    assert result.confidence == "none"
    assert result.reasoning == "parse error"


def test_invalid_confidence_value_coerced_to_none() :
    raw = json.dumps({
        "asr_terms" : [], "ocr_terms" : [], "confidence" : "very sure",
        "reasoning" : "x",
    })
    result = _parse_filter_json(raw)
    assert result.confidence == "none"


def test_terms_have_whitespace_stripped_and_empty_strings_removed() :
    raw = json.dumps({
        "asr_terms" : ["  bún gà  ", "", "   ", "sả"],
        "ocr_terms" : ["37.05  ", ""],
        "confidence" : "high",
        "reasoning" : "x",
    })
    result = _parse_filter_json(raw)
    assert result.asr_terms == ["bún gà", "sả"]
    assert result.ocr_terms == ["37.05"]


# ── extract_filter_terms: provider availability + caching ──────────────────

def test_gemini_unavailable_returns_empty_filter_terms_without_raising(monkeypatch) :
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    result = extract_filter_terms("một câu hỏi bất kỳ", "KIS")
    assert result == FilterTerms([], [], "none", "no provider", "none", 0)


def test_cache_hit_returns_cached_result_with_cached_true_and_zero_elapsed(monkeypatch) :
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    text = json.dumps({
        "asr_terms" : ["bún gà"], "ocr_terms" : [], "confidence" : "high",
        "reasoning" : "Dish name is distinctive.",
    })
    monkeypatch.setattr(
        filter_extraction.urllib.request, "urlopen",
        lambda request, timeout=None : io.BytesIO(_gemini_body(text)),
    )

    first = extract_filter_terms("món bún gà sào xả", "KIS")
    assert first.cached is False
    assert first.provider == "gemini"

    second = extract_filter_terms("món bún gà sào xả", "KIS")
    assert second.cached is True
    assert second.elapsed_ms == 0
    assert second.asr_terms == ["bún gà"]


def test_cache_is_idempotent_second_call_hits_cache_not_network(monkeypatch) :
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    call_count = {"n" : 0}

    def fake_urlopen(request, timeout=None) :
        call_count["n"] += 1
        text = json.dumps({
            "asr_terms" : [], "ocr_terms" : [], "confidence" : "none", "reasoning" : "x",
        })
        return io.BytesIO(_gemini_body(text))

    monkeypatch.setattr(filter_extraction.urllib.request, "urlopen", fake_urlopen)

    extract_filter_terms("câu lặp lại", "QA")
    extract_filter_terms("câu lặp lại", "QA")
    extract_filter_terms("câu lặp lại", "QA")

    assert call_count["n"] == 1
