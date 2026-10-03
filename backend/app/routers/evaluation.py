from __future__ import annotations

import sqlite3
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, ValidationError

from app import audit
from app.auth.deps import require_admin
from app.db.connection import get_db
from app.evaluation import text_cache
from app.evaluation.config import RunConfig
from app.evaluation.presets import DEFAULT_DATASETS, preset_configs
from app.evaluation.suite import cancel_suite, create_suite, resume_suite, suite_runs, suite_status
from app.evaluation.repository import (
    create_run,
    find_active_run,
    get_dataset,
    get_result,
    get_results,
    get_run,
    list_datasets,
    list_runs,
    request_cancel,
    resume_run,
)
from app.evaluation.runner import enqueue_run
from app.translation import DEFAULT_TRANSLATION_POLICY, translation_policy_options


router = APIRouter(prefix = "/api/admin/evaluation", tags = ["evaluation"])


class EvaluationRunCreate(BaseModel) :
    dataset_version : str = "round1-v2"
    reference_set_version : str = "r1-manual-v2"
    translation_policy : str = DEFAULT_TRANSLATION_POLICY
    # A RunConfig as a dict makes a configured run (shared search, cached text). Absent = the
    # legacy run, unchanged.
    config : dict[str, Any] | None = None


class PreflightRequest(BaseModel) :
    config : dict[str, Any]
    dataset_versions : list[str]


class TextCacheImport(BaseModel) :
    jsonl : str


def _parse_config(raw : dict[str, Any]) -> RunConfig :
    try :
        return RunConfig.model_validate(raw)
    except ValidationError as exc :
        raise HTTPException(
            status_code = 422,
            detail = exc.errors(include_url = False, include_context = False, include_input = False),
        )


def _preflight_or_422(conn : sqlite3.Connection, config : RunConfig, dataset_versions : list[str]) -> dict[str, Any] :
    """The cache check that runs before a run exists: a missing text that needs an unconfigured key
    is a 422 listing what is missing, never a failure in the middle of a run."""
    report = text_cache.preflight(conn, [config], dataset_versions)
    try :
        text_cache.ensure_ready(report)
    except text_cache.PreflightBlocked as exc :
        raise HTTPException(status_code = 422, detail = exc.report)
    return text_cache.public_report(report)


@router.post("/preflight")
def preflight(
    payload : PreflightRequest,
    _ : Annotated[sqlite3.Row, Depends(require_admin)],
    conn : Annotated[sqlite3.Connection, Depends(get_db)],
) -> dict[str, Any] :
    return {"preflight" : _preflight_or_422(conn, _parse_config(payload.config), payload.dataset_versions)}


@router.get("/text-cache/export", response_class = PlainTextResponse)
def text_cache_export(
    _ : Annotated[sqlite3.Row, Depends(require_admin)],
    conn : Annotated[sqlite3.Connection, Depends(get_db)],
) -> str :
    return text_cache.export_jsonl(conn)


@router.post("/text-cache/import")
def text_cache_import(
    payload : TextCacheImport,
    _ : Annotated[sqlite3.Row, Depends(require_admin)],
    conn : Annotated[sqlite3.Connection, Depends(get_db)],
) -> dict[str, int] :
    try :
        return text_cache.import_jsonl(conn, payload.jsonl)
    except (ValueError, KeyError) as exc :
        raise HTTPException(status_code = status.HTTP_400_BAD_REQUEST, detail = str(exc))


@router.get("/translation-policies")
def translation_policies(
    _ : Annotated[sqlite3.Row, Depends(require_admin)],
) -> dict[str, Any] :
    return {
        "default" : DEFAULT_TRANSLATION_POLICY,
        "policies" : translation_policy_options(),
    }


@router.get("/datasets")
def datasets(
    _ : Annotated[sqlite3.Row, Depends(require_admin)],
    conn : Annotated[sqlite3.Connection, Depends(get_db)],
) -> dict[str, Any] :
    return {"datasets" : list_datasets(conn)}


@router.get("/datasets/{dataset_id}")
def dataset_detail(
    dataset_id : int,
    _ : Annotated[sqlite3.Row, Depends(require_admin)],
    conn : Annotated[sqlite3.Connection, Depends(get_db)],
) -> dict[str, Any] :
    dataset = get_dataset(conn, dataset_id)
    if (dataset is None) :
        raise HTTPException(status_code = status.HTTP_404_NOT_FOUND, detail = "Evaluation dataset not found")
    return {"dataset" : dataset}


