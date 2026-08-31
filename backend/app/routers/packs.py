# -*- coding: utf-8 -*-
"""Pack import: preview, then commit.

Preview writes nothing to the database. Commit creates the pack and all of its
tasks in one transaction, so "half a round imported" is not a state the board
can ever be in.
"""
from __future__ import annotations

import json
import secrets
import sqlite3
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel

from app import audit
from app.auth.deps import active_user, require_admin
from app.db.connection import get_db, utcnow_iso
from app.packs.parser import DEFAULT_PATTERN, ParsedTask, parse_zip
from app.routers._shared import active_pack

router = APIRouter(prefix="/api", tags=["packs"])

# token -> parsed tasks. Bounded by hand because a preview is a step in a form,
# not a session: an admin previews, edits the inferred questions, commits, and
# the entry is dropped. An expired preview just means uploading again.
_PREVIEWS: dict[str, list[ParsedTask]] = {}
_MAX_PREVIEWS = 8


def _as_dict(task: ParsedTask) -> dict[str, Any]:
    return {
        "filename": task.filename,
        "matched": task.matched,
        "error": task.error,
        "phase": task.phase,
        "code": task.code,
        "type": task.type,
        "query_text": task.query_text,
        "question_text": task.question_text,
        "n_events": task.n_events,
        "event_labels": task.event_labels,
        "warnings": task.warnings,
        "lines": task.lines,
    }


@router.post("/admin/packs/preview")
async def preview_pack(
    _: Annotated[sqlite3.Row, Depends(require_admin)],
    file: Annotated[UploadFile, File()],
    filename_pattern: Annotated[str, Form()] = DEFAULT_PATTERN,
) -> dict[str, Any]:
    try:
        tasks = parse_zip(await file.read(), filename_pattern)
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Could not read the archive: {error}",
        ) from error

    token = secrets.token_urlsafe(16)
    if len(_PREVIEWS) >= _MAX_PREVIEWS:
        _PREVIEWS.pop(next(iter(_PREVIEWS)))
    _PREVIEWS[token] = tasks

    return {
        "preview_token": token,
        "source_filename": file.filename or "",
        "files": [_as_dict(task) for task in tasks],
    }


class TaskEdit(BaseModel):
    filename: str
    question_text: str | None = None


class CommitRequest(BaseModel):
    preview_token: str
    round_label: str
    filename_pattern: str = DEFAULT_PATTERN
    source_filename: str = ""
    edits: list[TaskEdit] = []


@router.post("/admin/packs/commit", status_code=201)
def commit_pack(
    payload: CommitRequest,
    user: Annotated[sqlite3.Row, Depends(require_admin)],
    conn: Annotated[sqlite3.Connection, Depends(get_db)],
) -> dict[str, Any]:
    tasks = _PREVIEWS.get(payload.preview_token)
    if tasks is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="That preview has expired. Upload the pack again.",
        )

    edited = {edit.filename: edit.question_text for edit in payload.edits}
    matched = [task for task in tasks if task.matched]
    if not matched:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No file in the archive matched the pattern.",
        )

    now = utcnow_iso()
    conn.execute("BEGIN IMMEDIATE")
    try:
        # Imported inactive, and the round that is live is not touched.
        #
        # This used to run `UPDATE packs SET active = 0 WHERE active = 1` first,
        # which is how a whole round could vanish. /api/board only ever reads
        # the active pack, so any second import — a retry, a fixed regex, a
        # stray upload — retired the round being competed in, taking its tasks
        # and every answer under them off every screen at once. Nothing was
        # deleted and nothing said what had happened.
        #
        # Going live is now its own deliberate action: POST
        # /api/admin/packs/{id}/activate, from the rounds screen, after seeing
        # what is being swapped out.
        # Số vòng lấy từ chính tên file trong zip, không hỏi người nhập.
        #
        # `phase` vẫn được trình đọc tách ra từ trước, nhưng không có chỗ cất
        # nên export viết cứng "p1" — một gói vòng 2 xuất ra vẫn mang tên vòng
        # 1 và làm hỏng bài nộp. Lấy giá trị phổ biến nhất trong các file khớp:
        # 25 file cùng một vòng, nên bất đồng chỉ xảy ra khi trong zip lẫn file
        # của vòng khác, và lúc đó số đông là đáp án đúng.
        phases = [t.phase for t in matched if t.phase]
        phase = max(set(phases), key=phases.count) if phases else None

        cursor = conn.execute(
            "INSERT INTO packs (round_label, source_filename, filename_pattern, "
            "imported_by, imported_at, active, phase) VALUES (?, ?, ?, ?, ?, 0, ?)",
            (
                payload.round_label,
                payload.source_filename,
                payload.filename_pattern,
                user["id"],
                now,
                phase,
            ),
        )
        pack_id = cursor.lastrowid
        for task in matched:
            conn.execute(
                "INSERT INTO tasks (pack_id, code, type, query_text, question_text, "
                "n_events, event_labels) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    pack_id,
                    task.code,
                    task.type,
                    task.query_text,
                    edited.get(task.filename, task.question_text),
                    task.n_events,
                    json.dumps(task.event_labels, ensure_ascii=False),
                ),
            )
        audit.record(
            conn,
            user["id"],
            audit.PACK_IMPORT,
            f"pack:{pack_id}",
            f"Nhập vòng “{payload.round_label}” — {len(matched)} task, chưa kích hoạt",
            {"source_filename": payload.source_filename, "tasks": len(matched)},
        )
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise

    _PREVIEWS.pop(payload.preview_token, None)
    return {
        "pack_id": pack_id,
        "round_label": payload.round_label,
        "tasks_created": len(matched),
        "skipped": len(tasks) - len(matched),
        # The caller has to say so: the new round is not on anyone's board yet.
        "active": False,
    }


@router.get("/packs/active")
def read_active_pack(
    _: Annotated[sqlite3.Row, Depends(active_user)],
    conn: Annotated[sqlite3.Connection, Depends(get_db)],
) -> dict[str, Any]:
    row = active_pack(conn)
    return {"pack": dict(row) if row else None}
