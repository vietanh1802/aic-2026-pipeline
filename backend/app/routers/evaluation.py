from __future__ import annotations

import sqlite3
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from app.auth.deps import require_admin
from app.db.connection import get_db
from app.evaluation.repository import (
    create_run,
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
from app.translation import (
    DEFAULT_TRANSLATION_POLICY,
    translation_policy_options,
)


router = APIRouter(prefix = "/api/admin/evaluation", tags = ["evaluation"])


class EvaluationRunCreate(BaseModel) :
    dataset_version : str = "round1-v1"
    reference_set_version : str = "r1-manual-v1"
    translation_policy : str = DEFAULT_TRANSLATION_POLICY


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
    try :
        run = create_run(
            conn,
            payload.dataset_version,
            payload.reference_set_version,
            int(user["id"]),
            translation_policy = payload.translation_policy,
        )
    except ValueError as exc :
        raise HTTPException(status_code = status.HTTP_400_BAD_REQUEST, detail = str(exc))
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
    _ : Annotated[sqlite3.Row, Depends(require_admin)],
    conn : Annotated[sqlite3.Connection, Depends(get_db)],
) -> dict[str, Any] :
    run = request_cancel(conn, run_id)
    if (run is None) :
        raise HTTPException(status_code = status.HTTP_404_NOT_FOUND, detail = "Evaluation run not found")
    return {"run" : run}


@router.post("/runs/{run_id}/resume", status_code = status.HTTP_202_ACCEPTED)
def resume(
    run_id : int,
    _ : Annotated[sqlite3.Row, Depends(require_admin)],
    conn : Annotated[sqlite3.Connection, Depends(get_db)],
) -> dict[str, Any] :
    try :
        run = resume_run(conn, run_id)
    except ValueError as exc :
        raise HTTPException(status_code = status.HTTP_409_CONFLICT, detail = str(exc))
    if (run is None) :
        raise HTTPException(status_code = status.HTTP_404_NOT_FOUND, detail = "Evaluation run not found")
    enqueue_run(run_id)
    return {"run" : run}