@router.post("/runs", status_code = status.HTTP_202_ACCEPTED)
def start_run(
    payload : EvaluationRunCreate,
    user : Annotated[sqlite3.Row, Depends(require_admin)],
    conn : Annotated[sqlite3.Connection, Depends(get_db)],
) -> dict[str, Any] :
    active = find_active_run(conn)
    if (active is not None) :
        raise HTTPException(
            status_code = status.HTTP_409_CONFLICT,
            detail = f"Evaluation run {active['id']} is already {active['status']}",
        )
    config = _parse_config(payload.config) if payload.config is not None else None
    if (config is not None) :
        _preflight_or_422(conn, config, [payload.dataset_version])
    try :
        run = create_run(
            conn,
            payload.dataset_version,
            payload.reference_set_version,
            int(user["id"]),
            translation_policy = payload.translation_policy,
            config = config,
        )
    except ValueError as exc :
        raise HTTPException(status_code = status.HTTP_400_BAD_REQUEST, detail = str(exc))

    audit.record(
        conn,
        user["id"],
        audit.EVALUATION_RUN_START,
        f"evaluation_run:{run['id']}",
        f"Chạy benchmark {run['dataset_version']} / {run['reference_set_version']} "
        f"({run['translator']})",
        {"translation_policy" : payload.translation_policy},
    )
    enqueue_run(run["id"])
    return {"run" : run}


@router.get("/runs")
def runs(
    _ : Annotated[sqlite3.Row, Depends(require_admin)],
    conn : Annotated[sqlite3.Connection, Depends(get_db)],
    limit : int = Query(default = 50, ge = 1, le = 200),
) -> dict[str, Any] :
    return {"runs" : list_runs(conn, limit)}


@router.get("/runs/{run_id}")
def run_detail(
    run_id : int,
    _ : Annotated[sqlite3.Row, Depends(require_admin)],
    conn : Annotated[sqlite3.Connection, Depends(get_db)],
) -> dict[str, Any] :
    run = get_run(conn, run_id)
    if (run is None) :
        raise HTTPException(status_code = status.HTTP_404_NOT_FOUND, detail = "Evaluation run not found")
    return {"run" : run}


@router.get("/runs/{run_id}/results")
def run_results(
    run_id : int,
    _ : Annotated[sqlite3.Row, Depends(require_admin)],
    conn : Annotated[sqlite3.Connection, Depends(get_db)],
) -> dict[str, Any] :
    if (get_run(conn, run_id) is None) :
        raise HTTPException(status_code = status.HTTP_404_NOT_FOUND, detail = "Evaluation run not found")
    return {"results" : get_results(conn, run_id)}


@router.get("/runs/{run_id}/results/{query_key}")
def run_result_detail(
    run_id : int,
    query_key : str,
    _ : Annotated[sqlite3.Row, Depends(require_admin)],
    conn : Annotated[sqlite3.Connection, Depends(get_db)],
) -> dict[str, Any] :
    result = get_result(conn, run_id, query_key)
    if (result is None) :
        raise HTTPException(status_code = status.HTTP_404_NOT_FOUND, detail = "Evaluation result not found")
    return {"result" : result}


@router.post("/runs/{run_id}/cancel")
def cancel_run(
    run_id : int,
    user : Annotated[sqlite3.Row, Depends(require_admin)],
    conn : Annotated[sqlite3.Connection, Depends(get_db)],
) -> dict[str, Any] :
    run = request_cancel(conn, run_id)
    if (run is None) :
        raise HTTPException(status_code = status.HTTP_404_NOT_FOUND, detail = "Evaluation run not found")
    audit.record(
        conn,
        user["id"],
        audit.EVALUATION_RUN_CANCEL,
        f"evaluation_run:{run_id}",
        f"Huỷ benchmark run {run_id} (trạng thái: {run['status']})",
    )
    return {"run" : run}


@router.post("/runs/{run_id}/resume", status_code = status.HTTP_202_ACCEPTED)
def resume(
    run_id : int,
    user : Annotated[sqlite3.Row, Depends(require_admin)],
    conn : Annotated[sqlite3.Connection, Depends(get_db)],
) -> dict[str, Any] :
    active = find_active_run(conn)
    if (active is not None and active["id"] != run_id) :
        raise HTTPException(
            status_code = status.HTTP_409_CONFLICT,
            detail = f"Evaluation run {active['id']} is already {active['status']}",
        )
    try :
        run = resume_run(conn, run_id)
    except ValueError as exc :
        raise HTTPException(status_code = status.HTTP_409_CONFLICT, detail = str(exc))
    if (run is None) :
        raise HTTPException(status_code = status.HTTP_404_NOT_FOUND, detail = "Evaluation run not found")
    audit.record(
        conn,
        user["id"],
        audit.EVALUATION_RUN_RESUME,
        f"evaluation_run:{run_id}",
        f"Chạy tiếp benchmark run {run_id} (lần {run['resume_count']})",
    )
    enqueue_run(run_id)
    return {"run" : run}


