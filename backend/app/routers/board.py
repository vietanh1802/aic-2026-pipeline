# -*- coding: utf-8 -*-
"""The task board: who is holding what.

Claiming is a conditional UPDATE and nothing else:

    UPDATE tasks SET owner_id = ? WHERE id = ? AND owner_id IS NULL

`rowcount == 0` means somebody else got there first. That is the whole
concurrency story — no locks, no read-then-write race, and it stays correct
however many browsers poll at once.
"""
from __future__ import annotations

import sqlite3
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.auth.deps import active_user
from app.db.connection import get_db, utcnow_iso
from app.routers._shared import (
    active_pack,
    load_task,
    rows_per_query,
    task_payload,
    user_out,
)

router = APIRouter(prefix="/api", tags=["board"])


class PresenceRequest(BaseModel):
    task_id: int | None = None


@router.get("/board")
def board(
    user: Annotated[sqlite3.Row, Depends(active_user)],
    conn: Annotated[sqlite3.Connection, Depends(get_db)],
    pack_id: int | None = Query(default=None),
) -> dict[str, Any]:
    pack = None
    if pack_id is not None:
        pack = conn.execute(
            "SELECT * FROM packs WHERE id = ? AND deleted_at IS NULL", (pack_id,)
        ).fetchone()
    if pack is None:
        pack = active_pack(conn)
    if pack is None:
        return {"round": None, "tasks": [], "me": user_out(user)}

    tasks = [
        task_payload(conn, row["id"])
        for row in conn.execute(
            "SELECT id FROM tasks WHERE pack_id = ? ORDER BY CAST(code AS INTEGER), code",
            (pack["id"],),
        )
    ]
    return {
        "round": {
            "id": pack["id"],
            "label": pack["round_label"],
            "source_filename": pack["source_filename"],
            # So a screen can tell it is looking at a retired round rather than
            # the live one — a member holding a task from the round that was
            # just swapped out would otherwise keep answering into it silently.
            "active": bool(pack["active"]),
            "deadline_at": pack["deadline_at"],
            "server_time": utcnow_iso(),
            "rows_per_query": rows_per_query(conn),
        },
        "tasks": tasks,
        "me": user_out(user),
    }


@router.post("/tasks/{task_id}/claim")
def claim_task(
    task_id: int,
    user: Annotated[sqlite3.Row, Depends(active_user)],
    conn: Annotated[sqlite3.Connection, Depends(get_db)],
):
    cursor = conn.execute(
        "UPDATE tasks SET owner_id = ?, claimed_at = ?, version = version + 1 "
        "WHERE id = ? AND owner_id IS NULL",
        (user["id"], utcnow_iso(), task_id),
    )
    if cursor.rowcount != 1:
        current = task_payload(conn, task_id)
        # Claiming a task you already hold is not a conflict, it is a no-op.
        if current["owner"] and current["owner"]["id"] == user["id"]:
            return {"task": current}
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={"detail": "Already claimed", "owner": current["owner"]},
        )
    return {"task": task_payload(conn, task_id)}


@router.post("/tasks/{task_id}/release")
def release_task(
    task_id: int,
    user: Annotated[sqlite3.Row, Depends(active_user)],
    conn: Annotated[sqlite3.Connection, Depends(get_db)],
) -> dict[str, Any]:
    task = load_task(conn, task_id)
    if user["role"] != "admin" and task["owner_id"] != user["id"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Not your task"
        )
    conn.execute(
        "UPDATE tasks SET owner_id = NULL, claimed_at = NULL, version = version + 1 "
        "WHERE id = ?",
        (task_id,),
    )
    return {"task": task_payload(conn, task_id)}


@router.post("/presence")
def heartbeat(
    payload: PresenceRequest,
    user: Annotated[sqlite3.Row, Depends(active_user)],
    conn: Annotated[sqlite3.Connection, Depends(get_db)],
) -> dict[str, Any]:
    conn.execute(
        "INSERT INTO presence (user_id, task_id, last_seen_at) VALUES (?, ?, ?) "
        "ON CONFLICT(user_id) DO UPDATE SET task_id = excluded.task_id, "
        "last_seen_at = excluded.last_seen_at",
        (user["id"], payload.task_id, utcnow_iso()),
    )
    return {"ok": True}
