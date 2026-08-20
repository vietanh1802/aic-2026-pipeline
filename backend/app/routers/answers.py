# -*- coding: utf-8 -*-
"""The answer basket: a hundred rows per task, ordered by sort_key.

Two things carry over from dev unchanged because they were already right: the
optimistic `version` check on PATCH, and deriving rank at read time so moving a
row is one UPDATE rather than a renumbering.

Autofill is a rewrite. dev copied the search order verbatim and derived TRAKE
frames as `base + i*18`, where 18 came from nowhere. Spec §7 replaces both with
the tactic the team actually uses: pin a video by hand, then spread frames
around the row you trust most.
"""
from __future__ import annotations

import json
import sqlite3
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.answers.autofill import spread
from app.auth.deps import active_user
from app.db.connection import get_db, utcnow_iso
from app.routers._shared import (
    after_sort_key,
    answer_payload,
    answers,
    before_sort_key,
    load_task,
    next_sort_key,
    rows_per_query,
    top_sort_key,
)

router = APIRouter(prefix="/api", tags=["answers"])


class AnswerCreateRequest(BaseModel):
    video_id: str
    frames: list[int]
    answer_text: str | None = None
    position: Any = None


class AnswerPatchRequest(BaseModel):
    version: int
    video_id: str | None = None
    frames: list[int] | None = None
    answer_text: str | None = None
    origin: str | None = None


class ReorderRequest(BaseModel):
    answer_id: int
    before_id: int | None = None
    after_id: int | None = None


class AutofillRequest(BaseModel):
    limit: int = Field(100, ge=1, le=500)
    # One second at 25 fps for KIS and Q&A. TRAKE overrides it to 2 from the
    # client: the rules put each event's window at "usually under 10 frames",
    # so a one-second step would jump clean over it.
    step: int = Field(25, ge=1, le=2000)
    # append       add rows until the basket reaches the target
    # replace_auto drop the generated rows, then refill - for changing the step
    # clear        drop the generated rows and stop
    mode: str = "append"


def _row_with_rank(conn: sqlite3.Connection, answer_id: int) -> sqlite3.Row:
    return conn.execute(
        "SELECT ROW_NUMBER() OVER (ORDER BY sort_key, id) AS rank, * "
        "FROM answers WHERE id = ?",
        (answer_id,),
    ).fetchone()


@router.get("/tasks/{task_id}/answers")
def list_answers(
    task_id: int,
    _: Annotated[sqlite3.Row, Depends(active_user)],
    conn: Annotated[sqlite3.Connection, Depends(get_db)],
) -> dict[str, Any]:
    load_task(conn, task_id)
    return {"answers": answers(conn, task_id)}


@router.post("/tasks/{task_id}/answers", status_code=201)
def create_answer(
    task_id: int,
    payload: AnswerCreateRequest,
    user: Annotated[sqlite3.Row, Depends(active_user)],
    conn: Annotated[sqlite3.Connection, Depends(get_db)],
) -> dict[str, Any]:
    load_task(conn, task_id)
    if isinstance(payload.position, dict) and "after_id" in payload.position:
        sort_key = after_sort_key(conn, task_id, int(payload.position["after_id"]))
    elif payload.position == "top":
        sort_key = top_sort_key(conn, task_id)
    else:
        sort_key = next_sort_key(conn, task_id)

    now = utcnow_iso()
    cursor = conn.execute(
        "INSERT INTO answers "
        "(task_id, sort_key, video_id, frames, answer_text, origin, created_by, "
        " updated_by, updated_at, version) VALUES (?, ?, ?, ?, ?, 'manual', ?, ?, ?, 1)",
        (
            task_id,
            sort_key,
            payload.video_id,
            json.dumps(payload.frames),
            payload.answer_text,
            user["id"],
            user["id"],
            now,
        ),
    )
    return {"answer": answer_payload(conn, _row_with_rank(conn, cursor.lastrowid))}


@router.patch("/answers/{answer_id}")
def patch_answer(
    answer_id: int,
    payload: AnswerPatchRequest,
    user: Annotated[sqlite3.Row, Depends(active_user)],
    conn: Annotated[sqlite3.Connection, Depends(get_db)],
):
    row = conn.execute("SELECT * FROM answers WHERE id = ?", (answer_id,)).fetchone()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="No such answer"
        )

    cursor = conn.execute(
        "UPDATE answers SET video_id = ?, frames = ?, answer_text = ?, origin = ?, "
        "updated_by = ?, updated_at = ?, version = version + 1 "
        "WHERE id = ? AND version = ?",
        (
            payload.video_id if payload.video_id is not None else row["video_id"],
            json.dumps(payload.frames) if payload.frames is not None else row["frames"],
            payload.answer_text
            if payload.answer_text is not None
            else row["answer_text"],
            payload.origin if payload.origin is not None else row["origin"],
            user["id"],
            utcnow_iso(),
            answer_id,
            payload.version,
        ),
    )
    if cursor.rowcount != 1:
        # Somebody edited this row between the client reading it and writing it.
        # Hand back what is there now so the UI can show both.
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={
                "detail": "Modified by someone else",
                "current": answer_payload(conn, _row_with_rank(conn, answer_id)),
            },
        )
    return {"answer": answer_payload(conn, _row_with_rank(conn, answer_id))}


