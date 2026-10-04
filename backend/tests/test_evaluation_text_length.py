# backend/tests/test_evaluation_text_length.py
"""Token counts of the searched text against each encoder's context limit.

The real tokenizers are not loaded here (they need open_clip, beit3.spm and the SigLIP2 tokenizer files). A fake
counter per encoder stands in, and the fallback to a word-count estimate is exercised with loaders that fail.
"""
from __future__ import annotations

import math

import pytest

from app.evaluation import text_length


@pytest.fixture()
def fake_counters(monkeypatch) :
    """One token per word plus two special tokens, limits as in production."""
    monkeypatch.setattr(text_length, "_LOADED", {m : ((lambda text : len(text.split()) + 2), text_length.LIMITS[m]) for m in text_length.MODELS})


def test_over_limit_and_truncated_differ_for_beit3(fake_counters) :
    result = text_length.measure(["word " * 70])          # 72 tokens: over BEiT-3's and SigLIP2's 64, under CLIP's 77
    assert result["words"] == 70 and result["n_texts"] == 1
    assert (result["beit3"]["over_limit"], result["beit3"]["truncated"]) == (True, False)      # the backend does not cut BEiT-3 text
    assert (result["siglip2"]["over_limit"], result["siglip2"]["truncated"]) == (True, True)
    assert (result["clip"]["over_limit"], result["clip"]["truncated"], result["clip"]["tokens"]) == (False, False, 72)
    assert all(result[m]["method"] == "tokenizer" for m in text_length.MODELS)


def test_the_boundary_is_inclusive_of_the_limit(fake_counters) :
    assert not text_length.measure(["w " * 62])["siglip2"]["over_limit"]       # 64 tokens fit
    assert text_length.measure(["w " * 63])["siglip2"]["over_limit"]           # 65 do not


def test_several_texts_report_the_longest_and_how_many_are_over(fake_counters) :
    result = text_length.measure(["short text", "word " * 80, "word " * 66])    # a TRAKE-N query: one text per event
    assert result["clip"]["tokens"] == 82 and result["clip"]["n_over"] == 1 and result["siglip2"]["n_over"] == 2
    assert result["n_texts"] == 3 and result["words"] == 80


def test_a_missing_tokenizer_falls_back_to_a_labelled_estimate(monkeypatch, capsys) :
    def missing() :
        raise FileNotFoundError("/idx/beit3.spm")

    monkeypatch.setattr(text_length, "_LOADED", {})
    monkeypatch.setattr(text_length, "_LOADERS", {**text_length._LOADERS, "beit3" : missing})
    count, limit, method = text_length.counter("beit3")
    assert method == "estimate: FileNotFoundError: /idx/beit3.spm" and limit == 64
    assert count("one two three four five") == math.ceil(5 * text_length.TOKENS_PER_WORD) + 2
    assert "word-count estimate" in capsys.readouterr().out                    # said once, never silent
    text_length.counter("beit3")
    assert capsys.readouterr().out == ""
