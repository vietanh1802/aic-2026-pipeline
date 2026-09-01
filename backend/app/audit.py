# -*- coding: utf-8 -*-
"""The log that answers "ai đã bấm gì", and the undo built on top of it.

Nothing recorded who imported, who activated or who cleared, so when a round
stopped showing up nobody could say why. Every state change and every deletion
now writes one row here.

Deletions write more than a note: `detail` carries the rows themselves. A
cleared basket is a hundred rows of JSON, a few KB, and having them means a
misclick is recoverable instead of merely explainable.
"""
from __future__ import annotations

import json
import sqlite3
from typing import Any

from fastapi import HTTPException, status

from app.db.connection import utcnow_iso

# The whole vocabulary. Actions are matched exactly by the restore path, so a
# typo'd action string is a row that can never be undone — keep them here.
PACK_IMPORT = "pack.import"
PACK_ACTIVATE = "pack.activate"
PACK_RENAME = "pack.rename"
PACK_DELETE = "pack.delete"
# Không còn endpoint nào ghi ra hành động này: xoá vòng giờ là xoá thật,
# không có đường khôi phục. Giữ hằng số vì nhật ký cũ vẫn chứa nó và màn
# nhật ký phải đọc lại được những dòng đó.
PACK_RESTORE = "pack.restore"
ANSWER_DELETE = "answer.delete"
ANSWERS_CLEAR = "answers.clear"
ANSWERS_AUTOFILL_CLEAR = "answers.autofill_clear"
ANSWERS_RESTORE = "answers.restore"
# Chọn bài của ai làm bài nộp cho một câu. KHÔNG nằm trong RESTORABLE: nó không
# xoá gì, chỉ đổi một con trỏ, và "khôi phục" nó nghĩa là chọn lại người cũ —
# việc đó bấm một cái là xong, không cần cơ chế khôi phục.
TASK_CHOOSE_AUTHOR = "task.choose_author"
# Đổi số vòng trong tên file nộp (query-p2-15-qa.csv). Một cú bấm đổi tên cả 25
# file của gói, và đặt sai thì bài bị chấm hỏng mà không có dấu hiệu gì trên
# giao diện — nên phải biết ai đổi, đổi lúc nào, từ giá trị nào.
PACK_SET_PHASE = "pack.set_phase"

# Which actions put answer rows in `detail`, and so can be undone.
RESTORABLE = (ANSWER_DELETE, ANSWERS_CLEAR, ANSWERS_AUTOFILL_CLEAR)


def record(
    conn: sqlite3.Connection,
    user_id: int,
    action: str,
    target: str,
    summary: str,
    detail: dict[str, Any] | None = None,
) -> int:
    cursor = conn.execute(
        "INSERT INTO audit_log (at, user_id, action, target, summary, detail) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (
            utcnow_iso(),
            user_id,
            action,
            target,
            summary,
            json.dumps(detail, ensure_ascii=False) if detail is not None else None,
        ),
    )
    return int(cursor.lastrowid)


def snapshot_answers(conn: sqlite3.Connection, where: str, params: tuple) -> list[dict]:
    """The answer rows a DELETE with this WHERE clause is about to remove.

    Read before the delete, obviously — the point is to hold what the delete
    destroys. `id` is not kept: a restored row is a new row, and reusing the id
    would make the audit trail claim two different things share an identity.
    """
    return [
        {
            "task_id": row["task_id"],
            # Phải giữ author_id, không suy ra từ created_by lúc khôi phục:
            # dòng do admin tạo hộ có created_by khác author_id, đoán lại sẽ
            # chuyển bài của người này sang tên người khác.
            "author_id": row["author_id"],
            "sort_key": row["sort_key"],
            "video_id": row["video_id"],
            "frames": row["frames"],
            "answer_text": row["answer_text"],
            "origin": row["origin"],
            "created_by": row["created_by"],
            "updated_at": row["updated_at"],
        }
        for row in conn.execute(f"SELECT * FROM answers WHERE {where}", params)
    ]


