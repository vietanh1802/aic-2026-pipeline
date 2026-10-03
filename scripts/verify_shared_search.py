# scripts/verify_shared_search.py
"""Compare shared_search with the live ensemble_search on the real loaded indexes.

Takes the first N queries of a dataset and, for each of the 7 encoder subsets with rerank per_model and
off, checks that both give the same frames in the same order with the same scores (tolerance 1e-6).
One PASS or FAIL line per subset and mode; a FAIL prints the first differing frame and both scores.
Exit code 0 only if everything passes. Needs the indexes (AIC_INDEX_DIR), so run it where the backend
runs, for example inside the API container, the same way as run_ablation_suite.py.

    python scripts/verify_shared_search.py --dataset round1-v3 --n 5
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "backend"))

if hasattr(sys.stdout, "reconfigure") :
    sys.stdout.reconfigure(encoding = "utf-8")

from app.evaluation.verify import seed_queries, verify_shared_search  # noqa: E402


def main() -> int :
    parser = argparse.ArgumentParser(description = __doc__.split("\n")[0])
    parser.add_argument("--dataset", default = "round1-v3", help = "dataset version whose first queries are used")
    parser.add_argument("--n", type = int, default = 5, help = "number of queries")
    args = parser.parse_args()

    outcome = verify_shared_search(seed_queries(args.dataset, args.n), lambda line : print(line, flush = True))
    print("ALL PASS" if outcome["ok"] else "FAILED: shared_search does not reproduce ensemble_search")
    return 0 if outcome["ok"] else 1


if (__name__ == "__main__") :
    raise SystemExit(main())
