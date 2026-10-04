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


PRESETS = {"core" : _core, "extras" : _extras, "trake" : _trake, "core2" : _core2}


def preset_configs(name : str) -> list[RunConfig] :
    """A fresh list of RunConfig for a preset name, or several joined with commas ("core,extras")."""
    configs : list[RunConfig] = []
    for part in name.split(",") :
        if (part.strip() not in PRESETS) :
            raise ValueError(f"Unknown preset {part!r}; choose from {sorted(PRESETS)}")
        configs.extend(PRESETS[part.strip()]())
    return configs
