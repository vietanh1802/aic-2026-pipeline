# -*- coding: utf-8 -*-
"""Rounds: many of them, one live at a time, and a log of every switch.

Importing used to be the only way a round changed, and it changed it silently —
the new pack went active and the old one went dark, taking its tasks and every
answer under it off every screen. Import now only imports. Which round the team
is working in is decided here, deliberately, by an admin who can see what is
being swapped out first.

Deletion is soft. Partly because it has to be — tasks.pack_id and
presence.task_id carry no ON DELETE CASCADE, so a hard delete raises a foreign
key error against a round anyone has looked at — and partly because the whole
point of this change is that losing a round's work should stop happening.
"""
from __future__ import annotations

import sqlite3
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from app import audit
from app.auth.deps import require_admin
from app.db.connection import get_db, utcnow_iso
from app.routers._shared import active_pack, load_pack, pack_counts, pack_payload

router = APIRouter(prefix="/api/admin", tags=["rounds"])


class PackPatch(BaseModel):
    round_label: str | None = None
    # "" clears the countdown; None leaves it alone. They are different requests
    # and a single optional field cannot express both, so empty string is the
    # clear. Anything else is stored as given.
    deadline_at: str | None = None


@router.get("/packs")
def list_packs(
    _: Annotated[sqlite3.Row, Depends(require_admin)],
    conn: Annotated[sqlite3.Connection, Depends(get_db)],
    include_deleted: bool = Query(default=True),
) -> dict[str, Any]:
    where = "" if include_deleted else " WHERE deleted_at IS NULL"
    rows = conn.execute(
        f"SELECT * FROM packs{where} ORDER BY imported_at DESC, id DESC"
    ).fetchall()
    return {"packs": [pack_payload(conn, row) for row in rows]}


@router.post("/packs/{pack_id}/activate")
def activate_pack(
    pack_id: int,
    user: Annotated[sqlite3.Row, Depends(require_admin)],
    conn: Annotated[sqlite3.Connection, Depends(get_db)],
) -> dict[str, Any]:
    pack = load_pack(conn, pack_id)
    if pack["deleted_at"]:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Vòng này đã xoá. Khôi phục trước khi kích hoạt.",
        )

    previous = active_pack(conn)
    conn.execute("BEGIN IMMEDIATE")
    try:
        # Both statements or neither: a moment with no active round is a board
        # that says "chưa có gói truy vấn" to everyone looking at it.
        conn.execute("UPDATE packs SET active = 0 WHERE active = 1")
        conn.execute("UPDATE packs SET active = 1 WHERE id = ?", (pack_id,))
        tasks, answers = pack_counts(conn, pack_id)
        was = (
            f" thay cho “{previous['round_label']}”"
            if previous is not None and previous["id"] != pack_id
            else ""
        )
        audit.record(
            conn,
            user["id"],
            audit.PACK_ACTIVATE,
            f"pack:{pack_id}",
            f"Kích hoạt vòng “{pack['round_label']}” ({tasks} task, {answers} đáp án){was}",
            {
                "previous_pack_id": previous["id"] if previous else None,
                "previous_label": previous["round_label"] if previous else None,
            },
        )
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise

    return {"pack": pack_payload(conn, load_pack(conn, pack_id))}


@router.patch("/packs/{pack_id}")
def patch_pack(
    pack_id: int,
    payload: PackPatch,
    user: Annotated[sqlite3.Row, Depends(require_admin)],
    conn: Annotated[sqlite3.Connection, Depends(get_db)],
) -> dict[str, Any]:
    pack = load_pack(conn, pack_id)

    label = pack["round_label"]
    if payload.round_label is not None:
        label = payload.round_label.strip()
        if not label:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Tên vòng không được để trống.",
            )

    deadline = pack["deadline_at"]
    if payload.deadline_at is not None:
        deadline = payload.deadline_at.strip() or None

    conn.execute(
        "UPDATE packs SET round_label = ?, deadline_at = ? WHERE id = ?",
        (label, deadline, pack_id),
    )
    if label != pack["round_label"]:
        audit.record(
            conn,
            user["id"],
            audit.PACK_RENAME,
            f"pack:{pack_id}",
            f"Đổi tên vòng “{pack['round_label']}” → “{label}”",
        )
    return {"pack": pack_payload(conn, load_pack(conn, pack_id))}


@router.delete("/packs/{pack_id}")
def delete_pack(
    pack_id: int,
    user: Annotated[sqlite3.Row, Depends(require_admin)],
    conn: Annotated[sqlite3.Connection, Depends(get_db)],
) -> dict[str, Any]:
    pack = load_pack(conn, pack_id)
    if pack["active"]:
        # Refusing rather than silently deactivating: deleting the live round
        # would empty every board in the building, which is the failure this
        # whole change exists to stop. Switch rounds first, on purpose.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Đây là vòng đang dùng. Kích hoạt vòng khác trước khi xoá.",
        )
    if pack["deleted_at"]:
        return {"pack": pack_payload(conn, pack)}

    tasks, answers = pack_counts(conn, pack_id)
    conn.execute(
        "UPDATE packs SET deleted_at = ? WHERE id = ?", (utcnow_iso(), pack_id)
    )
    audit.record(
        conn,
        user["id"],
        audit.PACK_DELETE,
        f"pack:{pack_id}",
        f"Xoá vòng “{pack['round_label']}” ({tasks} task, {answers} đáp án)",
        {"tasks": tasks, "answers": answers},
    )
    return {"pack": pack_payload(conn, load_pack(conn, pack_id))}


@router.post("/packs/{pack_id}/restore")
def restore_pack(
    pack_id: int,
    user: Annotated[sqlite3.Row, Depends(require_admin)],
    conn: Annotated[sqlite3.Connection, Depends(get_db)],
) -> dict[str, Any]:
    pack = load_pack(conn, pack_id)
    if pack["deleted_at"]:
        conn.execute("UPDATE packs SET deleted_at = NULL WHERE id = ?", (pack_id,))
        audit.record(
            conn,
            user["id"],
            audit.PACK_RESTORE,
            f"pack:{pack_id}",
            f"Khôi phục vòng “{pack['round_label']}”",
        )
    return {"pack": pack_payload(conn, load_pack(conn, pack_id))}


@router.get("/audit")
def read_audit(
    _: Annotated[sqlite3.Row, Depends(require_admin)],
    conn: Annotated[sqlite3.Connection, Depends(get_db)],
    limit: int = Query(default=100, ge=1, le=500),
) -> dict[str, Any]:
    return {"entries": audit.recent(conn, limit)}


@router.post("/audit/{entry_id}/restore")
def restore_from_audit(
    entry_id: int,
    user: Annotated[sqlite3.Row, Depends(require_admin)],
    conn: Annotated[sqlite3.Connection, Depends(get_db)],
) -> dict[str, Any]:
    return audit.restore_answers(conn, entry_id, user["id"])
