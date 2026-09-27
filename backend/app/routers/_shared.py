# -*- coding: utf-8 -*-
"""Helpers the board, answer and export routers all need.

Split out of dev's single prototype router so each router stays readable. The
sort_key arithmetic is the part worth reading twice: rank is derived at read
time with ROW_NUMBER(), and moving a row is one UPDATE to the midpoint of its
new neighbours rather than renumbering everything below it.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import HTTPException, status

from app.settings_store import all_settings

# How long a heartbeat counts for. Presence is polled every few seconds, so this
# is generous enough to survive a slow request and short enough that a closed
# tab stops showing as present within half a minute.
PRESENCE_WINDOW_SECONDS = 30


def cutoff_iso(seconds: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(seconds=seconds)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )


def user_out(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        "id": row["id"],
        "username": row["username"],
        "display_name": row["display_name"],
        "role": row["role"],
    }


def rows_per_query(conn: sqlite3.Connection) -> int:
    return int(all_settings(conn).get("export.rows_per_query", 100))


def active_pack(conn: sqlite3.Connection) -> sqlite3.Row | None:
    """The one round everybody is working in, or None before the first import.

    One function because there were two spellings of this query and they did not
    agree: /api/packs/active was a bare `WHERE active = 1` taking whatever row
    came back first, while /api/board ordered by imported_at. Neither excluded a
    deleted pack. Two screens disagreeing about which round is live is precisely
    the confusion this whole change is meant to end.
    """
    return conn.execute(
        "SELECT * FROM packs WHERE active = 1 AND deleted_at IS NULL "
        "ORDER BY imported_at DESC, id DESC LIMIT 1"
    ).fetchone()


def load_pack(conn: sqlite3.Connection, pack_id: int) -> sqlite3.Row:
    """A pack by id, deleted ones included — admin screens have to see those."""
    row = conn.execute("SELECT * FROM packs WHERE id = ?", (pack_id,)).fetchone()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Không có vòng này"
        )
    return row


def pack_counts(conn: sqlite3.Connection, pack_id: int) -> tuple[int, int]:
    """(tasks, answers) — what an admin needs before retiring or deleting one."""
    tasks = conn.execute(
        "SELECT COUNT(*) AS n FROM tasks WHERE pack_id = ?", (pack_id,)
    ).fetchone()["n"]
    answers = conn.execute(
        "SELECT COUNT(*) AS n FROM answers a JOIN tasks t ON t.id = a.task_id "
        "WHERE t.pack_id = ?",
        (pack_id,),
    ).fetchone()["n"]
    return int(tasks), int(answers)


def pack_payload(conn: sqlite3.Connection, row: sqlite3.Row) -> dict[str, Any]:
    tasks, answers = pack_counts(conn, row["id"])
    who = conn.execute(
        "SELECT * FROM users WHERE id = ?", (row["imported_by"],)
    ).fetchone()
    return {
        "id": row["id"],
        "label": row["round_label"],
        "source_filename": row["source_filename"],
        "imported_at": row["imported_at"],
        "imported_by": user_out(who),
        "deadline_at": row["deadline_at"],
        "active": bool(row["active"]),
        "deleted_at": row["deleted_at"],
        "task_count": tasks,
        "answer_count": answers,
    }


def load_task(conn: sqlite3.Connection, task_id: int) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="No such task"
        )
    return row


def contributors(conn: sqlite3.Connection, task_id: int) -> list[dict[str, Any]]:
    """Ai đã có đáp án cho câu này, và bao nhiêu dòng.

    Một truy vấn gộp cho cả bảng thay vì mỗi người một lần: Board hiện 25 câu
    cùng lúc, mà mỗi câu tối đa 6 người — hỏi lẻ là 150 lượt truy vấn cho một
    lần tải trang.
    """
    return [
        {
            "id": r["id"],
            "username": r["username"],
            "display_name": r["display_name"],
            "count": r["n"],
        }
        for r in conn.execute(
            "SELECT u.id, u.username, u.display_name, COUNT(*) AS n "
            "  FROM answers a JOIN users u ON u.id = a.author_id "
            " WHERE a.task_id = ? "
            " GROUP BY u.id ORDER BY n DESC, u.username",
            (task_id,),
        )
    ]


def task_payload(conn: sqlite3.Connection, task_id: int) -> dict[str, Any]:
    row = conn.execute(
        "SELECT t.*, u.id AS owner_user_id, u.username AS owner_username, "
        "       u.display_name AS owner_display_name, u.role AS owner_role "
        "  FROM tasks t "
        "  LEFT JOIN users u ON u.id = t.owner_id "
        " WHERE t.id = ?",
        (task_id,),
    ).fetchone()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="No such task"
        )

    owner = None
    if row["owner_user_id"] is not None:
        owner = {
            "id": row["owner_user_id"],
            "username": row["owner_username"],
            "display_name": row["owner_display_name"],
            "role": row["owner_role"],
        }

    count = conn.execute(
        "SELECT COUNT(*) AS n, SUM(CASE WHEN origin='manual' THEN 1 ELSE 0 END) AS v "
        "FROM answers WHERE task_id = ?",
        (task_id,),
    ).fetchone()

    viewers = [
        {
            "id": r["id"],
            "username": r["username"],
            "display_name": r["display_name"],
            "last_seen_at": r["last_seen_at"],
        }
        for r in conn.execute(
            "SELECT u.id, u.username, u.display_name, p.last_seen_at "
            "  FROM presence p JOIN users u ON u.id = p.user_id "
            " WHERE p.task_id = ? AND p.last_seen_at >= ? "
            "   AND (? IS NULL OR p.user_id != ?) "
            " ORDER BY p.last_seen_at DESC",
            (
                task_id,
                cutoff_iso(PRESENCE_WINDOW_SECONDS),
                row["owner_id"],
                row["owner_id"],
            ),
        )
    ]

    updated = conn.execute(
        "SELECT MAX(updated_at) AS updated_at FROM answers WHERE task_id = ?",
        (task_id,),
    ).fetchone()["updated_at"]

    return {
        "id": row["id"],
        "pack_id": row["pack_id"],
        "code": row["code"],
        "type": row["type"],
        "query_text": row["query_text"],
        "question_text": row["question_text"],
        "n_events": row["n_events"],
        "event_labels": json.loads(row["event_labels"] or "[]"),
        # owner/claimed_at giữ lại cho tương thích ngược: bản frontend cũ đọc
        # chúng, và cột trong CSDL vẫn còn. Nhưng KHÔNG còn ai ghi vào chúng
        # nữa — endpoint claim/release đã bỏ. Xem `contributors` thay thế.
        "owner": owner,
        "answer_count": int(count["n"] or 0),
        "verified_count": int(count["v"] or 0),
        # Ai đã làm câu này và được bao nhiêu dòng. Thay cho "ai đang giữ câu
        # này" của mô hình Nhận/Nhả: giờ ai cũng làm được, nên thứ đáng biết
        # không phải là quyền sở hữu mà là câu nào đã có người ngó tới.
        "contributors": contributors(conn, task_id),
        "chosen_author_id": row["chosen_author_id"],
        "updated_at": updated or row["claimed_at"],
        "claimed_at": row["claimed_at"],
        "version": row["version"],
        "viewers": viewers,
    }


def answer_payload(conn: sqlite3.Connection, row: sqlite3.Row) -> dict[str, Any]:
    creator = conn.execute(
        "SELECT * FROM users WHERE id = ?", (row["created_by"],)
    ).fetchone()
    updater = (
        conn.execute("SELECT * FROM users WHERE id = ?", (row["updated_by"],)).fetchone()
        if row["updated_by"]
        else None
    )
    return {
        "id": row["id"],
        "task_id": row["task_id"],
        "rank": row["rank"],
        "video_id": row["video_id"],
        "frames": json.loads(row["frames"]),
        "answer_text": row["answer_text"],
        "origin": row["origin"],
        # Chủ của DANH SÁCH, khác created_by là người tạo ra đúng dòng này.
        # Frontend cần nó để biết dòng thuộc danh sách của ai.
        "author_id": row["author_id"],
        "created_by": user_out(creator),
        "updated_by": user_out(updater),
        "updated_at": row["updated_at"],
        "version": row["version"],
    }


def answers(
    conn: sqlite3.Connection, task_id: int, author_id: int | None = None
) -> list[dict[str, Any]]:
    """Danh sách xếp hạng của MỘT tác giả cho một câu.

    author_id=None trả về mọi tác giả gộp lại — chỉ dùng cho màn Export, nơi
    cần bày cả 5 danh sách cạnh nhau. Mọi chỗ khác phải truyền tác giả, nếu
    không hạng sẽ đánh số xuyên qua danh sách của người khác.
    """
    if author_id is None:
        rows = conn.execute(
            "SELECT ROW_NUMBER() OVER (PARTITION BY author_id ORDER BY sort_key, id) "
            "         AS rank, * "
            "  FROM answers WHERE task_id = ? ORDER BY author_id, sort_key, id",
            (task_id,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT ROW_NUMBER() OVER (ORDER BY sort_key, id) AS rank, * "
            "  FROM answers WHERE task_id = ? AND author_id = ? "
            "  ORDER BY sort_key, id",
            (task_id, author_id),
        ).fetchall()
    return [answer_payload(conn, row) for row in rows]


def answers_by_author(
    conn: sqlite3.Connection, task_id: int
) -> list[dict[str, Any]]:
    """Mỗi tác giả một khối, kèm số dòng — thứ màn Export bày ra để chọn."""
    grouped: dict[int, list[dict[str, Any]]] = {}
    for row in answers(conn, task_id, None):
        grouped.setdefault(row["author_id"], []).append(row)
    out = []
    for author_id, rows in grouped.items():
        who = conn.execute(
            "SELECT * FROM users WHERE id = ?", (author_id,)
        ).fetchone()
        out.append({"author": user_out(who), "count": len(rows), "answers": rows})
    # Nhiều dòng nhất lên trước: người làm kỹ nhất thường là người đáng chọn.
    out.sort(key=lambda g: -g["count"])
    return out


def renumber(conn: sqlite3.Connection, task_id: int, author_id: int) -> None:
    """Reset sort_key to 1, 2, 3… — only when two keys have collapsed together.

    Chỉ đánh lại TRONG danh sách của một tác giả. Đánh lại cả câu sẽ dẫm lên
    khoá sắp xếp của bốn người kia và xáo tung thứ tự của họ.
    """
    ids = [
        row["id"]
        for row in conn.execute(
            "SELECT id FROM answers WHERE task_id = ? AND author_id = ? "
            "ORDER BY sort_key, id",
            (task_id, author_id),
        )
    ]
    for index, answer_id in enumerate(ids, 1):
        conn.execute(
            "UPDATE answers SET sort_key = ? WHERE id = ?", (float(index), answer_id)
        )


def next_sort_key(conn: sqlite3.Connection, task_id: int, author_id: int) -> float:
    row = conn.execute(
        "SELECT COALESCE(MAX(sort_key), 0) + 1 AS k FROM answers "
        "WHERE task_id = ? AND author_id = ?",
        (task_id, author_id),
    ).fetchone()
    return float(row["k"])


def top_sort_key(conn: sqlite3.Connection, task_id: int, author_id: int) -> float:
    row = conn.execute(
        "SELECT MIN(sort_key) AS k FROM answers WHERE task_id = ? AND author_id = ?",
        (task_id, author_id),
    ).fetchone()
    if row["k"] is None:
        return 1.0
    return float(row["k"]) - 1.0


def after_sort_key(
    conn: sqlite3.Connection, task_id: int, after_id: int, author_id: int
) -> float:
    current = conn.execute(
        "SELECT sort_key FROM answers WHERE id = ? AND task_id = ? AND author_id = ?",
        (after_id, task_id, author_id),
    ).fetchone()
    if current is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="No such anchor"
        )
    nxt = conn.execute(
        "SELECT sort_key FROM answers WHERE task_id = ? AND author_id = ? "
        "AND sort_key > ? ORDER BY sort_key LIMIT 1",
        (task_id, author_id, current["sort_key"]),
    ).fetchone()
    if nxt is None:
        return float(current["sort_key"]) + 1.0
    gap = (float(nxt["sort_key"]) - float(current["sort_key"])) / 2
    if gap < 1e-9:
        renumber(conn, task_id, author_id)
        return after_sort_key(conn, task_id, after_id, author_id)
    return float(current["sort_key"]) + gap


def before_sort_key(
    conn: sqlite3.Connection, task_id: int, before_id: int, author_id: int
) -> float:
    current = conn.execute(
        "SELECT sort_key FROM answers WHERE id = ? AND task_id = ? AND author_id = ?",
        (before_id, task_id, author_id),
    ).fetchone()
    if current is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="No such anchor"
        )
    prev = conn.execute(
        "SELECT sort_key FROM answers WHERE task_id = ? AND author_id = ? "
        "AND sort_key < ? ORDER BY sort_key DESC LIMIT 1",
        (task_id, author_id, current["sort_key"]),
    ).fetchone()
    if prev is None:
        return float(current["sort_key"]) - 1.0
    gap = (float(current["sort_key"]) - float(prev["sort_key"])) / 2
    if gap < 1e-9:
        renumber(conn, task_id, author_id)
        return before_sort_key(conn, task_id, before_id, author_id)
    return float(prev["sort_key"]) + gap
