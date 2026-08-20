from app.db.migrate import migrate


def _tables(conn):
    return {
        row["name"]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    }


def test_migrate_creates_the_tables_we_kept(conn):
    assert {
        "users", "sessions", "packs", "tasks", "answers", "presence", "settings",
    } <= _tables(conn)


def test_migrate_drops_what_the_spec_left_behind(conn):
    names = _tables(conn)
    assert "edit_requests" not in names
    assert "video_cache" not in names


def test_pragmas_are_set(conn):
    assert conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_migrate_is_idempotent(conn):
    migrate(conn)
    migrate(conn)
