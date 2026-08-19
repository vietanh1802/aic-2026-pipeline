import sqlite3

import pytest

from app.db.connection import get_conn
from app.db.migrate import migrate


@pytest.fixture()
def conn(tmp_path, monkeypatch) -> sqlite3.Connection:
    monkeypatch.setenv("AIC_DB_PATH", str(tmp_path / "test.db"))
    connection = get_conn()
    migrate(connection)
    yield connection
    connection.close()
