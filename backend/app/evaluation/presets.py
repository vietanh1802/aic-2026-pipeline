# backend/app/evaluation/presets.py
"""The named lists of configurations a suite runs.

"core" is the paper's ablation: one baseline plus one factor changed at a time (encoders, rerank
placement, text policy), never a full factorial. Every configuration runs on all four datasets.
"extras" holds what is worth running if time allows; the expand_gemini rung needs GEMINI_API_KEY
and is deliberately outside "core" so nothing else has to be rerun when the key appears.
"trake" runs TRAKE-N and its plain-ensemble comparison on the TRAKE queries. The text filter arms
are not configurations: they annotate the stored frames of a run.

"core2" is the paper's main run and replaces "core" + "trake": the baseline text is the LLM-prepared English
search text (Expand, Gemini), as in the paper's Section 3.3, and every other arm searches that same text unless
it is the arm that varies the text. The first real run (preset "core") used plain Google Translate as the
baseline, so many texts were longer than the encoders' context (CLIP 77 tokens) and were truncated; plain
translation is now the text ablation (C14). Raw Vietnamese (C15) is a sanity check and carries sanity = True.
The older presets stay available so a run folder made with them can still be reproduced.
"""
from __future__ import annotations

import json
from pathlib import Path

from app.evaluation.config import RunConfig

# Benchmark A is the three preliminary rounds, B the final. Newest version of each round.
DEFAULT_DATASETS = ("round1-v3", "round2-v2", "round3-v2", "final-v2")

_ALL = ["beit3", "clip", "siglip2"]
_PAIRS = (("beit3", "clip"), ("beit3", "siglip2"), ("clip", "siglip2"))


def _config(name : str, **fields) -> RunConfig :
    return RunConfig(name = name, **fields)


def _core() -> list[RunConfig] :
    singles = [_config(f"C{2 + i:02d} {m} only", models = [m]) for i, m in enumerate(_ALL)]
    pairs = [_config(f"C{5 + i:02d} {a}+{b}", models = [a, b]) for i, (a, b) in enumerate(_PAIRS)]
    singles_off = [_config(f"C{9 + i:02d} {m} only, rerank off", models = [m], rerank_mode = "off") for i, m in enumerate(_ALL)]
    return [
        # The baseline also carries the OCR and ASR annotation measures (annotation only: no ranking effect).
        _config("C01 baseline", text_filter = {"sources" : ["ocr", "asr"]}),
        *singles,
        *pairs,
        _config("C08 rerank off", rerank_mode = "off"),
        *singles_off,
        _config("C12 raw Vietnamese text", text_policy = "raw_vi"),
        _config("C13 rerank after fusion", rerank_mode = "after_fusion"),
    ]


def _extras() -> list[RunConfig] :
    pairs_off = [_config(f"C{14 + i:02d} {a}+{b}, rerank off", models = [a, b], rerank_mode = "off") for i, (a, b) in enumerate(_PAIRS)]
    return [*pairs_off, _config("C17 expand_gemini text", text_policy = "expand_gemini")]


def _trake() -> list[RunConfig] :
    """TRAKE-N (production path, K 20, g 60 s) against plain ensemble search over the whole query text,
    on the TRAKE queries only, so the two sit side by side in one report."""
    return [
        _config("T01 TRAKE-N", task_mode = "trake_n"),
        _config("T02 TRAKE queries, plain ensemble", subset = {"task_types" : ["TRAKE"]}),
    ]