@router.delete("/answers/{answer_id}")
def delete_answer(
    answer_id: int,
    _: Annotated[sqlite3.Row, Depends(active_user)],
    conn: Annotated[sqlite3.Connection, Depends(get_db)],
) -> dict[str, Any]:
    cursor = conn.execute("DELETE FROM answers WHERE id = ?", (answer_id,))
    if cursor.rowcount != 1:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="No such answer"
        )
    return {"ok": True}


@router.delete("/tasks/{task_id}/answers")
def clear_answers(
    task_id: int,
    _: Annotated[sqlite3.Row, Depends(active_user)],
    conn: Annotated[sqlite3.Connection, Depends(get_db)],
) -> dict[str, Any]:
    """Throw away the whole answer set for one task.

    Distinct from `autofill mode="clear"`, which spares the manual pins because
    its job is to let the spread be redone with a different step. This one is
    for the export screen: the reviewer looks at the CSV a query is about to
    submit, decides it is wrong, and starts that query over.

    `removed` rather than a bare ok, so the screen can say what it just threw
    away instead of leaving the reviewer guessing whether the click landed.
    """
    load_task(conn, task_id)
    removed = conn.execute("DELETE FROM answers WHERE task_id = ?", (task_id,)).rowcount
    return {"removed": removed, "total": 0}


@router.post("/tasks/{task_id}/answers/reorder")
def reorder_answer(
    task_id: int,
    payload: ReorderRequest,
    _: Annotated[sqlite3.Row, Depends(active_user)],
    conn: Annotated[sqlite3.Connection, Depends(get_db)],
) -> dict[str, Any]:
    load_task(conn, task_id)
    if payload.before_id is not None:
        sort_key = before_sort_key(conn, task_id, payload.before_id)
    elif payload.after_id is not None:
        sort_key = after_sort_key(conn, task_id, payload.after_id)
    else:
        sort_key = top_sort_key(conn, task_id)
    conn.execute(
        "UPDATE answers SET sort_key = ?, updated_at = ?, version = version + 1 "
        "WHERE id = ? AND task_id = ?",
        (sort_key, utcnow_iso(), payload.answer_id, task_id),
    )
    return {"answers": answers(conn, task_id)}


@router.post("/tasks/{task_id}/answers/autofill")
def autofill_answers(
    task_id: int,
    payload: AutofillRequest,
    user: Annotated[sqlite3.Row, Depends(active_user)],
    conn: Annotated[sqlite3.Connection, Depends(get_db)],
) -> dict[str, Any]:
    task = load_task(conn, task_id)
    target = min(payload.limit, rows_per_query(conn))

    if payload.mode in ("replace_auto", "clear"):
        removed = conn.execute(
            "DELETE FROM answers WHERE task_id = ? AND origin = 'auto'", (task_id,)
        ).rowcount
        if payload.mode == "clear":
            total = conn.execute(
                "SELECT COUNT(*) AS n FROM answers WHERE task_id = ?", (task_id,)
            ).fetchone()["n"]
            return {"added": 0, "removed": removed, "total": total}

    rows = conn.execute(
        "SELECT * FROM answers WHERE task_id = ? ORDER BY sort_key, id", (task_id,)
    ).fetchall()
    if not rows:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Pin at least one answer first — autofill spreads around it.",
        )

    # The anchor is whichever row the user put at rank 1, not whatever the ranker
    # liked best. Spec §7.1.
    anchor_row = rows[0]
    anchor_frames = [int(f) for f in json.loads(anchor_row["frames"])]
    if not anchor_frames:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The first answer has no frame to spread around.",
        )
    anchor = anchor_frames[0]
    video_id = anchor_row["video_id"]
    answer_text = anchor_row["answer_text"] if task["type"] == "qa" else None

    taken = {
        (row["video_id"], tuple(int(f) for f in json.loads(row["frames"])))
        for row in rows
    }
    needed = max(0, target - len(rows))
    now = utcnow_iso()
    added = 0

    for frame in spread(anchor, payload.step, needed * 2):
        if added >= needed:
            break
        # TRAKE keeps the whole tuple and shifts it by one delta, so the gaps
        # between events survive. Guessing per-event offsets would be inventing
        # numbers, and the scoring is lopsided: the wrong video is zero outright,
        # while a wrong mark costs 1/N.
        frames = (
            [frame + (f - anchor) for f in anchor_frames]
            if task["type"] == "trake"
            else [frame]
        )
        key = (video_id, tuple(frames))
        if any(f < 0 for f in frames) or key in taken:
            continue
        taken.add(key)
        conn.execute(
            "INSERT INTO answers (task_id, sort_key, video_id, frames, answer_text, "
            "origin, created_by, updated_by, updated_at, version) "
            "VALUES (?, ?, ?, ?, ?, 'auto', ?, NULL, ?, 1)",
            (
                task_id,
                next_sort_key(conn, task_id),
                video_id,
                json.dumps(frames),
                answer_text,
                user["id"],
                now,
            ),
        )
        added += 1

    total = conn.execute(
        "SELECT COUNT(*) AS n FROM answers WHERE task_id = ?", (task_id,)
    ).fetchone()["n"]
    return {"added": added, "total": total}
