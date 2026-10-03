# backend/app/evaluation/suite.py
"""A suite is a named, ordered list of runs: every (configuration, dataset) pair of a preset.

There is no suite table. The run rows are the source of truth and each carries suite_id,
suite_name, config_name and suite_order inside configuration_json, so older databases need no
migration and a suite is just a query over runs. Runs execute one after another through
runner.process_run, so the memoised per-model search of shared_search is reused across them: the
first run pays for the searches, later arms of the same text pay only for the fusion.
"""
from __future__ import annotations

import sqlite3
import time
import uuid
from typing import Any, Callable

from app.evaluation.config import RunConfig
from app.evaluation.repository import create_run, get_run, request_cancel, resume_run

TERMINAL = {"completed", "partial", "cancelled", "interrupted", "failed"}
RESUMABLE = {"interrupted", "partial", "cancelled", "failed"}


def new_suite_id() -> str :
    return uuid.uuid4().hex[ : 12]


def _latest_reference_set(conn : sqlite3.Connection, dataset_version : str) -> str :
    row = conn.execute(
        """
        SELECT rs.version FROM evaluation_reference_sets rs
        JOIN evaluation_datasets d ON d.id = rs.dataset_id
        WHERE d.version = ? ORDER BY rs.id DESC LIMIT 1
        """,
        (dataset_version,),
    ).fetchone()
    if (row is None) :
        raise ValueError(f"Unknown evaluation dataset version: {dataset_version}")
    return row["version"]


def create_suite(
    conn : sqlite3.Connection,
    name : str,
    configs : list[RunConfig],
    dataset_versions : list[str],
    created_by_user_id : int | None = None,
) -> dict[str, Any] :
    """Create every run, queued, in order: all datasets of one configuration, then the next
    configuration. If one cannot be created the ones already made are cancelled, so a failed
    request never leaves half a suite behind."""
    suite_id = new_suite_id()
    run_ids : list[int] = []
    try :
        for config in configs :
            for version in dataset_versions :
                run = create_run(
                    conn, version, _latest_reference_set(conn, version), created_by_user_id,
                    config = config,
                    extra_configuration = {
                        "suite_id" : suite_id, "suite_name" : name,
                        "config_name" : config.name, "suite_order" : len(run_ids) + 1,
                    },
                )
                run_ids.append(run["id"])
    except Exception :
        for run_id in run_ids :
            request_cancel(conn, run_id)
        raise
    return {"suite_id" : suite_id, "name" : name, "run_ids" : run_ids}


def suite_runs(conn : sqlite3.Connection, suite_id : str) -> list[dict[str, Any]] :
    rows = conn.execute(
        "SELECT id FROM evaluation_runs WHERE json_extract(configuration_json, '$.suite_id') = ? ORDER BY id",
        (suite_id,),
    ).fetchall()
    return [get_run(conn, int(row["id"])) for row in rows]


def suite_status(conn : sqlite3.Connection, suite_id : str) -> dict[str, Any] :
    runs = suite_runs(conn, suite_id)
    counts : dict[str, int] = {}
    for run in runs :
        counts[run["status"]] = counts.get(run["status"], 0) + 1
    return {
        "suite_id"        : suite_id,
        "runs"            : len(runs),
        "by_status"       : counts,
        "queries_total"   : sum(r["query_count"] for r in runs),
        "queries_done"    : sum(r["completed_count"] + r["failed_count"] for r in runs),
        "finished"        : bool(runs) and all(r["status"] in TERMINAL for r in runs),
    }


def cancel_suite(conn : sqlite3.Connection, suite_id : str) -> int :
    """Cancel what has not finished: queued runs at once, the running one after its current query."""
    cancelled = 0
    for run in suite_runs(conn, suite_id) :
        if (run["status"] in ("queued", "running")) :
            request_cancel(conn, run["id"])
            cancelled += 1
    return cancelled


def resume_suite(conn : sqlite3.Connection, suite_id : str) -> list[int] :
    """Put every run that did not finish back in the queue. Completed runs are left alone, and
    resume_run keeps the completed queries of a partly done run."""
    resumed = []
    for run in suite_runs(conn, suite_id) :
        if (run["status"] in RESUMABLE) :
            resume_run(conn, run["id"])
            resumed.append(run["id"])
    return resumed


def run_suite(
    conn : sqlite3.Connection,
    suite_id : str,
    process : Callable[[int], None],
    on_run_done : Callable[[dict[str, Any], float], None] | None = None,
) -> list[int] :
    """Execute the queued runs of a suite in order through `process` (runner.process_run).

    Stops at the first run that ends `failed`: that is a preflight or prefetch failure (missing key,
    provider down) and every later run would fail the same way. Returns the ids it processed."""
    done : list[int] = []
    for run in suite_runs(conn, suite_id) :
        if (run["status"] != "queued") :
            continue
        started = time.monotonic()
        process(run["id"])
        finished = get_run(conn, run["id"])
        done.append(run["id"])
        if (on_run_done is not None) :
            on_run_done(finished, time.monotonic() - started)
        if (finished["status"] == "failed") :
            break
    return done
