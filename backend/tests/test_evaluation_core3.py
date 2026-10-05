# backend/tests/test_evaluation_core3.py
"""Preset core3, the Expand keyword text, and the final-v2 seed.

Pinned here: core3 = core2 plus the rerank-off text arms (plain translation and Expand keywords for all seven
encoder sets) and the TRAKE arms on one text policy each; expand_keywords searches the check_units of the SAME
recorded Gemini answer as expand_gemini and never asks for a call of its own; final-v2 differs from final-v1 only
in the shortened query_vi of KIS and QA, each a prefix of the original.
"""
from __future__ import annotations

import json

import pytest

from app.evaluation import text_cache
from app.evaluation.config import config_hash
from app.evaluation.presets import DEFAULT_DATASETS, preset_configs
from app.evaluation.seed import SEEDS_DIR, import_seed

SETS = [["beit3"], ["clip"], ["siglip2"], ["beit3", "clip"], ["beit3", "siglip2"], ["clip", "siglip2"], ["beit3", "clip", "siglip2"]]


def _by_code() -> dict[str, object] :
    return {c.name.split()[0] : c for c in preset_configs("core3")}


def test_core3_is_core2_plus_the_rerank_off_text_arms_and_the_trake_arms() :
    configs = _by_code()
    core2 = [c.name.split()[0] for c in preset_configs("core2")]
    assert list(configs)[ : len(core2)] == core2
    assert list(configs)[len(core2) : ] == [f"C{n}" for n in range(16, 31)] + ["T01g", "T01k", "T02b", "T02g", "T02k"]
    assert len(configs) == 39 and len({config_hash(c) for c in configs.values()}) == 39
    for i, models in enumerate(SETS) :
        gtx, kw = configs[f"C{16 + i}"], configs[f"C{23 + i}"]
        assert (gtx.models, gtx.rerank_mode, gtx.text_policy) == (models, "off", "translate_gtx")
        assert (kw.models, kw.rerank_mode, kw.text_policy) == (models, "off", "expand_keywords")
    assert (configs["C30"].rerank_mode, configs["C30"].text_policy) == ("per_model", "expand_keywords")
    assert [configs[c].text_policy for c in ("T01", "T01g", "T01k")] == ["expand_gemini", "translate_gtx", "expand_keywords"]
    assert all(configs[c].task_mode == "trake_n" and configs[c].rerank_mode == "per_model" for c in ("T01", "T01g", "T01k"))
    for code, policy in (("T02b", "expand_gemini"), ("T02g", "translate_gtx"), ("T02k", "expand_keywords")) :
        assert configs[code].subset.task_types == ["TRAKE"] and configs[code].rerank_mode == "off" and configs[code].text_policy == policy


def test_benchmark_b_is_final_v2_by_default() :
    assert DEFAULT_DATASETS == ("round1-v3", "round2-v2", "round3-v2", "final-v2")


def _record(conn, item, units) :
    output = {"eng_query" : f"sentence for {item.query_key}", "check_units" : units, "translated_query" : None}
    text_cache.store(conn, text_cache.make_key("expand_gemini", item.text, item.task_type), item.text, output, "gemini")


def test_expand_keywords_reads_the_same_answer_as_expand_gemini(conn, monkeypatch) :
    import_seed(conn, SEEDS_DIR / "round1-v3.json")
    monkeypatch.delenv("GEMINI_API_KEY", raising = False)
    sentence = next(c for c in preset_configs("core3") if c.name.startswith("C08 "))
    keywords = next(c for c in preset_configs("core3") if c.name.startswith("C29 "))
    needed = text_cache.preflight(conn, [sentence], ["round1-v3"])["needed"]
    both = text_cache.preflight(conn, [sentence, keywords], ["round1-v3"])
    assert both["needed"] == needed and both["missing_by_policy"] == {"expand_gemini" : needed}   # no extra text, no extra call

    for item in both["_missing_items"] :
        _record(conn, item, ["red car", " bridge ", ""])
    assert not text_cache.preflight(conn, [keywords], ["round1-v3"])["missing"]
    item = both["_missing_items"][0]
    kw = text_cache.get_text(conn, "expand_keywords", item.text, item.task_type)
    se = text_cache.get_text(conn, "expand_gemini", item.text, item.task_type)
    assert kw.text == "red car, bridge" and se.text == f"sentence for {item.query_key}"
    assert kw.digest == se.digest and kw.provider == "gemini"


def test_expand_keywords_refuses_an_answer_without_keywords(conn) :
    import_seed(conn, SEEDS_DIR / "round1-v3.json")
    keywords = next(c for c in preset_configs("core3") if c.name.startswith("C29 "))
    item = text_cache.preflight(conn, [keywords], ["round1-v3"])["_missing_items"][0]
    _record(conn, item, [])
    with pytest.raises(text_cache.TextCacheMiss) :
        text_cache.get_text(conn, "expand_keywords", item.text, item.task_type)


def test_final_v2_shortens_only_the_kis_and_qa_text_of_final_v1() :
    v1 = json.loads((SEEDS_DIR / "final-v1.json").read_text(encoding = "utf-8"))
    v2 = json.loads((SEEDS_DIR / "final-v2.json").read_text(encoding = "utf-8"))
    q1, q2 = v1["queries"], v2["queries"]
    assert [q["id"] for q in q1] == [q["id"] for q in q2] and len(q2) == 28
    changed = 0
    for a, b in zip(q1, q2) :
        assert {k : v for k, v in a.items() if k not in ("query_vi", "notes")} == {k : v for k, v in b.items() if k not in ("query_vi", "notes")}, a["id"]
        if (a["task_type"] == "TRAKE") :
            assert a["query_vi"] == b["query_vi"], a["id"]
            continue
        assert a["query_vi"].startswith(b["query_vi"].rstrip(" .")), a["id"]
        changed += a["query_vi"] != b["query_vi"]
    assert changed == 25
