# -*- coding: utf-8 -*-
"""Rounds, and the bug that started all of this.

The complaint was that importing sometimes lost every task. Nothing deleted
them — the importer retired the round that was live, and only the live round is
ever shown. test_importing_leaves_the_live_round_alone is the regression.
"""
import json

import pytest
from fastapi import HTTPException

from app import audit
from app.db.connection import utcnow_iso
from app.db.migrations import STEPS, current_version
from app.routers._shared import active_pack, pack_counts


def _user(conn, username="admin", role="admin"):
    cursor = conn.execute(
        "INSERT INTO users (username, display_name, role, password_hash, "
        "must_change_password, disabled, created_at) VALUES (?, ?, ?, 'x', 0, 0, ?)",
        (username, username, role, utcnow_iso()),
    )
    return cursor.lastrowid


def _pack(conn, label, user_id, active=0):
    cursor = conn.execute(
        "INSERT INTO packs (round_label, source_filename, filename_pattern, "
        "imported_by, imported_at, active) VALUES (?, ?, 'x', ?, ?, ?)",
        (label, f"{label}.zip", user_id, utcnow_iso(), active),
    )
    return cursor.lastrowid


def _task(conn, pack_id, code="01", kind="kis"):
    cursor = conn.execute(
        "INSERT INTO tasks (pack_id, code, type, query_text) VALUES (?, ?, ?, 'q')",
        (pack_id, code, kind),
    )
    return cursor.lastrowid


def _answer(conn, task_id, user_id, sort_key, video="L01_V001", frames=(10,)):
    cursor = conn.execute(
        "INSERT INTO answers (task_id, author_id, sort_key, video_id, frames, "
        "answer_text, origin, created_by, updated_by, updated_at, version) "
        "VALUES (?, ?, ?, ?, ?, NULL, 'manual', ?, ?, ?, 1)",
        (task_id, user_id, sort_key, video, json.dumps(list(frames)), user_id,
         user_id, utcnow_iso()),
    )
    return cursor.lastrowid


# ── migrations ───────────────────────────────────────────────────────────────


def test_migrate_brings_the_database_to_the_latest_step(conn):
    assert current_version(conn) == STEPS[-1][0]


def test_packs_has_the_soft_delete_column(conn):
    columns = {r["name"] for r in conn.execute("PRAGMA table_info(packs)")}
    assert "deleted_at" in columns


def test_migrating_twice_changes_nothing(conn):
    from app.db.migrations import apply_steps

    before = current_version(conn)
    assert apply_steps(conn) == before
    assert apply_steps(conn) == before


# ── the regression ───────────────────────────────────────────────────────────


def test_importing_leaves_the_live_round_alone(conn):
    """A second import must not take the round being competed in off the board.

    The old commit ran `UPDATE packs SET active = 0 WHERE active = 1` before its
    INSERT, so this is the whole bug in one assertion.
    """
    admin = _user(conn)
    live = _pack(conn, "Vòng 1", admin, active=1)
    _task(conn, live)

    imported = _pack(conn, "Vòng 2", admin, active=0)  # what commit_pack now writes
    _task(conn, imported)

    still_live = active_pack(conn)
    assert still_live["id"] == live
    assert still_live["round_label"] == "Vòng 1"
    assert conn.execute(
        "SELECT active FROM packs WHERE id = ?", (imported,)
    ).fetchone()["active"] == 0


def test_active_pack_ignores_a_deleted_round(conn):
    admin = _user(conn)
    gone = _pack(conn, "Vòng cũ", admin, active=1)
    conn.execute("UPDATE packs SET deleted_at = ? WHERE id = ?", (utcnow_iso(), gone))
    assert active_pack(conn) is None


# ── activate / delete / restore ──────────────────────────────────────────────


def test_activating_swaps_exactly_one_round_in(conn):
    from app.routers.rounds import activate_pack

    admin_id = _user(conn)
    admin = conn.execute("SELECT * FROM users WHERE id = ?", (admin_id,)).fetchone()
    first = _pack(conn, "Vòng 1", admin_id, active=1)
    second = _pack(conn, "Vòng 2", admin_id, active=0)

    activate_pack(second, admin, conn)

    assert active_pack(conn)["id"] == second
    assert conn.execute("SELECT COUNT(*) AS n FROM packs WHERE active = 1").fetchone()["n"] == 1
    assert conn.execute("SELECT active FROM packs WHERE id = ?", (first,)).fetchone()["active"] == 0


