# -*- coding: utf-8 -*-
"""
Offline annotation: run extract_filter_terms() over a benchmark seed file and
write the results back into each query as a "filter_terms" field.

Idempotent -- a query that already carries a non-null "filter_terms" is
skipped, so re-running the script never overwrites a result already reviewed.
Only that one field is added/updated; schema_version, dataset, and
reference_set are left untouched (see CLAUDE.md: a content change to a
shipped seed needs a new dataset version, not an edit in place -- this script
only appends annotation metadata, which is not the kind of content change
that rule is about, but the script still never touches dataset.version).

Usage:
    python scripts/generate_filter_terms.py --seed backend/app/evaluation/seeds/round1-v3.json
    python scripts/generate_filter_terms.py            # prompts for a seed file
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SEEDS_DIR = REPO_ROOT / "backend" / "app" / "evaluation" / "seeds"

sys.path.insert(0, str(REPO_ROOT / "backend"))
from app.filter_extraction import extract_filter_terms  # noqa: E402

if hasattr(sys.stdout, "reconfigure") :
    sys.stdout.reconfigure(encoding="utf-8")

# Gap between successive Gemini calls made BY THIS SCRIPT, on top of
# extract_filter_terms()'s own _wait_for_rate_limit() pacing (translation.py,
# also 4.5s). Belt and suspenders: if this script is ever invoked in a context
# that bypasses that shared pacing queue, it still self-paces.
_CALL_GAP_S = 4.5


def _load_env_file() -> None :
    """Load backend/.env into the environment if GEMINI_API_KEY isn't already
    set, so the script runs from the repo root without manual export."""
    if os.environ.get("GEMINI_API_KEY") :
        return
    env_path = REPO_ROOT / "backend" / ".env"
    if not env_path.exists() :
        return
    try :
        from dotenv import load_dotenv
        load_dotenv(env_path)
        return
    except ImportError :
        pass
    # Manual fallback: simple KEY=VALUE lines, quotes stripped.
    with open(env_path, encoding="utf-8") as f :
        for line in f :
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line :
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ :
                os.environ[key] = value


def _discover_current_seed_files() -> list[Path] :
    """One file per round: for each dataset.slug, the file carrying the
    HIGHEST dataset.version (round1-v2.json superseded by round1-v3.json,
    etc.) -- not a hardcoded filename list, so a future round/version just
    works."""
    best : dict[str, tuple[str, Path]] = {}
    for path in sorted(SEEDS_DIR.glob("*.json")) :
        try :
            with open(path, encoding="utf-8") as f :
                dataset = json.load(f).get("dataset") or {}
        except (json.JSONDecodeError, OSError) :
            continue
        slug = dataset.get("slug")
        version = dataset.get("version")
        if not slug or not version :
            continue
        current = best.get(slug)
        if current is None or version > current[0] :
            best[slug] = (version, path)
    return [path for _, path in sorted(best.values(), key=lambda pair : pair[1].name)]


def _prompt_for_seed_file() -> Path :
    candidates = _discover_current_seed_files()
    if not candidates :
        print(f"ERROR: no seed files found under {SEEDS_DIR}", file=sys.stderr)
        sys.exit(1)
    print("Choose a seed file:")
    for i, path in enumerate(candidates, 1) :
        print(f"  {i}. {path.name}")
    choice = input(f"Enter 1-{len(candidates)}: ").strip()
    try :
        index = int(choice) - 1
        if not (0 <= index < len(candidates)) :
            raise ValueError
    except ValueError :
        print("ERROR: invalid selection", file=sys.stderr)
        sys.exit(1)
    return candidates[index]


def _format_terms(terms : list[str]) -> str :
    return ", ".join(terms) if terms else "—"


def main() -> int :
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=Path, default=None,
                         help="Path to a seed JSON file. Omit to be prompted.")
    args = parser.parse_args()

    _load_env_file()

    seed_path = args.seed if args.seed is not None else _prompt_for_seed_file()
    if not seed_path.exists() :
        print(f"ERROR: seed file not found: {seed_path}", file=sys.stderr)
        return 1

    with open(seed_path, encoding="utf-8") as f :
        seed = json.load(f)

    queries = seed.get("queries", [])
    processed = 0
    skipped = 0
    failed = 0
    confidence_counts = {"high" : 0, "medium" : 0, "none" : 0}

    for query in queries :
        if query.get("filter_terms") is not None :
            skipped += 1
            continue

        result = extract_filter_terms(query["query_vi"], query["task_type"])
        if result.provider == "none" :
            failed += 1
            print(f"{query['id']}  {query['task_type']}  [SKIPPED -- no provider]")
            continue

        query["filter_terms"] = {
            "asr_terms" : result.asr_terms,
            "ocr_terms" : result.ocr_terms,
            "confidence" : result.confidence,
            "reasoning" : result.reasoning,
        }
        processed += 1
        confidence_counts[result.confidence] = confidence_counts.get(result.confidence, 0) + 1

        print(
            f"{query['id']}  {query['task_type']}  [{result.confidence}] "
            f"asr: {_format_terms(result.asr_terms)}  ocr: {_format_terms(result.ocr_terms)}  "
            f'"{result.reasoning}"'
        )

        # Only a real network round trip needs pacing -- a cache hit or a
        # "no provider" short-circuit didn't touch Gemini at all.
        if result.provider == "gemini" and not result.cached :
            time.sleep(_CALL_GAP_S)

    with open(seed_path, "w", encoding="utf-8") as f :
        json.dump(seed, f, indent=2, ensure_ascii=False)

    print()
    print(f"Processed: {processed} queries")
    print(f"Skipped (already annotated): {skipped}")
    print(f"Failed (no provider): {failed}")
    print(
        f"Results: {confidence_counts['high']} high, "
        f"{confidence_counts['medium']} medium, {confidence_counts['none']} none"
    )
    print(f"Written to: {seed_path}")
    return 0


if __name__ == "__main__" :
    raise SystemExit(main())
