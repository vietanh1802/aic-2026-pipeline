from app.db.connection import utcnow_iso


def _seed(conn):
    for username in ("nam", "phat"):
        conn.execute(
            "INSERT INTO users (username, display_name, role, password_hash, "
            "must_change_password, disabled, created_at) VALUES (?, ?, 'member', 'x', 0, 0, ?)",
            (username, username, utcnow_iso()),
        )
    conn.execute(
        "INSERT INTO packs (round_label, source_filename, filename_pattern, "
        "imported_by, imported_at, active) VALUES ('R1', 'p.zip', 'x', 1, ?, 1)",
        (utcnow_iso(),),
    )
    conn.execute("INSERT INTO tasks (pack_id, code, type, query_text) VALUES (1, '01', 'kis', 'a')")
    return conn.execute("SELECT id FROM tasks").fetchone()["id"]


def _claim(conn, task_id, user_id):
    """The exact statement board.claim_task runs."""
    cursor = conn.execute(
        "UPDATE tasks SET owner_id = ?, claimed_at = ?, version = version + 1 "
        "WHERE id = ? AND owner_id IS NULL",
        (user_id, utcnow_iso(), task_id),
    )
    return cursor.rowcount == 1


def test_first_claim_wins_and_the_second_loses(conn):
    task_id = _seed(conn)
    assert _claim(conn, task_id, 1) is True
    assert _claim(conn, task_id, 2) is False
    assert conn.execute("SELECT owner_id FROM tasks").fetchone()["owner_id"] == 1


def test_release_frees_the_task_for_someone_else(conn):
    task_id = _seed(conn)
    _claim(conn, task_id, 1)
    conn.execute(
        "UPDATE tasks SET owner_id = NULL, claimed_at = NULL, version = version + 1 WHERE id = ?",
        (task_id,),
    )
    assert _claim(conn, task_id, 2) is True


def test_claiming_bumps_the_version(conn):
    task_id = _seed(conn)
    before = conn.execute("SELECT version FROM tasks WHERE id = ?", (task_id,)).fetchone()["version"]
    _claim(conn, task_id, 1)
    after = conn.execute("SELECT version FROM tasks WHERE id = ?", (task_id,)).fetchone()["version"]
    assert after == before + 1


def test_task_payload_counts_answers_and_shows_the_owner(conn):
    from app.routers._shared import task_payload

    task_id = _seed(conn)
    _claim(conn, task_id, 1)
    for frame in (100, 200):
        conn.execute(
            "INSERT INTO answers (task_id, author_id, sort_key, video_id, frames, "
            "origin, created_by, updated_at, version) "
            "VALUES (?, 1, ?, 'L21_V015', ?, 'manual', 1, ?, 1)",
            (task_id, float(frame), f"[{frame}]", utcnow_iso()),
        )
    payload = task_payload(conn, task_id)
    assert payload["answer_count"] == 2
    assert payload["verified_count"] == 2
    assert payload["owner"]["display_name"] == "nam"


def test_presence_upserts_one_row_per_user(conn):
    task_id = _seed(conn)
    for _ in range(3):
        conn.execute(
            "INSERT INTO presence (user_id, task_id, last_seen_at) VALUES (?, ?, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET task_id = excluded.task_id, "
            "last_seen_at = excluded.last_seen_at",
            (2, task_id, utcnow_iso()),
        )
    assert conn.execute("SELECT COUNT(*) AS n FROM presence").fetchone()["n"] == 1