def test_activating_names_what_it_replaced_in_the_log(conn):
    from app.routers.rounds import activate_pack

    admin_id = _user(conn)
    admin = conn.execute("SELECT * FROM users WHERE id = ?", (admin_id,)).fetchone()
    _pack(conn, "Vòng 1", admin_id, active=1)
    second = _pack(conn, "Vòng 2", admin_id, active=0)

    activate_pack(second, admin, conn)

    entry = conn.execute(
        "SELECT * FROM audit_log WHERE action = ? ORDER BY id DESC LIMIT 1",
        (audit.PACK_ACTIVATE,),
    ).fetchone()
    assert "Vòng 2" in entry["summary"]
    assert "Vòng 1" in entry["summary"]


def test_deleting_the_live_round_is_refused(conn):
    from app.routers.rounds import delete_pack

    admin_id = _user(conn)
    admin = conn.execute("SELECT * FROM users WHERE id = ?", (admin_id,)).fetchone()
    live = _pack(conn, "Vòng 1", admin_id, active=1)

    with pytest.raises(HTTPException) as raised:
        delete_pack(live, admin, conn)
    assert raised.value.status_code == 409
    assert conn.execute(
        "SELECT deleted_at FROM packs WHERE id = ?", (live,)
    ).fetchone()["deleted_at"] is None


def test_delete_is_soft_and_restore_undoes_it(conn):
    from app.routers.rounds import delete_pack, restore_pack

    admin_id = _user(conn)
    admin = conn.execute("SELECT * FROM users WHERE id = ?", (admin_id,)).fetchone()
    pack = _pack(conn, "Thử nghiệm", admin_id, active=0)
    task = _task(conn, pack)
    _answer(conn, task, admin_id, 1.0)

    delete_pack(pack, admin, conn)
    assert conn.execute(
        "SELECT deleted_at FROM packs WHERE id = ?", (pack,)
    ).fetchone()["deleted_at"] is not None
    # Soft: the work is still there, which is the entire point.
    assert pack_counts(conn, pack) == (1, 1)

    restore_pack(pack, admin, conn)
    assert conn.execute(
        "SELECT deleted_at FROM packs WHERE id = ?", (pack,)
    ).fetchone()["deleted_at"] is None


def test_renaming_a_round_is_logged_but_a_no_op_rename_is_not(conn):
    from app.routers.rounds import PackPatch, patch_pack

    admin_id = _user(conn)
    admin = conn.execute("SELECT * FROM users WHERE id = ?", (admin_id,)).fetchone()
    pack = _pack(conn, "Vòng 1", admin_id)

    patch_pack(pack, PackPatch(round_label="Vòng 1"), admin, conn)
    assert conn.execute(
        "SELECT COUNT(*) AS n FROM audit_log WHERE action = ?", (audit.PACK_RENAME,)
    ).fetchone()["n"] == 0

    patch_pack(pack, PackPatch(round_label="Sơ tuyển"), admin, conn)
    assert conn.execute(
        "SELECT round_label FROM packs WHERE id = ?", (pack,)
    ).fetchone()["round_label"] == "Sơ tuyển"
    assert conn.execute(
        "SELECT COUNT(*) AS n FROM audit_log WHERE action = ?", (audit.PACK_RENAME,)
    ).fetchone()["n"] == 1


def test_an_empty_label_is_refused(conn):
    from app.routers.rounds import PackPatch, patch_pack

    admin_id = _user(conn)
    admin = conn.execute("SELECT * FROM users WHERE id = ?", (admin_id,)).fetchone()
    pack = _pack(conn, "Vòng 1", admin_id)

    with pytest.raises(HTTPException) as raised:
        patch_pack(pack, PackPatch(round_label="   "), admin, conn)
    assert raised.value.status_code == 400


def test_blank_deadline_clears_it_and_none_leaves_it(conn):
    from app.routers.rounds import PackPatch, patch_pack

    admin_id = _user(conn)
    admin = conn.execute("SELECT * FROM users WHERE id = ?", (admin_id,)).fetchone()
    pack = _pack(conn, "Vòng 1", admin_id)

    patch_pack(pack, PackPatch(deadline_at="2026-08-21T12:00:00Z"), admin, conn)
    assert conn.execute(
        "SELECT deadline_at FROM packs WHERE id = ?", (pack,)
    ).fetchone()["deadline_at"] == "2026-08-21T12:00:00Z"

    patch_pack(pack, PackPatch(round_label="Vòng 1"), admin, conn)
    assert conn.execute(
        "SELECT deadline_at FROM packs WHERE id = ?", (pack,)
    ).fetchone()["deadline_at"] == "2026-08-21T12:00:00Z"

    patch_pack(pack, PackPatch(deadline_at=""), admin, conn)
    assert conn.execute(
        "SELECT deadline_at FROM packs WHERE id = ?", (pack,)
    ).fetchone()["deadline_at"] is None


