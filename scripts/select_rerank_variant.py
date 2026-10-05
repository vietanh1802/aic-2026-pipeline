# scripts/select_rerank_variant.py
"""Apply the selection rule of HANDOVER/rerank_selection_rule.md to a rerank_diag run and freeze the winner.

The rule was committed before the development run:
  1. text: R01S (Expand sentence) against R01K (Expand keywords), both rerank off, all three encoders;
  2. rerank: R01 to R12 on the chosen text;
  each by Hit@1 on Benchmark A pooled (86 queries), ties by MRR, then Recall@10, then the lower code (R01 first,
  the sentence before the keywords).

It reads only Benchmark A rows and REFUSES a run folder that holds any Benchmark B row, so the selection cannot
see B. The winner's full RunConfig goes to backend/app/evaluation/frozen_selection.json together with every
candidate's numbers, which preset final_table then reads. Commit that file before running final_table.

    python scripts/select_rerank_variant.py --run-dir <rerank_diag run folder>
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.evaluation.presets import FROZEN_SELECTION, preset_configs  # noqa: E402

EXPECTED_A = 86


def pooled_a(run_dir : Path) -> dict[str, dict[str, float]] :
    rows = list(csv.DictReader((run_dir / "results_long.csv").open(encoding = "utf-8")))
    if (any(r["benchmark"] == "B" for r in rows)) :
        raise SystemExit("REFUSED: this run folder holds Benchmark B rows; the selection must be made on A only")
    out = {}
    for r in rows :
        if ((r["benchmark"], r["flags"], r["task_type"], r["prefix"]) != ("A", "all", "all", "all")) :
            continue
        if (int(r["n"]) != EXPECTED_A or int(r["failed"] or 0) != 0) :
            raise SystemExit(f"REFUSED: {r['config']} has n = {r['n']}, failed = {r['failed']} (expected {EXPECTED_A}, 0)")
        out[r["config"]] = {k : float(r[k]) for k in ("hit_at_1", "r_at_5", "r_at_10", "mrr")}
    return out


def rank_key(code_order : int, m : dict[str, float]) -> tuple :
    # Highest Hit@1, then MRR, then R@10; a full tie goes to the earlier candidate.
    return (-round(m["hit_at_1"], 9), -round(m["mrr"], 9), -round(m["r_at_10"], 9), code_order)


def main() -> int :
    parser = argparse.ArgumentParser(description = __doc__.split("\n")[0])
    parser.add_argument("--run-dir", required = True)
    parser.add_argument("--out", default = str(FROZEN_SELECTION))
    args = parser.parse_args()
    run_dir = Path(args.run_dir)

    configs = {c.name : c for c in preset_configs("rerank_diag")}
    scores = pooled_a(run_dir)
    missing = sorted(set(configs) - set(scores))
    if (missing) :
        raise SystemExit(f"REFUSED: the run lacks {len(missing)} grid configurations, e.g. {missing[ : 3]}")

    by_code = {name.split()[0] : name for name in configs}
    texts = [("S", "expand_gemini"), ("K", "expand_keywords")]
    text_suffix, text_policy = min(texts, key = lambda t : rank_key(texts.index(t), scores[by_code[f"R01{t[0]}"]]))
    grid = [name for code, name in by_code.items() if code.endswith(text_suffix)]
    winner = min(grid, key = lambda name : rank_key(grid.index(name), scores[name]))

    print(f"text: R01S {scores[by_code['R01S']]} vs R01K {scores[by_code['R01K']]} -> {text_policy}")
    print(f"{'config':<60} {'H@1':>6} {'R@5':>6} {'R@10':>6} {'MRR':>6}")
    for name in configs :
        m = scores[name]
        mark = "  <== frozen" if name == winner else ""
        print(f"{name:<60} {m['hit_at_1'] * 100:6.1f} {m['r_at_5'] * 100:6.1f} {m['r_at_10'] * 100:6.1f} {m['mrr']:6.3f}{mark}")

    provenance = json.loads((run_dir / "provenance.json").read_text(encoding = "utf-8")) if (run_dir / "provenance.json").exists() else {}
    frozen = {
        "rule"        : "HANDOVER/rerank_selection_rule.md",
        "run_dir"     : run_dir.name,
        "run_commit"  : provenance.get("commit_full") or provenance.get("commit"),
        "frozen_at"   : datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "text_policy" : text_policy,
        "winner"      : winner,
        "config"      : json.loads(configs[winner].model_dump_json()),
        "candidates"  : {name : scores[name] for name in configs},
    }
    Path(args.out).write_text(json.dumps(frozen, indent = 1, ensure_ascii = False) + "\n", encoding = "utf-8")
    print(f"frozen: {winner} -> {args.out}")
    return 0


if (__name__ == "__main__") :
    raise SystemExit(main())
