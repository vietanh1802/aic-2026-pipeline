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
        "INSERT INTO answers (task_id, author_id, sort_key, video_id, frames, "
        "origin, created_by, updated_at, version) "
        "VALUES (?, 1, ?, 'L26_V071', ?, ?, 1, ?, 1)",
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


# ── Sửa một dòng: chỉ sửa được dòng của CHÍNH MÌNH ──────────────────────────
#
# delete_answer và reorder_answer đều lọc theo author_id ngay từ đầu, riêng
# patch_answer thì không — lọt lưới lúc tách danh sách theo người. Với câu Q&A
# thì ô answer_text chính là thứ được chấm, nên đó là lỗ nghiêm trọng nhất
# trong ba đường ghi.


def _user(conn, username):
    cursor = conn.execute(
        "INSERT INTO users (username, display_name, role, password_hash, "
        "must_change_password, disabled, created_at) "
        "VALUES (?, ?, 'member', 'x', 0, 0, ?)",
        (username, username.upper(), utcnow_iso()),
    )
    return conn.execute(
        "SELECT * FROM users WHERE id = ?", (cursor.lastrowid,)
    ).fetchone()


def _qa_row(conn, task_id, author_id, text):
    cursor = conn.execute(
        "INSERT INTO answers (task_id, author_id, sort_key, video_id, frames, "
        "answer_text, origin, created_by, updated_at, version) "
        "VALUES (?, ?, 1.0, 'L27_V010', '[5550]', ?, 'manual', ?, ?, 1)",
        (task_id, author_id, text, author_id, utcnow_iso()),
    )
    return cursor.lastrowid


def test_patching_my_own_answer_text_works(conn):
    from app.routers.answers import AnswerPatchRequest, patch_answer

    task_id = _task(conn)
    an = _user(conn, "an")
    answer_id = _qa_row(conn, task_id, an["id"], "hồ Gươm")

    patch_answer(
        answer_id,
        AnswerPatchRequest(answer_text='hồ "Gươm"', version=1),
        an,
        conn,
    )

    row = conn.execute(
        "SELECT answer_text, version FROM answers WHERE id = ?", (answer_id,)
    ).fetchone()
    assert row["answer_text"] == 'hồ "Gươm"'
    assert row["version"] == 2


def test_patching_someone_elses_answer_is_refused(conn):
    import pytest
    from fastapi import HTTPException

    from app.routers.answers import AnswerPatchRequest, patch_answer

    task_id = _task(conn)
    an = _user(conn, "an")
    vanh = _user(conn, "vanh")
    answer_id = _qa_row(conn, task_id, an["id"], "hồ Gươm")

    with pytest.raises(HTTPException) as raised:
        patch_answer(
            answer_id,
            AnswerPatchRequest(answer_text="Vanh sửa trộm", version=1),
            vanh,
            conn,
        )
    # 404 chứ không 409: 409 nghĩa là "người khác vừa sửa, đọc lại rồi thử
    # lại" — một lời khuyên sai khi dòng đó vốn không phải của bạn.
    assert raised.value.status_code == 404
    assert (
        conn.execute(
            "SELECT answer_text FROM answers WHERE id = ?", (answer_id,)
        ).fetchone()["answer_text"]
        == "hồ Gươm"
    )
