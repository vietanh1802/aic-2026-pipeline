"""Emptying one task's basket.

`autofill mode="clear"` already drops the generated rows, which is the tactic
for changing the spread's step. This is the other half: throw away the whole
answer set for one query — the manual pins included — when the team looks at
the file it is about to submit and decides it is not worth submitting.

Scoped to one task on purpose. The export screen shows one CSV per task, so
"delete this one" has to mean the same thing there as it does here.
"""
import json

import pytest
from fastapi import HTTPException

from app.db.connection import utcnow_iso
from app.routers.answers import clear_answers


def _pack(conn):
    conn.execute(
        "INSERT INTO users (username, display_name, role, password_hash, "
        "must_change_password, disabled, created_at) VALUES ('nam','Nam','member','x',0,0,?)",
        (utcnow_iso(),),
    )
    conn.execute(
        "INSERT INTO packs (round_label, source_filename, filename_pattern, "
        "imported_by, imported_at, active) VALUES ('R1','p.zip','x',1,?,1)",
        (utcnow_iso(),),
    )
    conn.execute("INSERT INTO tasks (pack_id, code, type, query_text) VALUES (1,'01','kis','a')")
    conn.execute("INSERT INTO tasks (pack_id, code, type, query_text) VALUES (1,'02','kis','b')")
    return [row["id"] for row in conn.execute("SELECT id FROM tasks ORDER BY id")]


def _add(conn, task_id, frame, origin="manual"):
    conn.execute(
        "INSERT INTO answers (task_id, sort_key, video_id, frames, origin, "
        "created_by, updated_at, version) VALUES (?,?, 'L26_V071', ?, ?, 1, ?, 1)",
        (task_id, float(frame), json.dumps([frame]), origin, utcnow_iso()),
    )


def test_clearing_removes_every_row_of_that_task(conn):
    first, _second = _pack(conn)
    _add(conn, first, 1804, "manual")
    _add(conn, first, 1805, "auto")

    result = clear_answers(first, None, conn)

    assert result == {"removed": 2, "total": 0}
    assert conn.execute(
        "SELECT COUNT(*) AS n FROM answers WHERE task_id = ?", (first,)
    ).fetchone()["n"] == 0


def test_clearing_one_task_leaves_the_others_alone(conn):
    first, second = _pack(conn)
    _add(conn, first, 1804)
    _add(conn, second, 2900)

    clear_answers(first, None, conn)

    remaining = conn.execute("SELECT task_id FROM answers").fetchall()
    assert [row["task_id"] for row in remaining] == [second]


def test_clearing_an_empty_basket_is_not_an_error(conn):
    first, _second = _pack(conn)

    assert clear_answers(first, None, conn) == {"removed": 0, "total": 0}


def test_clearing_an_unknown_task_is_404(conn):
    _pack(conn)

    with pytest.raises(HTTPException) as caught:
        clear_answers(9999, None, conn)

    assert caught.value.status_code == 404