# ── the upgrade path, which is the one production actually takes ─────────────


def test_step_one_upgrades_a_database_that_predates_it(tmp_path, monkeypatch):
    """A live database has `packs` already, without deleted_at and at version 0.

    The fixture above only ever exercises a database created from scratch, where
    the column arrives on an empty table. Production takes the other path: the
    table exists, rows are in it, and ALTER has to run against them. A failure
    here does not show up as a test going red — it shows up as the container
    refusing to start, the smoke test failing, and the deploy rolling back.
    """
    import sqlite3

    from app.db.migrate import migrate
    from app.db.migrations import apply_steps

    path = tmp_path / "old.db"
    old = sqlite3.connect(path, isolation_level=None)
    old.row_factory = sqlite3.Row
    # The packs table exactly as it was before this change.
    old.executescript(
        """
        CREATE TABLE users (
          id INTEGER PRIMARY KEY, username TEXT NOT NULL UNIQUE,
          display_name TEXT NOT NULL, role TEXT NOT NULL DEFAULT 'member',
          password_hash TEXT NOT NULL, must_change_password INTEGER NOT NULL DEFAULT 1,
          disabled INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL
        );
        CREATE TABLE packs (
          id INTEGER PRIMARY KEY, round_label TEXT NOT NULL,
          source_filename TEXT NOT NULL, filename_pattern TEXT NOT NULL,
          imported_by INTEGER NOT NULL REFERENCES users(id),
          imported_at TEXT NOT NULL, deadline_at TEXT,
          active INTEGER NOT NULL DEFAULT 1
        );
        """
    )
    old.execute(
        "INSERT INTO users (username, display_name, password_hash, created_at) "
        "VALUES ('admin', 'Admin', 'x', ?)",
        (utcnow_iso(),),
    )
    old.execute(
        "INSERT INTO packs (round_label, source_filename, filename_pattern, "
        "imported_by, imported_at, active) VALUES ('Vòng 1', 'p.zip', 'x', 1, ?, 1)",
        (utcnow_iso(),),
    )
    assert current_version(old) == 0
    assert "deleted_at" not in {r["name"] for r in old.execute("PRAGMA table_info(packs)")}

    monkeypatch.setenv("AIC_DB_PATH", str(path))
    migrate(old)

    columns = {r["name"] for r in old.execute("PRAGMA table_info(packs)")}
    assert "deleted_at" in columns
    assert current_version(old) == STEPS[-1][0]

    # The round that was already there survives, and reads as not-deleted.
    row = old.execute("SELECT * FROM packs WHERE round_label = 'Vòng 1'").fetchone()
    assert row["active"] == 1
    assert row["deleted_at"] is None
    # And it is the one active_pack() finds, which is what the board reads.
    assert active_pack(old)["round_label"] == "Vòng 1"

    # Re-running the whole startup path changes nothing, because the API runs it
    # on every boot.
    migrate(old)
    assert apply_steps(old) == STEPS[-1][0]
    assert old.execute("SELECT COUNT(*) AS n FROM packs").fetchone()["n"] == 1
    old.close()


