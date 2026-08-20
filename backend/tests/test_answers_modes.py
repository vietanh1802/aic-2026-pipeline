"""Autofill modes. `clear` exists because `replace_auto` deletes and refills in
one call, which looks like a no-op from the UI: 100 rows before, 100 after."""
import json

from app.db.connection import utcnow_iso


def _task(conn):
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
    return conn.execute("SELECT id FROM tasks").fetchone()["id"]


def _add(conn, task_id, frame, origin):
    conn.execute(
        "INSERT INTO answers (task_id, sort_key, video_id, frames, origin, "
        "created_by, updated_at, version) VALUES (?,?, 'L26_V071', ?, ?, 1, ?, 1)",
        (task_id, float(frame), json.dumps([frame]), origin, utcnow_iso()),
    )


def test_clearing_removes_only_the_generated_rows(conn):
    task_id = _task(conn)
    _add(conn, task_id, 1804, "manual")
    for frame in (1805, 1803, 1806):
        _add(conn, task_id, frame, "auto")

    removed = conn.execute(
        "DELETE FROM answers WHERE task_id = ? AND origin = 'auto'", (task_id,)
    ).rowcount
    remaining = conn.execute(
        "SELECT origin, frames FROM answers WHERE task_id = ?", (task_id,)
    ).fetchall()

    assert removed == 3
    assert [row["origin"] for row in remaining] == ["manual"]
    assert json.loads(remaining[0]["frames"]) == [1804]
