# backend/tests/test_evaluation_core2.py
"""Preset core2: the paper's main run with the LLM-prepared (Expand) text as the baseline.

Pinned here: which 19 configurations it holds and what text each one searches, that the sanity check is
flagged and kept out of the LaTeX paper table, and that fetching the Expand texts either records every output
(eng_query, check_units, provider) or stops with every failure listed, never falling back to another
provider.
"""
from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest

from app import expansion
from app.evaluation import report, text_cache
from app.evaluation.config import config_hash
from app.evaluation.presets import PRESETS, preset_configs
from app.evaluation.seed import SEEDS_DIR, import_seed

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"


def _by_code() -> dict[str, object] :
    return {c.name.split()[0] : c for c in preset_configs("core2")}


def test_core2_has_the_19_arms_of_the_paper_with_expand_as_the_baseline_text() :
    configs = _by_code()
    assert list(configs) == ["C01", "C02", "C03", "C04", "C05", "C06", "C07", "C08", "C09", "C10", "C11", "C12a", "C12b", "C12c", "C13", "C14", "C15", "T01", "T02"]
    assert len({config_hash(c) for c in configs.values()}) == 19                 # every arm is a different measurement
    for code, config in configs.items() :
        expected = {"C14" : "translate_gtx", "C15" : "raw_vi"}.get(code, "expand_gemini")
        assert config.text_policy == expected, code
        assert config.sanity == (code == "C15"), code
    assert configs["C01"].models == ["beit3", "clip", "siglip2"] and configs["C01"].rerank_mode == "per_model"
    assert configs["C01"].text_filter.sources == ["ocr", "asr"]                  # the baseline carries the annotation measures
    assert [configs[c].rerank_mode for c in ("C08", "C09", "C10", "C11", "C12a", "C12b", "C12c", "C13")] == ["off"] * 7 + ["after_fusion"]
    assert [configs[c].models for c in ("C12a", "C12b", "C12c")] == [["beit3", "clip"], ["beit3", "siglip2"], ["clip", "siglip2"]]
    assert configs["T01"].task_mode == "trake_n" and configs["T02"].subset.task_types == ["TRAKE"]
    assert len(PRESETS["core2"]()) * 4 == 76


def test_older_presets_still_resolve_with_the_gtx_baseline() :
    core = preset_configs("core")
    assert core[0].name == "C01 baseline" and core[0].text_policy == "translate_gtx" and not any(c.sanity for c in core)
    assert [c.name.split()[0] for c in preset_configs("trake")] == ["T01", "T02"]


def test_preflight_of_core2_needs_the_key_for_expand_but_not_for_the_gtx_arm(conn, monkeypatch) :
    import_seed(conn, SEEDS_DIR / "round1-v3.json")
    rows = text_cache.query_rows(conn, "round1-v3")
    n_events = sum(len(json.loads(r["trake_events_json"] or "[]")) for r in rows)
    monkeypatch.delenv("GEMINI_API_KEY", raising = False)
    report_ = text_cache.preflight(conn, preset_configs("core2"), ["round1-v3"])
    assert report_["blocked"] and report_["blocked_policies"] == ["expand_gemini"]
    assert report_["missing_by_policy"] == {"expand_gemini" : len(rows) + n_events, "translate_gtx" : len(rows)}
    monkeypatch.setenv("GEMINI_API_KEY", "not-a-real-key")
    assert not text_cache.preflight(conn, preset_configs("core2"), ["round1-v3"])["blocked"]


def test_latex_paper_table_leaves_the_sanity_arm_out_and_the_sanity_table_shows_it() :
    def row(config, hit, sanity) :
        return {"config" : config, "benchmark" : "A", "flags" : "all", "task_type" : "all", "prefix" : "all",
                "hit_at_1" : hit, "r_at_5" : hit, "r_at_10" : hit, "mrr" : hit, "sanity" : sanity}

    table = [row("C01 baseline", 0.5, False), row("C14 plain", 0.3, False), row("C15 raw (sanity)", 0.01, True)]
    paper = report.latex_table(table, "A")
    assert "C01" in paper and "C14" in paper and "C15" not in paper
    shown = report.latex_table(table, "A", configs = ["C01 baseline", "C15 raw (sanity)"])
    assert "C15" in shown and "C14" not in shown


# ─── fetching the Expand texts ─────────────────────────────────────────────

@pytest.fixture()
def suite_script(monkeypatch) :
    monkeypatch.syspath_prepend(str(SCRIPTS))
    sys.modules.pop("run_ablation_suite", None)
    return importlib.import_module("run_ablation_suite")


def _missing_expand(conn) :
    import_seed(conn, SEEDS_DIR / "round1-v3.json")
    config = next(c for c in preset_configs("core2") if c.name.startswith("C01"))
    return text_cache.preflight(conn, [config], ["round1-v3"])["_missing_items"]


