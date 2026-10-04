# scripts/ablation_analysis/facts.py
"""Numbers that are NOT in the run folder: supplied by the team, with their source, so a table that uses
one can say where it came from. Replace them with --facts <json> when they are measured again."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# Measured by the team on the live EC2 container (CPU only, 8 vCPU), one query, through the live endpoint.
LIVE_LATENCY_S = {
    "all three encoders, rerank on (warm)" : 1.58,
    "BEiT-3 alone (warm)" : 0.28,
    "OpenCLIP alone (warm)" : 0.76,
    "SigLIP2 alone (warm)" : 0.54,
    "all three encoders, rerank off (warm)" : 1.02,
    "first call after a restart (cold)" : 12.9,
}

# What the paper draft says (sections 1 to 3), to be checked against the corpus features.
PAPER_DRAFT = {"videos" : 1480, "hours" : 323.8, "keyframes" : 983931}

# Index state measured on EC2 on 2026-10-04.
LOADED_INDEX = {
    "videos" : 1487, "keyframes" : 991469, "frames_per_prefix" : {"L" : 360531, "M" : 336876, "N" : 201221, "S" : 92841},
    "neighbors_clip_empty_L" : (263895, 360531), "neighbors_clip_empty_MNS" : 0,
}

HARDWARE = "CPU only, 8 vCPU, 61 GB RAM, no GPU (AWS EC2 r6i.2xlarge)"


def load_facts(path : Path | None) -> dict[str, Any] :
    facts : dict[str, Any] = {"live_latency_s" : dict(LIVE_LATENCY_S), "paper_draft" : dict(PAPER_DRAFT), "loaded_index" : dict(LOADED_INDEX), "hardware" : HARDWARE}
    if (path) :
        facts.update(json.loads(Path(path).read_text(encoding = "utf-8")))
    return facts
