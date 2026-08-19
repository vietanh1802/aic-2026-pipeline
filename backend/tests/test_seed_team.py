from scripts.seed_team import ACCOUNTS, DEFAULT_PASSWORD, seed_team


def test_creates_six_accounts(conn):
    created = seed_team(conn)
    assert len(created) == 6
    rows = conn.execute("SELECT username, role FROM users ORDER BY id").fetchall()
    assert [row["username"] for row in rows] == [a[0] for a in ACCOUNTS]
    assert [row["role"] for row in rows].count("admin") == 1
    assert [row["role"] for row in rows].count("member") == 5


def test_display_names_keep_their_diacritics(conn):
    seed_team(conn)
    names = {row["display_name"] for row in conn.execute("SELECT display_name FROM users")}
    assert {"VAnh", "Bằng", "Nam", "An", "Phát"} <= names


def test_nobody_is_forced_to_change_the_default(conn):
    # A default password that must be changed before it works is not a default.
    seed_team(conn)
    flags = [
        row["must_change_password"]
        for row in conn.execute("SELECT must_change_password FROM users")
    ]
    assert not any(flags)


def test_the_default_password_actually_verifies(conn):
    from app.auth.passwords import verify_password

    seed_team(conn)
    for row in conn.execute("SELECT password_hash FROM users"):
        assert verify_password(row["password_hash"], DEFAULT_PASSWORD)


def test_running_twice_creates_nothing_new(conn):
    seed_team(conn)
    assert seed_team(conn) == []
    assert conn.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"] == 6


def test_every_account_gets_the_same_known_password(conn):
    created = seed_team(conn)
    assert {password for _, password in created} == {DEFAULT_PASSWORD}
