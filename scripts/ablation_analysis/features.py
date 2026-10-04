# scripts/ablation_analysis/features.py
"""Corpus features written by scripts/dump_corpus_features.py (videos.csv, shots.csv, frames_ref.csv,
index_files.csv, corpus_totals.json). Optional: every analysis that needs them says so and is skipped
without them."""
from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class Features :
    folder : Path
    videos : dict[str, dict[str, Any]] = field(default_factory = dict)
    shots : list[dict[str, Any]] = field(default_factory = list)
    frames_ref : dict[str, list[tuple[str, int, int]]] = field(default_factory = dict)   # video -> [(name, shot, frame_idx)]
    index_files : list[dict[str, Any]] = field(default_factory = list)
    totals : dict[str, Any] = field(default_factory = dict)
    synthetic : bool = False

    def shots_by_video(self) -> dict[str, list[dict[str, Any]]] :
        grouped : dict[str, list[dict[str, Any]]] = {}
        for shot in self.shots :
            grouped.setdefault(shot["video"], []).append(shot)
        return grouped


def _rows(path : Path) -> list[dict[str, str]] :
    if (not path.exists()) :
        return []
    with open(path, encoding = "utf-8", newline = "") as handle :
        return list(csv.DictReader(line for line in handle if not line.startswith("#")))


def _number(value : str) -> float | int | str :
    try :
        number = float(value)
    except ValueError :
        return value
    return int(number) if number.is_integer() and "." not in value else number


def load_features(folder : Path | None) -> Features | None :
    if (folder is None) :
        return None
    folder = Path(folder)
    if (not (folder / "videos.csv").exists()) :
        raise FileNotFoundError(f"{folder / 'videos.csv'} not found: run scripts/dump_corpus_features.py first")
    features = Features(folder = folder)
    for row in _rows(folder / "videos.csv") :
        features.videos[row["video"]] = {k : (v if k in ("video", "prefix") else _number(v)) for k, v in row.items()}
    features.shots = [{k : (v if k == "video" else _number(v)) for k, v in row.items()} for row in _rows(folder / "shots.csv")]
    for row in _rows(folder / "frames_ref.csv") :
        features.frames_ref.setdefault(row["video"], []).append((row["name"], int(row["shot"]), int(row["frame_idx"])))
    features.index_files = [{"name" : r["name"], "bytes" : int(r["bytes"])} for r in _rows(folder / "index_files.csv")]
    if ((folder / "corpus_totals.json").exists()) :
        features.totals = json.loads((folder / "corpus_totals.json").read_text(encoding = "utf-8"))
        features.synthetic = bool(features.totals.get("synthetic"))
    return features
