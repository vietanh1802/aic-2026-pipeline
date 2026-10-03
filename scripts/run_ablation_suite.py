# scripts/run_ablation_suite.py
"""Run an ablation suite in this process and write the paper's tables.

Calls the same functions the API uses (suite.create_suite, runner.process_run, report.*), against its
OWN SQLite file, so it can run next to a live API without touching the live database. Needs the
indexes the backend reads (AIC_INDEX_DIR) and, for text policies that are not cached yet, network
access (gtx) or GEMINI_API_KEY (Expand).

Everything lands in <out>/<timestamp>/:
    ablation.db           the runs (resume reads it)
    suite.json            suite id and arguments, so --resume can find the suite
    run.log               everything printed
    provenance.json       commit, version, configuration of every run, index coverage, timings
    results_long.csv      every configuration x benchmark x flag mode x slice
    rank_matrix_A.csv, rank_matrix_B.csv        reference video rank per query and configuration, flips vs baseline
    table_A.tex, table_A_noflag.tex, table_B.tex, table_B_noflag.tex      Configuration & Hit@1 & R@5 & R@10 & MRR
    bootstrap_A.csv, bootstrap_B.csv            paired bootstrap against the baseline

    python scripts/run_ablation_suite.py --preset core --out ablation_out
    python scripts/run_ablation_suite.py --preset core --limit-queries 3 --out ablation_out   # smoke test
    python scripts/run_ablation_suite.py --resume ablation_out/20261004-120000
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
# Before any `import app`: the checkout this script lives in must win over an `app` package that the
# environment (for example a container image) already has.
sys.path.insert(0, str(REPO_ROOT / "backend"))

if hasattr(sys.stdout, "reconfigure") :
    sys.stdout.reconfigure(encoding = "utf-8")

from app.db.connection import get_conn  # noqa: E402
from app.db.migrate import migrate  # noqa: E402
from app.evaluation import report, text_cache  # noqa: E402
from app.evaluation.presets import DEFAULT_DATASETS, preset_configs  # noqa: E402
from app.evaluation.runner import _db_path_env, interrupt_incomplete_runs, process_run  # noqa: E402
from app.evaluation.seed import import_all_seeds  # noqa: E402
from app.evaluation.suite import create_suite, resume_suite, run_suite, suite_runs  # noqa: E402
from app.evaluation.verify import seed_queries, verify_shared_search  # noqa: E402
from app.version import COMMIT, VERSION  # noqa: E402


def full_commit() -> str :
    """AIC_COMMIT when set (the image bakes it in), else the checkout's HEAD, else unknown."""
    if (COMMIT != "unknown") :
        return COMMIT
    try :
        result = subprocess.run(["git", "rev-parse", "HEAD"], cwd = REPO_ROOT, capture_output = True, text = True, check = True)
    except (OSError, subprocess.CalledProcessError) :
        return "unknown"   # an archive without .git: provenance says so instead of guessing
    return result.stdout.strip()


