# -*- coding: utf-8 -*-
"""Số mốc của câu TRAKE là việc của người nhập, và phải điền.

Trình đọc gói thôi đoán cấu trúc đề bài (xem test_pack_parser.py), nên
`n_events` không còn tự có. Nếu nó vào cơ sở dữ liệu ở dạng NULL thì
`export.py` chạy `int(task["n_events"] or 1)` và câu TRAKE bốn mốc xuất ra
đúng MỘT cột frame như câu KIS — bài nộp trông vẫn hợp lệ, chỉ là sai. Đó là
lý do commit từ chối thẳng thay vì nhận.
"""
import sqlite3

import pytest
from fastapi import HTTPException

from app.db.connection import utcnow_iso
from app.packs.parser import ParsedTask
from app.routers.packs import _PREVIEWS, CommitRequest, TaskEdit, commit_pack


def _admin(conn: sqlite3.Connection) -> sqlite3.Row:
    conn.execute(
        "INSERT INTO users (username, display_name, role, password_hash, "
        "must_change_password, disabled, created_at) "
        "VALUES ('admin', 'Admin', 'admin', 'x', 0, 0, ?)",
        (utcnow_iso(),),
    )
    return conn.execute("SELECT * FROM users WHERE username = 'admin'").fetchone()


def _preview(*tasks: ParsedTask) -> str:
    token = "test-token"
    _PREVIEWS[token] = list(tasks)
    return token


def _parsed(code: str, kind: str, body: str) -> ParsedTask:
    return ParsedTask(
        filename=f"query-p2-{code}-{kind}.txt",
        matched=True,
        phase="p2",
        code=code,
        type=kind,
        query_text=body,
        lines=len(body.splitlines()),
    )


# Đúng hình dạng query-p2-8-trake.txt: dòng dẫn nhập rồi bốn mốc, tất cả nằm
# trong một chuỗi vì trình đọc không tách nữa.
TRAKE_BODY = (
    "Video về một khu vườn cây ăn trái ở miền Tây Nam Bộ.\n"
    "E1: Cảnh đầu tiên có trái sầu riêng.\n"
    "E2: Cảnh đầu tiên có trái măng cụt.\n"
    "E3: Cảnh đầu tiên có trái bưởi.\n"
    "E4: Cảnh đầu tiên có trái dâu bòn bon."
)


def test_a_trake_task_without_a_count_is_refused(conn):
    user = _admin(conn)
    token = _preview(_parsed("8", "trake", TRAKE_BODY))

    with pytest.raises(HTTPException) as caught:
        commit_pack(
            CommitRequest(preview_token=token, round_label="Vòng 2"),
            user,
            conn,
        )

    assert caught.value.status_code == 400
    assert "query-p2-8-trake.txt" in caught.value.detail
    # Không có task nào lọt vào cơ sở dữ liệu.
    assert conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0] == 0


def test_the_count_the_admin_typed_is_what_gets_stored(conn):
    user = _admin(conn)
    token = _preview(_parsed("8", "trake", TRAKE_BODY))

    commit_pack(
        CommitRequest(
            preview_token=token,
            round_label="Vòng 2",
            edits=[TaskEdit(filename="query-p2-8-trake.txt", n_events=4)],
        ),
        user,
        conn,
    )

    row = conn.execute(
        "SELECT query_text, n_events, question_text, event_labels FROM tasks"
    ).fetchone()
    assert row["n_events"] == 4
    # Đề bài vào nguyên văn, bốn mốc còn nguyên trong đó.
    assert row["query_text"] == TRAKE_BODY
    assert "dâu bòn bon" in row["query_text"]
    # Hai cột này không còn ai điền.
    assert row["question_text"] is None
    assert row["event_labels"] == "[]"


def test_kis_and_qa_need_no_count(conn):
    user = _admin(conn)
    token = _preview(
        _parsed("1", "kis", "Tìm cảnh người đàn ông mặc áo đỏ."),
        _parsed("7", "qa", "Xã này tên là gì? (tại thời điểm đó)"),
    )

    result = commit_pack(
        CommitRequest(preview_token=token, round_label="Vòng 2"), user, conn
    )

    assert result["tasks_created"] == 2
    # Câu Q&A giữ nguyên cả câu hỏi bên trong đề bài, không tách ra cột riêng.
    qa = conn.execute("SELECT * FROM tasks WHERE type = 'qa'").fetchone()
    assert qa["query_text"] == "Xã này tên là gì? (tại thời điểm đó)"
    assert qa["question_text"] is None


def test_a_zero_is_refused_the_same_as_a_missing_count(conn):
    user = _admin(conn)
    token = _preview(_parsed("21", "trake", "4 cảnh này xảy ra liên tiếp nhau."))

    with pytest.raises(HTTPException) as caught:
        commit_pack(
            CommitRequest(
                preview_token=token,
                round_label="Vòng 2",
                edits=[TaskEdit(filename="query-p2-21-trake.txt", n_events=0)],
            ),
            user,
            conn,
        )

    assert caught.value.status_code == 400
    assert conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0] == 0