def test_a_live_database_with_answers_survives_the_multi_user_steps(tmp_path, monkeypatch):
    """CSDL production: đã chạy bước 1, có đáp án thật, chưa có author_id.

    Bài test cũ dựng một CSDL đời 0 RỖNG. Nó chứng minh cột được thêm vào,
    nhưng không chứng minh dữ liệu sống sót — mà lần deploy đưa bước 2, 3, 4
    lên máy chủ sẽ chạy đúng trên một CSDL đang giữ bài của cả nhóm.

    Ba điều phải đúng, và không điều nào hiển nhiên:
      - không mất dòng đáp án nào
      - author_id được điền từ created_by, không để NULL (dòng NULL sẽ biến
        mất khỏi mọi giỏ và khỏi bài nộp mà không báo gì)
      - chosen_author_id bắt đầu bằng NULL, nên export TỪ CHỐI thay vì đoán
        bừa lấy bài của ai
    """
    import sqlite3

    from app.db.migrate import migrate

    path = tmp_path / "live.db"
    old = sqlite3.connect(path, isolation_level=None)
    old.row_factory = sqlite3.Row
    # Lược đồ đúng như bản đang chạy trên máy chủ: sau bước 1, trước bước 2.
    old.executescript(
        """
        CREATE TABLE users (
          id INTEGER PRIMARY KEY, username TEXT NOT NULL UNIQUE,
          display_name TEXT NOT NULL, role TEXT NOT NULL DEFAULT 'member',
          password_hash TEXT NOT NULL, must_change_password INTEGER NOT NULL DEFAULT 1,
          disabled INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL
        );
        CREATE TABLE packs (
          id INTEGER PRIMARY KEY, round_label TEXT NOT NULL,
          source_filename TEXT NOT NULL, filename_pattern TEXT NOT NULL,
          imported_by INTEGER NOT NULL REFERENCES users(id),
          imported_at TEXT NOT NULL, deadline_at TEXT,
          active INTEGER NOT NULL DEFAULT 1, deleted_at TEXT
        );
        CREATE TABLE tasks (
          id INTEGER PRIMARY KEY, pack_id INTEGER NOT NULL REFERENCES packs(id),
          code TEXT NOT NULL, type TEXT NOT NULL, query_text TEXT NOT NULL,
          question_text TEXT, n_events INTEGER, event_labels TEXT,
          owner_id INTEGER REFERENCES users(id), claimed_at TEXT,
          version INTEGER NOT NULL DEFAULT 1, UNIQUE (pack_id, code)
        );
        CREATE TABLE answers (
          id INTEGER PRIMARY KEY,
          task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
          sort_key REAL NOT NULL, video_id TEXT NOT NULL, frames TEXT NOT NULL,
          answer_text TEXT, origin TEXT NOT NULL,
          created_by INTEGER NOT NULL REFERENCES users(id),
          updated_by INTEGER REFERENCES users(id), updated_at TEXT NOT NULL,
          version INTEGER NOT NULL DEFAULT 1
        );
        PRAGMA user_version = 1;
        """
    )
    now = utcnow_iso()
    for name in ("vanh", "an"):
        old.execute(
            "INSERT INTO users (username, display_name, password_hash, created_at) "
            "VALUES (?, ?, 'x', ?)",
            (name, name.upper(), now),
        )
    old.execute(
        "INSERT INTO packs (round_label, source_filename, filename_pattern, "
        "imported_by, imported_at, active) VALUES ('Vòng 1', 'p.zip', 'x', 1, ?, 1)",
        (now,),
    )
    old.execute(
        "INSERT INTO tasks (pack_id, code, type, query_text) "
        "VALUES (1, '07', 'kis', 'q')"
    )
    # Hai người đã bỏ dòng vào cùng một câu thời còn dùng chung danh sách.
    for index, creator in enumerate([1, 1, 2, 2, 1], start=1):
        old.execute(
            "INSERT INTO answers (task_id, sort_key, video_id, frames, origin, "
            "created_by, updated_at, version) "
            "VALUES (1, ?, 'L21_V001', ?, 'manual', ?, ?, 1)",
            (float(index), f"[{index * 100}]", creator, now),
        )
    assert current_version(old) == 1

    monkeypatch.setenv("AIC_DB_PATH", str(path))
    migrate(old)

    assert current_version(old) == STEPS[-1][0]

    rows = old.execute("SELECT * FROM answers ORDER BY sort_key").fetchall()
    assert len(rows) == 5, "không được mất dòng nào"
    assert [r["author_id"] for r in rows] == [1, 1, 2, 2, 1]
    assert all(r["author_id"] is not None for r in rows)

    task = old.execute("SELECT * FROM tasks WHERE code = '07'").fetchone()
    assert task["chosen_author_id"] is None

    # Bảng của bước 3 và cột của bước 4 phải có mặt, nếu không thì tính năng
    # xem lại đường tìm và số vòng trong tên file nộp sẽ ném lỗi lúc chạy.
    tables = {
        r["name"] for r in old.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert "search_states" in tables
    assert "phase" in {r["name"] for r in old.execute("PRAGMA table_info(packs)")}

    # Khởi động lại lần nữa không được đổi gì — API chạy migrate mỗi lần boot.
    migrate(old)
    assert old.execute("SELECT COUNT(*) AS n FROM answers").fetchone()["n"] == 5
