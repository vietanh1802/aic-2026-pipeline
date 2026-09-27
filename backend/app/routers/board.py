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

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from app.auth.deps import active_user
from app.db.connection import get_db, utcnow_iso
from app.routers._shared import (
    active_pack,
    rows_per_query,
    task_payload,
    user_out,
)

router = APIRouter(prefix="/api", tags=["board"])


class PresenceRequest(BaseModel):
    task_id: int | None = None


def team_size(conn: sqlite3.Connection) -> int:
    """Số người ĐI THI, không tính admin.

    Mẫu số của cột "số người đã làm" trên bảng. Đếm từ CSDL chứ không viết cứng
    5: thêm hay khoá một tài khoản là con số phải đổi theo, mà một mẫu số sai
    thì cả cột trở thành vô nghĩa.

    Tài khoản admin bị loại vì nó là tài khoản quản trị, không phải một suất
    trong nhóm. Nếu admin có làm bài thì tử số vẫn đếm họ — thà hiện 6/5 một
    lần còn hơn giấu công của một người.
    """
    return int(
        conn.execute(
            "SELECT COUNT(*) AS n FROM users "
            "WHERE role != 'admin' AND disabled = 0"
        ).fetchone()["n"]
    )


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
        return {
            "round": None,
            "tasks": [],
            "me": user_out(user),
            "team_size": team_size(conn),
        }

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
        "team_size": team_size(conn),
    }


# ── Nhận / Nhả đã bỏ ───────────────────────────────────────────────────────
# POST /tasks/{id}/claim và /release từng là cách giành quyền sửa một câu: một
# người giữ, những người khác chỉ đọc. Cách đó buộc cả nhóm chờ nhau, và ai vào
# sau thì sửa đè lên danh sách của người trước.
#
# Giờ mỗi người có danh sách riêng cho mỗi câu (answers.author_id), nên không
# còn gì để giành. Thứ thay thế là `contributors` trong task_payload: không phải
# "ai đang giữ câu này" mà "câu này đã có ai làm, được bao nhiêu dòng".
#
# Cột tasks.owner_id và claimed_at vẫn còn trong CSDL và vẫn được trả ra dưới
# tên `owner`, nhưng KHÔNG ai ghi vào chúng nữa. Giữ lại vì đó là bằng chứng ai
# từng giành câu nào, và xoá cột trong SQLite là dựng lại cả bảng.


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