class SuiteCreate(BaseModel) :
    name : str = "core"
    # A preset name ("core", "extras", "core,extras") or an explicit list of RunConfig dicts.
    preset : str | None = "core"
    configs : list[dict[str, Any]] | None = None
    datasets : list[str] = list(DEFAULT_DATASETS)


@router.post("/suites", status_code = status.HTTP_202_ACCEPTED)
def start_suite(
    payload : SuiteCreate,
    user : Annotated[sqlite3.Row, Depends(require_admin)],
    conn : Annotated[sqlite3.Connection, Depends(get_db)],
) -> dict[str, Any] :
    """Create every run of a suite and queue them; the single worker executes them in order."""
    active = find_active_run(conn)
    if (active is not None) :
        raise HTTPException(
            status_code = status.HTTP_409_CONFLICT,
            detail = f"Evaluation run {active['id']} is already {active['status']}",
        )
    try :
        configs = [_parse_config(c) for c in payload.configs] if payload.configs else preset_configs(payload.preset or "core")
    except ValueError as exc :
        raise HTTPException(status_code = status.HTTP_400_BAD_REQUEST, detail = str(exc))

    report = text_cache.preflight(conn, configs, payload.datasets)
    try :
        text_cache.ensure_ready(report)
    except text_cache.PreflightBlocked as exc :
        raise HTTPException(status_code = 422, detail = exc.report)
    try :
        created = create_suite(conn, payload.name, configs, payload.datasets, int(user["id"]))
    except ValueError as exc :
        raise HTTPException(status_code = status.HTTP_400_BAD_REQUEST, detail = str(exc))

    audit.record(
        conn, user["id"], audit.EVALUATION_RUN_START, f"evaluation_suite:{created['suite_id']}",
        f"Chạy suite {payload.name}: {len(created['run_ids'])} run", {"datasets" : payload.datasets},
    )
    for run_id in created["run_ids"] :
        enqueue_run(run_id)
    return {"suite" : created, "preflight" : text_cache.public_report(report)}


@router.get("/suites/{suite_id}")
def suite_detail(
    suite_id : str,
    _ : Annotated[sqlite3.Row, Depends(require_admin)],
    conn : Annotated[sqlite3.Connection, Depends(get_db)],
) -> dict[str, Any] :
    if (not suite_runs(conn, suite_id)) :
        raise HTTPException(status_code = status.HTTP_404_NOT_FOUND, detail = "Evaluation suite not found")
    return {"suite" : suite_status(conn, suite_id), "runs" : suite_runs(conn, suite_id)}


@router.post("/suites/{suite_id}/cancel")
def suite_cancel(
    suite_id : str,
    _ : Annotated[sqlite3.Row, Depends(require_admin)],
    conn : Annotated[sqlite3.Connection, Depends(get_db)],
) -> dict[str, Any] :
    if (not suite_runs(conn, suite_id)) :
        raise HTTPException(status_code = status.HTTP_404_NOT_FOUND, detail = "Evaluation suite not found")
    return {"cancelled" : cancel_suite(conn, suite_id), "suite" : suite_status(conn, suite_id)}


@router.post("/suites/{suite_id}/resume", status_code = status.HTTP_202_ACCEPTED)
def suite_resume(
    suite_id : str,
    _ : Annotated[sqlite3.Row, Depends(require_admin)],
    conn : Annotated[sqlite3.Connection, Depends(get_db)],
) -> dict[str, Any] :
    if (not suite_runs(conn, suite_id)) :
        raise HTTPException(status_code = status.HTTP_404_NOT_FOUND, detail = "Evaluation suite not found")
    active = find_active_run(conn)
    if (active is not None) :
        raise HTTPException(
            status_code = status.HTTP_409_CONFLICT,
            detail = f"Evaluation run {active['id']} is already {active['status']}",
        )
    resumed = resume_suite(conn, suite_id)
    for run in suite_runs(conn, suite_id) :
        if (run["status"] == "queued") :
            enqueue_run(run["id"])
    return {"resumed" : resumed, "suite" : suite_status(conn, suite_id)}