def _core2() -> list[RunConfig] :
    """19 configurations x 4 datasets = 76 runs. Names carry the paper's arm codes (C01 to C15, T01, T02)."""
    def arm(name : str, **fields) -> RunConfig :
        fields.setdefault("text_policy", "expand_gemini")
        return _config(name, **fields)

    singles     = [arm(f"C{2 + i:02d} {m} only", models = [m]) for i, m in enumerate(_ALL)]
    pairs       = [arm(f"C{5 + i:02d} {a}+{b}", models = [a, b]) for i, (a, b) in enumerate(_PAIRS)]
    singles_off = [arm(f"C{9 + i:02d} {m} only, rerank off", models = [m], rerank_mode = "off") for i, m in enumerate(_ALL)]
    pairs_off   = [arm(f"C12{'abc'[i]} {a}+{b}, rerank off", models = [a, b], rerank_mode = "off") for i, (a, b) in enumerate(_PAIRS)]
    return [
        # The baseline also carries the OCR and ASR annotation measures (annotation only: no ranking effect).
        arm("C01 baseline", text_filter = {"sources" : ["ocr", "asr"]}),
        *singles,
        *pairs,
        arm("C08 rerank off", rerank_mode = "off"),
        *singles_off,
        *pairs_off,
        arm("C13 rerank after fusion (post-fusion rerank, our implementation)", rerank_mode = "after_fusion"),
        arm("C14 plain translation (translate_gtx)", text_policy = "translate_gtx"),
        arm("C15 raw Vietnamese text (sanity)", text_policy = "raw_vi", sanity = True),
        arm("T01 TRAKE-N", task_mode = "trake_n"),
        arm("T02 TRAKE queries, plain ensemble", subset = {"task_types" : ["TRAKE"]}),
    ]


def _encoder_sets() -> list[tuple[str, list[str]]] :
    """The seven encoder sets in table order: three singles, three pairs, all three."""
    return [(m, [m]) for m in _ALL] + [(f"{a}+{b}", [a, b]) for a, b in _PAIRS] + [("all three", list(_ALL))]


def _core3() -> list[RunConfig] :
    """39 configurations x 4 datasets, Benchmark B = final-v2. core2 unchanged (C01 to C15, T01, T02), plus:

    C16 to C22  plain translation, rerank OFF, all seven encoder sets: the text comparison against the rerank-off
                rows C08 to C12c is then like-for-like (core2 had plain translation only with rerank on, C14).
    C23 to C29  Expand KEYWORDS (check_units of the same Gemini answer, joined by ", "), rerank OFF, seven sets.
    C30         Expand keywords, all three encoders, rerank on.
    T01g, T01k  TRAKE-N on plain translation and on Expand keywords (TRAKE-N always reranks, see config.py).
    T02b, T02g, T02k  whole-description search on the TRAKE queries, rerank OFF, with Expand sentence, plain
                translation and Expand keywords: T02 used rerank on, which does not match the rerank-off tables.
    """
    def arm(name : str, **fields) -> RunConfig :
        fields.setdefault("text_policy", "expand_gemini")
        return _config(name, **fields)

    sets = _encoder_sets()
    gtx_off = [arm(f"C{16 + i} {label}, plain translation, rerank off", models = models, rerank_mode = "off", text_policy = "translate_gtx")
               for i, (label, models) in enumerate(sets)]
    kw_off  = [arm(f"C{23 + i} {label}, Expand keywords, rerank off", models = models, rerank_mode = "off", text_policy = "expand_keywords")
               for i, (label, models) in enumerate(sets)]
    trake = {"subset" : {"task_types" : ["TRAKE"]}, "rerank_mode" : "off"}
    return [
        *_core2(),
        *gtx_off,
        *kw_off,
        arm("C30 all three, Expand keywords, rerank on", text_policy = "expand_keywords"),
        arm("T01g TRAKE-N, plain translation", task_mode = "trake_n", text_policy = "translate_gtx"),
        arm("T01k TRAKE-N, Expand keywords", task_mode = "trake_n", text_policy = "expand_keywords"),
        arm("T02b TRAKE queries, plain ensemble, rerank off", **trake),
        arm("T02g TRAKE queries, plain ensemble, rerank off, plain translation", text_policy = "translate_gtx", **trake),
        arm("T02k TRAKE queries, plain ensemble, rerank off, Expand keywords", text_policy = "expand_keywords", **trake),
    ]


