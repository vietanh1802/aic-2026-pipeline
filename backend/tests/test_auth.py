from app.auth.passwords import generate_password, hash_password, verify_password
from app.auth.sessions import create_session, delete_session, resolve_session
from app.db.connection import utcnow_iso


def _user(conn, username="nam", role="member", disabled=0):
    conn.execute(
        "INSERT INTO users (username, display_name, role, password_hash, "
        "must_change_password, disabled, created_at) VALUES (?, ?, ?, ?, 0, ?, ?)",
        (username, username, role, hash_password("hunter-hunter-2"), disabled, utcnow_iso()),
    )
    return conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()


def test_hash_round_trips():
    digest = hash_password("hunter-hunter-2")
    assert verify_password(digest, "hunter-hunter-2")
    assert not verify_password(digest, "hunter-hunter-3")


def test_generated_password_avoids_ambiguous_characters():
    for _ in range(50):
        password = generate_password()
        assert not set(password) & set("il1o0")
        assert password.count("-") == 2


def test_session_resolves_to_its_user(conn):
    user = _user(conn)
    token = create_session(conn, user["id"])
    assert resolve_session(conn, token)["username"] == "nam"


def test_deleted_session_stops_resolving(conn):
    user = _user(conn)
    token = create_session(conn, user["id"])
    delete_session(conn, token)
    assert resolve_session(conn, token) is None


def test_disabled_user_stops_resolving(conn):
    user = _user(conn, username="phat")
    token = create_session(conn, user["id"])
    conn.execute("UPDATE users SET disabled = 1 WHERE id = ?", (user["id"],))
    assert resolve_session(conn, token) is None


def test_expired_session_stops_resolving(conn):
    user = _user(conn, username="an")
    token = create_session(conn, user["id"])
    conn.execute(
        "UPDATE sessions SET expires_at = '2020-01-01T00:00:00Z' WHERE token = ?",
        (token,),
    )
    assert resolve_session(conn, token) is None


def test_unknown_token_resolves_to_nothing(conn):
    assert resolve_session(conn, "not-a-real-token") is None