def main() -> int :
    parser = argparse.ArgumentParser(description = __doc__.split("\n")[0])
    parser.add_argument("--preset", default = "core", help = "core, extras, or both comma-separated")
    parser.add_argument("--datasets", default = ",".join(DEFAULT_DATASETS), help = "comma-separated dataset versions")
    parser.add_argument("--out", default = "ablation_out", help = "parent folder; a timestamped folder is created inside")
    parser.add_argument("--resume", default = None, help = "an existing <out>/<timestamp> folder to continue")
    parser.add_argument("--limit-queries", type = int, default = None, help = "first N queries of each dataset (smoke test)")
    parser.add_argument("--skip-verify", action = "store_true", help = "do not check shared_search against ensemble_search first")
    parser.add_argument("--verify-queries", type = int, default = 5, help = "queries used by that check")
    args = parser.parse_args()

    started_at = datetime.now()
    run_dir = Path(args.resume) if args.resume else Path(args.out) / started_at.strftime("%Y%m%d-%H%M%S")
    run_dir.mkdir(parents = True, exist_ok = True)
    log_file = open(run_dir / "run.log", "a", encoding = "utf-8")

    def say(message : str) -> None :
        line = f"{datetime.now():%H:%M:%S} {message}"
        print(line, flush = True)
        log_file.write(line + "\n")
        log_file.flush()

    db_file = run_dir / "ablation.db"
    datasets = [d.strip() for d in args.datasets.split(",") if d.strip()]
    say(f"run folder {run_dir}")
    say(f"database {db_file} (the live database is not touched)")

    with _db_path_env(db_file) :
        conn = get_conn()
        migrate(conn)
        import_all_seeds(conn)
        added = text_cache.import_seed_caches(conn)
        say(f"text cache from seeds: {added['inserted']} added, {added['skipped']} already present")

        if (args.resume) :
            state = json.loads((run_dir / "suite.json").read_text(encoding = "utf-8"))
            suite_id = state["suite_id"]
            # A run that was mid-flight when the process died is still marked running; make it resumable.
            interrupted = interrupt_incomplete_runs(conn)
            resumed = resume_suite(conn, suite_id)
            say(f"resume: suite {suite_id}, {interrupted} marked interrupted, {len(resumed)} runs back in the queue")
        else :
            # shared_search is only valid if it reproduces ensemble_search on the real indexes.
            # A full run on top of a broken equivalence would produce a table nobody can trust.
            if (args.skip_verify) :
                verify = {"skipped" : True}
                say("WARNING: --skip-verify, shared_search was not checked against ensemble_search")
            else :
                say(f"verifying shared_search against ensemble_search on {datasets[0]} ({args.verify_queries} queries)")
                verify = verify_shared_search(seed_queries(datasets[0], args.verify_queries), say)
                if (not verify["ok"]) :
                    say("REFUSING to start: shared_search does not reproduce ensemble_search (see the FAIL lines)")
                    return 4
            configs = preset_configs(args.preset)
            for config in configs :
                config.subset.limit_queries = args.limit_queries
            say(f"preset {args.preset}: {len(configs)} configurations x {len(datasets)} datasets = {len(configs) * len(datasets)} runs")

            pre = text_cache.preflight(conn, configs, datasets)
            say(f"texts: {pre['needed']} needed, {pre['cached']} cached, {pre['missing']} missing")
            try :
                text_cache.ensure_ready(pre)
            except text_cache.PreflightBlocked as exc :
                say(f"BLOCKED: {exc}")
                return 2
            fetch_missing(conn, pre["_missing_items"], say)

            created = create_suite(conn, f"{args.preset}-{started_at:%Y%m%d-%H%M%S}", configs, datasets)
            suite_id = created["suite_id"]
            (run_dir / "suite.json").write_text(json.dumps({
                "suite_id" : suite_id, "preset" : args.preset, "datasets" : datasets,
                "limit_queries" : args.limit_queries, "started_at" : started_at.isoformat(), "verify" : verify,
            }, indent = 1, ensure_ascii = False), encoding = "utf-8")
            say(f"suite {suite_id}: {len(created['run_ids'])} runs created")

        timings : dict[int, float] = {}
        progress = {"seconds" : 0.0, "queries" : 0}

        def on_run_done(run, seconds : float) -> None :
            done = run["completed_count"] + run["failed_count"]
            timings[run["id"]] = seconds
            progress["seconds"] += seconds
            progress["queries"] += done
            remaining = sum(r["query_count"] for r in suite_runs(conn, suite_id) if r["status"] in ("queued", "running"))
            per_query = progress["seconds"] / max(1, progress["queries"])
            say(
                f"run {run['id']} {run['configuration'].get('config_name')} on {run['dataset_version']}: {run['status']}, "
                f"{done} queries in {seconds:.1f}s ({seconds / max(1, done):.2f} s/query). "
                f"Average {per_query:.2f} s/query; {remaining} queries left, ETA <= {remaining * per_query / 60:.1f} min "
                f"(an upper bound: later arms of the same text reuse the searches)"
            )

        run_suite(conn, suite_id, process_run, on_run_done)

        runs = suite_runs(conn, suite_id)
        unfinished = [r for r in runs if r["status"] not in ("completed", "partial")]
        if (unfinished) :
            say(f"{len(unfinished)} runs did not finish ({', '.join(sorted({r['status'] for r in unfinished}))}); "
                f"fix the cause and rerun with --resume {run_dir}")
        rows = report.load_rows(conn, [r["id"] for r in runs if r["status"] in ("completed", "partial")])
        write_outputs(run_dir, rows, say)
        write_provenance(run_dir, args, datasets, runs, timings, started_at,
                         json.loads((run_dir / "suite.json").read_text(encoding = "utf-8")).get("verify"))
        conn.close()
    say("done" if not unfinished else "finished with unfinished runs")
    return 0 if not unfinished else 1


