# -*- coding: utf-8 -*-
"""The log, and putting back what a click threw away."""
import json

import pytest
from fastapi import HTTPException

from app import audit
from app.db.connection import utcnow_iso


def _user(conn, username="nam", role="member"):
    cursor = conn.execute(
        "INSERT INTO users (username, display_name, role, password_hash, "
        "must_change_password, disabled, created_at) VALUES (?, ?, ?, 'x', 0, 0, ?)",
        (username, username, role, utcnow_iso()),
    )
    return cursor.lastrowid


def _task(conn, user_id):
    conn.execute(
        "INSERT INTO packs (round_label, source_filename, filename_pattern, "
        "imported_by, imported_at, active) VALUES ('R1', 'p.zip', 'x', ?, ?, 1)",
        (user_id, utcnow_iso()),
    )
    cursor = conn.execute(
        "INSERT INTO tasks (pack_id, code, type, query_text) VALUES (1, '07', 'kis', 'q')"
    )
    return cursor.lastrowid


def _answer(conn, task_id, user_id, sort_key, frames=(10,), origin="manual"):
    cursor = conn.execute(
        "INSERT INTO answers (task_id, sort_key, video_id, frames, answer_text, "
        "origin, created_by, updated_by, updated_at, version) "
        "VALUES (?, ?, 'L01_V001', ?, NULL, ?, ?, ?, ?, 1)",
        (task_id, sort_key, json.dumps(list(frames)), origin, user_id, user_id, utcnow_iso()),
    )
    return cursor.lastrowid


def _rows(conn, task_id):
    return conn.execute(
        "SELECT * FROM answers WHERE task_id = ? ORDER BY sort_key, id", (task_id,)
    ).fetchall()


def test_clearing_a_basket_is_logged_with_the_rows_it_removed(conn):
    from app.routers.answers import clear_answers

    user_id = _user(conn)
    user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    task = _task(conn, user_id)
    for i in range(1, 4):
        _answer(conn, task, user_id, float(i), frames=(i * 100,))

    result = clear_answers(task, user, conn)

    assert result["removed"] == 3
    assert _rows(conn, task) == []
    entry = conn.execute(
        "SELECT * FROM audit_log WHERE action = ?", (audit.ANSWERS_CLEAR,)
    ).fetchone()
    assert audit.restorable_count(entry) == 3
    assert "task 07" in entry["summary"]


def test_restore_puts_the_rows_back_where_they_were(conn):
    from app.routers.answers import clear_answers

    user_id = _user(conn)
    user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    task = _task(conn, user_id)
    for i in range(1, 4):
        _answer(conn, task, user_id, float(i), frames=(i * 100,))

    clear_answers(task, user, conn)
    entry_id = conn.execute(
        "SELECT id FROM audit_log WHERE action = ?", (audit.ANSWERS_CLEAR,)
    ).fetchone()["id"]

    assert audit.restore_answers(conn, entry_id, user_id) == {"restored": 3, "skipped": 0}

    rows = _rows(conn, task)
    assert [json.loads(r["frames"]) for r in rows] == [[100], [200], [300]]
    # Original sort_key, so rank 1 comes back as rank 1 rather than landing at
    # the bottom of a list whose order is a fifth of the score.
    assert [r["sort_key"] for r in rows] == [1.0, 2.0, 3.0]


def test_restoring_twice_is_refused(conn):
    from app.routers.answers import clear_answers

    user_id = _user(conn)
    user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    task = _task(conn, user_id)
    _answer(conn, task, user_id, 1.0)

    clear_answers(task, user, conn)
    entry_id = conn.execute(
        "SELECT id FROM audit_log WHERE action = ?", (audit.ANSWERS_CLEAR,)
    ).fetchone()["id"]

    audit.restore_answers(conn, entry_id, user_id)
    with pytest.raises(HTTPException) as raised:
        audit.restore_answers(conn, entry_id, user_id)
    assert raised.value.status_code == 409
    assert len(_rows(conn, task)) == 1


def test_deleting_one_row_is_logged_and_restorable(conn):
    from app.routers.answers import delete_answer

    user_id = _user(conn)
    user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    task = _task(conn, user_id)
    keep = _answer(conn, task, user_id, 1.0, frames=(100,))
    drop = _answer(conn, task, user_id, 2.0, frames=(200,))

    delete_answer(drop, user, conn)
    assert [r["id"] for r in _rows(conn, task)] == [keep]

    entry_id = conn.execute(
        "SELECT id FROM audit_log WHERE action = ?", (audit.ANSWER_DELETE,)
    ).fetchone()["id"]
    audit.restore_answers(conn, entry_id, user_id)
    assert [json.loads(r["frames"]) for r in _rows(conn, task)] == [[100], [200]]


def test_autofill_clear_spares_the_manual_rows_and_logs_only_the_auto_ones(conn):
    from app.routers.answers import AutofillRequest, autofill_answers

    user_id = _user(conn)
    user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    task = _task(conn, user_id)
    _answer(conn, task, user_id, 1.0, frames=(100,), origin="manual")
    _answer(conn, task, user_id, 2.0, frames=(125,), origin="auto")
    _answer(conn, task, user_id, 3.0, frames=(150,), origin="auto")

    result = autofill_answers(task, AutofillRequest(mode="clear"), user, conn)

    assert result["removed"] == 2
    assert result["total"] == 1
    entry = conn.execute(
        "SELECT * FROM audit_log WHERE action = ?", (audit.ANSWERS_AUTOFILL_CLEAR,)
    ).fetchone()
    assert audit.restorable_count(entry) == 2


def test_a_deletion_that_removed_nothing_writes_no_entry(conn):
    from app.routers.answers import clear_answers

    user_id = _user(conn)
    user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    task = _task(conn, user_id)

    assert clear_answers(task, user, conn)["removed"] == 0
    assert conn.execute("SELECT COUNT(*) AS n FROM audit_log").fetchone()["n"] == 0


def test_restore_skips_rows_whose_task_is_gone_rather_than_refusing_all(conn):
    from app.routers.answers import clear_answers

    user_id = _user(conn)
    user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    task = _task(conn, user_id)
    _answer(conn, task, user_id, 1.0)

    clear_answers(task, user, conn)
    entry_id = conn.execute(
        "SELECT id FROM audit_log WHERE action = ?", (audit.ANSWERS_CLEAR,)
    ).fetchone()["id"]
    conn.execute("DELETE FROM tasks WHERE id = ?", (task,))

    assert audit.restore_answers(conn, entry_id, user_id) == {"restored": 0, "skipped": 1}


def test_a_non_destructive_entry_cannot_be_restored(conn):
    user_id = _user(conn, "admin", "admin")
    entry_id = audit.record(
        conn, user_id, audit.PACK_ACTIVATE, "pack:1", "Kích hoạt vòng 1"
    )
    with pytest.raises(HTTPException) as raised:
        audit.restore_answers(conn, entry_id, user_id)
    assert raised.value.status_code == 400


def test_recent_names_who_did_it(conn):
    user_id = _user(conn, "phat")
    audit.record(conn, user_id, audit.PACK_IMPORT, "pack:3", "Nhập vòng 3")
    entries = audit.recent(conn)
    assert entries[0]["by"]["username"] == "phat"
    assert entries[0]["restorable"] == 0
