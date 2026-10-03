# backend/app/evaluation/cues.py
"""Labelled text cues: the terms an operator could type into the ASR or OCR filter for a query.

A cue sidecar lives next to the seeds, never inside them (a shipped seed cannot be edited):

    seeds/cues/<dataset_version>.cues.csv
    dataset_version,query_key,source,term,cue_type,derivable_from_query,reviewer,status,note

  source                 ocr | asr
  cue_type               visible_name | number | sign | spoken_phrase (filled in at review)
  derivable_from_query   yes | no | unknown: could an operator reading only the query text have chosen it
  status                 draft         drafted, not reviewed, not used for measures
                         confirmed     reviewed and accepted: the only rows that count as labelled cues
                         legacy_leaky  the seed's old filter_terms (rounds 1 to 3): they were audited
                                       against the real OCR/ASR engines, so a measure built on them is an
                                       UPPER BOUND and is always reported as a separate kind

Terms must come from the query text only, never from the OCR or ASR content of the reference video.
scripts/draft_cues.py drafts the file that way; the reviewer then edits it in a spreadsheet.
"""
from __future__ import annotations

import csv
from pathlib import Path

CUES_DIR = Path(__file__).resolve().parent / "seeds" / "cues"
FIELDS = ("dataset_version", "query_key", "source", "term", "cue_type", "derivable_from_query", "reviewer", "status", "note")

# Which sidecar statuses form which measured kind. draft rows form none.
KINDS = {"confirmed" : "confirmed", "legacy_leaky" : "legacy_leaky"}


def cues_path(dataset_version : str, directory : Path = CUES_DIR) -> Path :
    return directory / f"{dataset_version}.cues.csv"


def read_rows(dataset_version : str, directory : Path = CUES_DIR) -> list[dict[str, str]] :
    path = cues_path(dataset_version, directory)
    if (not path.exists()) :
        return []
    with open(path, encoding = "utf-8", newline = "") as handle :
        return list(csv.DictReader(handle))


def load_cues(dataset_version : str, directory : Path = CUES_DIR) -> dict[str, dict[str, dict[str, list[str]]]] :
    """{query_key: {kind: {"ocr": [terms], "asr": [terms]}}} for the confirmed and legacy_leaky rows."""
    cues : dict[str, dict[str, dict[str, list[str]]]] = {}
    for row in read_rows(dataset_version, directory) :
        kind = KINDS.get(row["status"].strip())
        term = row["term"].strip()
        if (kind is None or not term or row["source"].strip() not in ("ocr", "asr")) :
            continue
        by_source = cues.setdefault(row["query_key"], {}).setdefault(kind, {"ocr" : [], "asr" : []})
        if (term not in by_source[row["source"].strip()]) :
            by_source[row["source"].strip()].append(term)
    return cues


def write_rows(dataset_version : str, rows : list[dict[str, str]], directory : Path = CUES_DIR) -> Path :
    path = cues_path(dataset_version, directory)
    path.parent.mkdir(parents = True, exist_ok = True)
    with open(path, "w", encoding = "utf-8", newline = "") as handle :
        writer = csv.DictWriter(handle, fieldnames = FIELDS, lineterminator = "\n")
        writer.writeheader()
        for row in rows :
            writer.writerow({field : row.get(field, "") for field in FIELDS})
    return path
