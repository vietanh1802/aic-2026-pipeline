# backend/app/evaluation/presets.py
"""The named lists of configurations a suite runs.

"core" is the paper's ablation: one baseline plus one factor changed at a time (encoders, rerank
placement, text policy), never a full factorial. Every configuration runs on all four datasets.
"extras" holds what is worth running if time allows; the expand_gemini rung needs GEMINI_API_KEY
and is deliberately outside "core" so nothing else has to be rerun when the key appears.
"trake" runs TRAKE-N and its plain-ensemble comparison on the TRAKE queries. The text filter arms
are not configurations: they annotate the stored frames of a run.
"""
from __future__ import annotations

from app.evaluation.config import RunConfig

# Benchmark A is the three preliminary rounds, B the final. Newest version of each round.
DEFAULT_DATASETS = ("round1-v3", "round2-v2", "round3-v2", "final-v1")

_ALL = ["beit3", "clip", "siglip2"]
_PAIRS = (("beit3", "clip"), ("beit3", "siglip2"), ("clip", "siglip2"))


def _config(name : str, **fields) -> RunConfig :
    return RunConfig(name = name, **fields)


def _core() -> list[RunConfig] :
    singles = [_config(f"C{2 + i:02d} {m} only", models = [m]) for i, m in enumerate(_ALL)]
    pairs = [_config(f"C{5 + i:02d} {a}+{b}", models = [a, b]) for i, (a, b) in enumerate(_PAIRS)]
    singles_off = [_config(f"C{9 + i:02d} {m} only, rerank off", models = [m], rerank_mode = "off") for i, m in enumerate(_ALL)]
    return [
        _config("C01 baseline"),
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


PRESETS = {"core" : _core, "extras" : _extras, "trake" : _trake}


def preset_configs(name : str) -> list[RunConfig] :
    """A fresh list of RunConfig for a preset name, or several joined with commas ("core,extras")."""
    configs : list[RunConfig] = []
    for part in name.split(",") :
        if (part.strip() not in PRESETS) :
            raise ValueError(f"Unknown preset {part!r}; choose from {sorted(PRESETS)}")
        configs.extend(PRESETS[part.strip()]())
    return configs
