# scripts/draft_cues.py
"""Draft the cue sidecar backend/app/evaluation/seeds/cues/<dataset_version>.cues.csv.

Cues are the ASR or OCR terms an operator could type into the filter for a query, derived from the
QUERY TEXT ONLY, never from the OCR or ASR content of the reference video (that would leak the answer
into the measure). Two sources of drafts:

  seed filter_terms  (rounds 1 to 3, no key needed)  written as status legacy_leaky. They were audited
                     against the real OCR/ASR engines (commit 6c90853), so any measure built on them is
                     an UPPER BOUND and is reported as its own kind.
  extract_filter_terms(query_vi, task_type)  (needs GEMINI_API_KEY; the only input is the query text)
                     written as status draft, for datasets whose seed has no filter_terms (final-v1) or
                     when --llm is given.

Rows already in the CSV are kept as they are: a reviewer's status, cue_type and notes are never
overwritten, only missing (query_key, source, term) rows are appended, so rerunning is safe. Review in a
spreadsheet: set cue_type and derivable_from_query, and change status draft to confirmed. Only confirmed
rows count as labelled cues.

    python scripts/draft_cues.py --datasets round1-v3,round2-v2,round3-v2      # legacy_leaky, no key
    python scripts/draft_cues.py --datasets final-v1                           # LLM drafts, needs the key
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "backend"))

if hasattr(sys.stdout, "reconfigure") :
    sys.stdout.reconfigure(encoding = "utf-8")

from app.evaluation import cues  # noqa: E402
from app.evaluation.presets import DEFAULT_DATASETS  # noqa: E402
from app.evaluation.seed import SEEDS_DIR  # noqa: E402


def terms_of(entries) -> list[str] :
    """Plain strings (round 1) or {"concept", "terms": [...]} groups (rounds 2 and 3) as a flat list."""
    flat : list[str] = []
    for entry in entries or [] :
        flat.extend([entry] if isinstance(entry, str) else entry.get("terms", []))
    return [t.strip() for t in flat if t and t.strip()]


def legacy_rows(dataset : str, query : dict) -> list[dict[str, str]] :
    filter_terms = query.get("filter_terms") or {}
    return [
        {"dataset_version" : dataset, "query_key" : query["id"], "source" : source, "term" : term, "cue_type" : "",
         "derivable_from_query" : "unknown", "reviewer" : "legacy", "status" : "legacy_leaky",
         "note" : f"seed filter_terms, confidence {filter_terms.get('confidence')}"}
        for source in ("asr", "ocr") for term in terms_of(filter_terms.get(f"{source}_terms"))
    ]


def llm_rows(dataset : str, query : dict) -> list[dict[str, str]] :
    from app.filter_extraction import extract_filter_terms

    extracted = extract_filter_terms(query["query_vi"], query["task_type"])
    return [
        {"dataset_version" : dataset, "query_key" : query["id"], "source" : source, "term" : term, "cue_type" : "",
         "derivable_from_query" : "", "reviewer" : "", "status" : "draft", "note" : f"LLM draft, confidence {extracted.confidence}"}
        for source, terms in (("asr", extracted.asr_terms), ("ocr", extracted.ocr_terms)) for term in terms
    ]


def main() -> int :
    parser = argparse.ArgumentParser(description = __doc__.split("\n")[0])
    parser.add_argument("--datasets", default = ",".join(DEFAULT_DATASETS))
    parser.add_argument("--llm", action = "store_true", help = "draft with the LLM even where the seed has filter_terms")
    args = parser.parse_args()

    for dataset in [d.strip() for d in args.datasets.split(",") if d.strip()] :
        seed = json.loads((SEEDS_DIR / f"{dataset}.json").read_text(encoding = "utf-8"))
        existing = cues.read_rows(dataset)
        have = {(r["query_key"], r["source"], r["term"]) for r in existing}
        added = []
        for query in seed["queries"] :
            drafted = llm_rows(dataset, query) if (args.llm or "filter_terms" not in query) else legacy_rows(dataset, query)
            added.extend(r for r in drafted if (r["query_key"], r["source"], r["term"]) not in have)
        path = cues.write_rows(dataset, existing + added)
        print(f"{dataset}: {len(existing)} rows kept, {len(added)} added -> {path}")
    return 0


if (__name__ == "__main__") :
    raise SystemExit(main())