def _detail(row: sqlite3.Row) -> dict[str, Any]:
    return json.loads(row["detail"]) if row["detail"] else {}


def restorable_count(row: sqlite3.Row) -> int:
    if row["action"] not in RESTORABLE or row["restored_at"]:
        return 0
    return len(_detail(row).get("answers", []))


def entry_payload(conn: sqlite3.Connection, row: sqlite3.Row) -> dict[str, Any]:
    who = conn.execute(
        "SELECT username, display_name FROM users WHERE id = ?", (row["user_id"],)
    ).fetchone()
    return {
        "id": row["id"],
        "at": row["at"],
        "action": row["action"],
        "target": row["target"],
        "summary": row["summary"],
        "by": {
            "id": row["user_id"],
            "username": who["username"] if who else "?",
            "display_name": who["display_name"] if who else "?",
        },
        "restorable": restorable_count(row),
        "restored_at": row["restored_at"],
    }


def recent(conn: sqlite3.Connection, limit: int = 100) -> list[dict[str, Any]]:
    return [
        entry_payload(conn, row)
        for row in conn.execute(
            "SELECT * FROM audit_log ORDER BY at DESC, id DESC LIMIT ?", (limit,)
        )
    ]


def restore_answers(
    conn: sqlite3.Connection, entry_id: int, user_id: int
) -> dict[str, Any]:
    """Put back the rows one logged deletion removed.

    Original `sort_key` is kept rather than appended, so the rows land where
    they were rather than at the bottom of a basket that is ranked. Two rows
    sharing a key is fine — the rank is derived with ROW_NUMBER() over
    (sort_key, id), so a tie breaks by insertion order.
    """
    row = conn.execute("SELECT * FROM audit_log WHERE id = ?", (entry_id,)).fetchone()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Không có mục nhật ký này"
        )
    if row["action"] not in RESTORABLE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Mục này không phải thao tác xoá — không có gì để khôi phục.",
        )
    if row["restored_at"]:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Đã khôi phục lúc {row['restored_at']}.",
        )

    answers = _detail(row).get("answers", [])
    if not answers:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Mục này không lưu lại dòng nào.",
        )

    now = utcnow_iso()
    conn.execute("BEGIN IMMEDIATE")
    try:
        restored = 0
        skipped = 0
        for answer in answers:
            # The task can have gone with its pack since. Skipping is right:
            # restoring 90 of 100 rows beats refusing all 100 over one.
            exists = conn.execute(
                "SELECT 1 FROM tasks WHERE id = ?", (answer["task_id"],)
            ).fetchone()
            if exists is None:
                skipped += 1
                continue
            conn.execute(
                "INSERT INTO answers (task_id, author_id, sort_key, video_id, "
                "frames, answer_text, origin, created_by, updated_by, "
                "updated_at, version) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)",
                (
                    answer["task_id"],
                    # Bản ghi cũ (xoá trước khi có nhiều người dùng) không có
                    # khoá này; rơi về created_by là đúng vì hồi đó mỗi câu chỉ
                    # một người làm.
                    answer.get("author_id") or answer["created_by"],
                    answer["sort_key"],
                    answer["video_id"],
                    answer["frames"],
                    answer["answer_text"],
                    answer["origin"],
                    answer["created_by"],
                    user_id,
                    now,
                ),
            )
            restored += 1

        conn.execute(
            "UPDATE audit_log SET restored_at = ? WHERE id = ?", (now, entry_id)
        )
        record(
            conn,
            user_id,
            ANSWERS_RESTORE,
            row["target"],
            f"Khôi phục {restored} dòng từ nhật ký #{entry_id}"
            + (f", bỏ qua {skipped} dòng có task đã mất" if skipped else ""),
        )
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise

    return {"restored": restored, "skipped": skipped}