def fetch_missing(conn, missing, say) -> None :
    """Fill the text cache before any run is created, so the runs themselves never wait on a provider."""
    if (not missing) :
        return
    say(f"fetching {len(missing)} texts (about 4.5 s each, one provider call at a time)")
    started = time.monotonic()

    def progress(index : int, total : int) -> None :
        elapsed = time.monotonic() - started
        say(f"  text {index}/{total}, ETA {(total - index) * elapsed / max(1, index) / 60:.1f} min")

    try :
        fetched = text_cache.prefetch(conn, missing, on_progress = progress)
    except text_cache.PrefetchError as exc :
        say(f"PREFETCH FAILED: {exc}")
        raise SystemExit(3)
    say(f"fetched {fetched} texts")


def write_outputs(run_dir : Path, rows : list, say) -> None :
    if (not rows) :
        say("no finished runs, no tables written")
        return
    table = report.long_table(rows)
    (run_dir / "results_long.csv").write_text(report.long_csv(table), encoding = "utf-8")
    configs = report.configs_in_order(rows)
    baseline = next((c for c in configs if c.startswith("C01")), configs[0])
    for benchmark in ("A", "B") :
        matrix = report.rank_matrix(rows, baseline, benchmark)
        (run_dir / f"rank_matrix_{benchmark}.csv").write_text(report.rank_matrix_csv(matrix), encoding = "utf-8")
        (run_dir / f"bootstrap_{benchmark}.csv").write_text(
            report.bootstrap_csv(report.paired_bootstrap(rows, baseline, benchmark)), encoding = "utf-8")
        (run_dir / f"table_{benchmark}.tex").write_text(report.latex_table(table, benchmark, "all"), encoding = "utf-8")
        (run_dir / f"table_{benchmark}_noflag.tex").write_text(
            report.latex_table(table, benchmark, "exclude_flagged"), encoding = "utf-8")
    say(f"wrote results_long.csv, rank matrices, bootstrap and LaTeX tables for {len(configs)} configurations (baseline: {baseline})")


def write_provenance(run_dir : Path, args, datasets, runs, timings, started_at, verify) -> None :
    first_runtime = next((r["runtime"] for r in runs if r.get("runtime")), None)
    provenance = {
        "started_at"      : started_at.isoformat(),
        "finished_at"     : datetime.now().isoformat(),
        "argv"            : sys.argv,
        "preset"          : args.preset,
        "datasets"        : datasets,
        "limit_queries"   : args.limit_queries,
        "commit_full"     : full_commit(),
        "version"         : VERSION,
        "python"          : platform.python_version(),
        "host"            : platform.node(),
        "aic_index_dir"   : os.environ.get("AIC_INDEX_DIR"),
        "gemini_key_configured" : text_cache.key_configured(),   # presence only, never the value
        "verify_shared_search" : verify,
        "runs"            : [
            {
                "id" : r["id"], "config_name" : r["configuration"].get("config_name"), "dataset" : r["dataset_version"],
                "status" : r["status"], "completed" : r["completed_count"], "failed" : r["failed_count"],
                "seconds" : round(timings.get(r["id"], 0.0), 1), "config_hash" : r["configuration"].get("config_hash"),
                "config" : r["configuration"].get("config"),
            }
            for r in runs
        ],
        "runtime_first_run" : first_runtime,
    }
    (run_dir / "provenance.json").write_text(json.dumps(provenance, indent = 1, ensure_ascii = False), encoding = "utf-8")


if (__name__ == "__main__") :
    raise SystemExit(main())