def _rerank_grid() -> list[tuple[str, dict]] :
    """The development grid of HANDOVER/rerank_selection_rule.md, declared before any grid run. R01 and R02 are
    the references (rerank off, shipped). Run on Benchmark A only."""
    from app.evaluation.config import RerankVariant

    def v(**fields) -> dict :
        return {"rerank_mode" : "variant", "rerank_variant" : RerankVariant(**fields)}

    return [
        ("R01 rerank off",                                  {"rerank_mode" : "off"}),
        ("R02 shipped rerank",                              v()),
        ("R03 stored-style neighbours, sum",                v(neighbourhood = "stored_style")),
        ("R04 stored-style neighbours, mean",               v(neighbourhood = "stored_style", aggregate = "mean")),
        ("R05 same-shot neighbours, mean",                  v(neighbourhood = "same_shot", aggregate = "mean")),
        ("R06 time window 2 s, mean",                       v(neighbourhood = "time_window", window_s = 2.0, aggregate = "mean")),
        ("R07 time window 3 s, mean",                       v(neighbourhood = "time_window", window_s = 3.0, aggregate = "mean")),
        ("R08 own + 0.5 x mean stored-style",               v(neighbourhood = "stored_style", aggregate = "mean", own_weight = 0.5)),
        ("R09 own + 1.0 x mean stored-style",               v(neighbourhood = "stored_style", aggregate = "mean", own_weight = 1.0)),
        ("R10 same-shot neighbours, sum (source method)",   v(neighbourhood = "same_shot")),
        ("R11 own + 0.5 x mean same-shot",                  v(neighbourhood = "same_shot", aggregate = "mean", own_weight = 0.5)),
        ("R12 own + 1.0 x mean same-shot",                  v(neighbourhood = "same_shot", aggregate = "mean", own_weight = 1.0)),
    ]


def _rerank_diag() -> list[RunConfig] :
    """The rerank grid, all three encoders, on both Expand texts (sentence S, keywords K): 24 configurations.
    Benchmark A ONLY (--datasets round1-v3,round2-v2,round3-v2). Which text and which variant win is decided by
    scripts/select_rerank_variant.py with the rule committed before the run."""
    configs = []
    for suffix, policy in (("S", "expand_gemini"), ("K", "expand_keywords")) :
        for name, fields in _rerank_grid() :
            code, label = name.split(" ", 1)
            configs.append(_config(f"{code}{suffix} {label}, Expand {'sentence' if suffix == 'S' else 'keywords'}", text_policy = policy, **fields))
    return configs


FROZEN_SELECTION = Path(__file__).resolve().parent / "frozen_selection.json"


def _final_table() -> list[RunConfig] :
    """The component ablation table (slot 3, Benchmarks A and B, one run). Reads the selection frozen by
    scripts/select_rerank_variant.py from frozen_selection.json, which must be committed BEFORE this runs.
    Rows: full system, no rerank, plain translation instead of Expand, each encoder removed in turn, and the other
    Expand output (sentence or keywords, whichever the full system does not search)."""
    if (not FROZEN_SELECTION.exists()) :
        raise ValueError(f"final_table needs {FROZEN_SELECTION.name}: run scripts/select_rerank_variant.py on the development run first")
    frozen = json.loads(FROZEN_SELECTION.read_text(encoding = "utf-8"))
    full = dict(frozen["config"])
    full.pop("name", None)
    full.pop("models", None)
    full.pop("text_filter", None)   # annotation only; F01 carries it, as C01 does

    def row(name : str, **change) -> RunConfig :
        return RunConfig(name = name, **{**full, **change})

    other_expand = "expand_keywords" if full.get("text_policy") == "expand_gemini" else "expand_gemini"
    rows = [
        row("F01 full system", text_filter = {"sources" : ["ocr", "asr"]}),
        # If the frozen setting is rerank off, F01 already is the row without rerank.
        *([row("F02 without rerank", rerank_mode = "off", rerank_variant = None)] if full.get("rerank_mode") != "off" else []),
        row("F03 plain translation instead of Expand", text_policy = "translate_gtx"),
        row("F04 without BEiT-3", models = ["clip", "siglip2"]),
        row("F05 without OpenCLIP", models = ["beit3", "siglip2"]),
        row("F06 without SigLIP2", models = ["beit3", "clip"]),
        row(f"F07 the other Expand output ({'keywords' if other_expand == 'expand_keywords' else 'sentence'})", text_policy = other_expand),
    ]
    return rows


PRESETS = {
    "core" : _core, "extras" : _extras, "trake" : _trake, "core2" : _core2, "core3" : _core3,
    "rerank_diag" : _rerank_diag, "final_table" : _final_table,
}


def preset_configs(name : str) -> list[RunConfig] :
    """A fresh list of RunConfig for a preset name, or several joined with commas ("core,extras")."""
    configs : list[RunConfig] = []
    for part in name.split(",") :
        if (part.strip() not in PRESETS) :
            raise ValueError(f"Unknown preset {part!r}; choose from {sorted(PRESETS)}")
        configs.extend(PRESETS[part.strip()]())
    return configs