def test_expand_outputs_are_recorded_and_exported(conn, tmp_path, suite_script, monkeypatch) :
    missing = _missing_expand(conn)

    def gemini(text, task_type) :
        return {"eng_query" : f"English for {text[ : 10]}", "check_units" : ["person", "table"], "translated_query" : None, "provider" : "gemini", "elapsed_ms" : 5}

    monkeypatch.setattr(expansion, "expand_query", gemini)
    cache_file = tmp_path / "text_cache.jsonl"
    messages : list[str] = []
    suite_script.fetch_missing(conn, missing, messages.append, cache_file)

    entries = [json.loads(line) for line in cache_file.read_text(encoding = "utf-8").splitlines()]
    assert len(entries) == len(missing)
    first = json.loads(entries[0]["output_json"])
    assert entries[0]["provider"] == "gemini" and first["check_units"] == ["person", "table"] and first["eng_query"].startswith("English for")
    # Replay returns the recorded eng_query and checklist.
    cached = text_cache.get_text(conn, "expand_gemini", missing[0].text, missing[0].task_type)
    assert cached.text == first["eng_query"] and cached.check_units == ["person", "table"] and cached.provider == "gemini"


def test_a_non_gemini_expand_answer_stops_the_suite_and_lists_every_failure(conn, tmp_path, suite_script, monkeypatch) :
    missing = _missing_expand(conn)
    monkeypatch.setattr(expansion, "expand_query", lambda text, task_type : {
        "eng_query" : "from the fallback", "check_units" : [], "provider" : "ollama", "elapsed_ms" : 5})
    cache_file = tmp_path / "text_cache.jsonl"
    messages : list[str] = []
    with pytest.raises(SystemExit) as stop :
        suite_script.fetch_missing(conn, missing, messages.append, cache_file)
    assert stop.value.code == 3
    text = "\n".join(messages)
    assert "PREFETCH FAILED" in text and "'ollama'" in text and "check_expand.py" in text
    assert text.count("expand_gemini round1-v3/") == 5                          # five in a row, then it stops asking the provider
    assert cache_file.exists() and cache_file.read_text(encoding = "utf-8") == ""     # nothing from the fallback was recorded
    assert text_cache.lookup(conn, text_cache.make_key("expand_gemini", missing[0].text, missing[0].task_type)) is None


def test_a_failed_attempt_keeps_what_it_fetched_for_the_next_start(conn, tmp_path, suite_script, monkeypatch) :
    missing = _missing_expand(conn)
    calls = {"n" : 0}

    def flaky(text, task_type) :
        calls["n"] += 1
        if (calls["n"] <= 3) :
            return {"eng_query" : f"ok {calls['n']}", "check_units" : [], "provider" : "gemini", "elapsed_ms" : 1}
        return {"eng_query" : "", "check_units" : [], "provider" : "none", "elapsed_ms" : 1, "error" : "No expansion provider available (Gemini unreachable)"}

    monkeypatch.setattr(expansion, "expand_query", flaky)
    cache_file = tmp_path / "text_cache.jsonl"
    with pytest.raises(SystemExit) :
        suite_script.fetch_missing(conn, missing, lambda message : None, cache_file)
    assert len(cache_file.read_text(encoding = "utf-8").splitlines()) == 3
    # A fresh database (a new run folder) imports the file and only misses the rest.
    fresh = text_cache.import_jsonl(conn, cache_file.read_text(encoding = "utf-8"))
    assert fresh == {"inserted" : 0, "skipped" : 3}


# ─── prefetching the Expand texts without loading anything ──────────────────

def _run_prefetch(monkeypatch, tmp_path, *extra : str) -> tuple[int, Path] :
    monkeypatch.syspath_prepend(str(SCRIPTS))
    sys.modules.pop("prefetch_text_cache", None)
    prefetch = importlib.import_module("prefetch_text_cache")
    out = tmp_path / "text_cache.jsonl"
    monkeypatch.setattr(sys, "argv", ["prefetch_text_cache.py", "--preset", "core2", "--policy", "expand_gemini", "--datasets", "round1-v3", "--out", str(out), *extra])
    return prefetch.main(), out


def test_prefetch_expand_writes_the_file_the_suite_imports(monkeypatch, tmp_path) :
    monkeypatch.setenv("GEMINI_API_KEY", "not-a-real-key")
    monkeypatch.setattr(expansion, "expand_query", lambda text, task_type : {
        "eng_query" : f"English {task_type}", "check_units" : ["a"], "translated_query" : None, "provider" : "gemini", "elapsed_ms" : 1})
    code, out = _run_prefetch(monkeypatch, tmp_path)
    entries = [json.loads(line) for line in out.read_text(encoding = "utf-8").splitlines()]
    expand = [e for e in entries if e["policy_id"] == "expand_v1"]       # the file also carries the committed gtx seed texts
    assert code == 0 and len(expand) == 27 and all(e["provider"] == "gemini" for e in expand)    # 24 queries and 3 TRAKE events of round1-v3
    assert {json.loads(e["output_json"])["check_units"][0] for e in expand} == {"a"}


def test_prefetch_expand_without_a_key_says_blocked_and_writes_nothing(monkeypatch, tmp_path, capsys) :
    monkeypatch.delenv("GEMINI_API_KEY", raising = False)
    code, out = _run_prefetch(monkeypatch, tmp_path)
    assert code == 2 and not out.exists() and "BLOCKED" in capsys.readouterr().out
