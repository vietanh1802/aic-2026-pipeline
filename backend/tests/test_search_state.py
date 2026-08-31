# -*- coding: utf-8 -*-
"""Chỗ làm việc của mỗi người trên một câu, để người khác mở lại được."""
import pytest
from fastapi import HTTPException

from app.db.connection import utcnow_iso
from app.routers.search_state import (
    SearchStateRequest,
    list_search_states,
    save_search_state,
)


def _user(conn, username="an"):
    cursor = conn.execute(
        "INSERT INTO users (username, display_name, role, password_hash, "
        "must_change_password, disabled, created_at) "
        "VALUES (?, ?, 'member', 'x', 0, 0, ?)",
        (username, username.upper(), utcnow_iso()),
    )
    return conn.execute("SELECT * FROM users WHERE id = ?", (cursor.lastrowid,)).fetchone()


def _task(conn, user_id, code="07"):
    conn.execute(
        "INSERT OR IGNORE INTO packs (id, round_label, source_filename, "
        "filename_pattern, imported_by, imported_at, active) "
        "VALUES (1, 'R1', 'p.zip', 'x', ?, ?, 1)",
        (user_id, utcnow_iso()),
    )
    cursor = conn.execute(
        "INSERT INTO tasks (pack_id, code, type, query_text) VALUES (1, ?, 'kis', 'q')",
        (code,),
    )
    return cursor.lastrowid


def _state(**overrides):
    base = {
        "query_text": "một nhóm người tập thể dục",
        "search_type": "ensemble",
        "params": {"topM": 50, "useRerank": True, "resultLimit": "100"},
        "picked_frame": "L21_V002-0028-3175.jpg",
        "picked_video": "L21_V002",
        "picked_frame_idx": 3175,
    }
    base.update(overrides)
    return SearchStateRequest(**base)


def test_a_teammate_sees_the_query_and_the_frame_that_was_picked(conn):
    """Cả tính năng gói trong một phép thử: B đọc được đúng thứ A đã làm."""
    an = _user(conn, "an")
    vanh = _user(conn, "vanh")
    task = _task(conn, an["id"])

    save_search_state(task, _state(), an, conn)
    states = list_search_states(task, vanh, conn)["states"]

    assert len(states) == 1
    only = states[0]
    assert only["user"]["display_name"] == "AN"
    assert only["query_text"] == "một nhóm người tập thể dục"
    # Tham số phải về NGUYÊN VẸN, không phải chuỗi JSON: thiếu một cái là chạy
    # lại ra danh sách khác với danh sách A đang nhìn.
    assert only["params"] == {"topM": 50, "useRerank": True, "resultLimit": "100"}
    assert only["picked_frame"] == "L21_V002-0028-3175.jpg"
    assert (only["picked_video"], only["picked_frame_idx"]) == ("L21_V002", 3175)


def test_searching_again_replaces_the_row_and_drops_the_old_frame(conn):
    """Khung đã chọn thuộc về bộ kết quả CŨ.

    Giữ nó lại sau khi đổi truy vấn thì vòng khoanh đỏ sẽ trỏ vào một thẻ không
    còn trong danh sách — hoặc tệ hơn, trỏ nhầm sang thẻ khác trùng vị trí.
    """
    an = _user(conn, "an")
    task = _task(conn, an["id"])

    save_search_state(task, _state(), an, conn)
    save_search_state(
        task,
        _state(
            query_text="cảnh khác hẳn",
            search_type="ocr",
            picked_frame=None,
            picked_video=None,
            picked_frame_idx=None,
        ),
        an,
        conn,
    )

    states = list_search_states(task, an, conn)["states"]
    assert len(states) == 1
    assert states[0]["query_text"] == "cảnh khác hẳn"
    assert states[0]["search_type"] == "ocr"
    assert states[0]["picked_frame"] is None


def test_one_person_working_two_tasks_keeps_both(conn):
    """Khoá theo (user, task), không riêng user.

    Chuyển sang câu 12 không được xoá mất đường tìm của câu 7 — người khác vẫn
    cần mở lại được câu 7 sau đó.
    """
    an = _user(conn, "an")
    first = _task(conn, an["id"], code="07")
    second = _task(conn, an["id"], code="12")

    save_search_state(first, _state(query_text="câu bảy"), an, conn)
    save_search_state(second, _state(query_text="câu mười hai"), an, conn)

    assert list_search_states(first, an, conn)["states"][0]["query_text"] == "câu bảy"
    assert (
        list_search_states(second, an, conn)["states"][0]["query_text"]
        == "câu mười hai"
    )


def test_the_row_belongs_to_whoever_sent_it(conn):
    """user_id lấy từ token, không từ body.

    Cả tính năng dựa trên việc tin rằng dòng mang tên ai là do người đó gõ. Nếu
    giả được thì "Coi An làm" có thể mở ra thứ An chưa từng gõ.
    """
    an = _user(conn, "an")
    vanh = _user(conn, "vanh")
    task = _task(conn, an["id"])

    save_search_state(task, _state(query_text="của An"), an, conn)
    save_search_state(task, _state(query_text="của Vanh"), vanh, conn)

    by_user = {
        s["user"]["id"]: s["query_text"] for s in list_search_states(task, an, conn)["states"]
    }
    assert by_user == {an["id"]: "của An", vanh["id"]: "của Vanh"}


def test_a_task_that_does_not_exist_is_refused(conn):
    an = _user(conn, "an")
    with pytest.raises(HTTPException) as raised:
        save_search_state(999999, _state(), an, conn)
    assert raised.value.status_code == 404


def test_params_too_large_fall_back_to_empty_rather_than_being_stored(conn):
    """Một request không được nhét cả megabyte vào CSDL.

    Bỏ tham số chứ không từ chối cả lần ghi: truy vấn vẫn là phần đáng giữ, và
    tham số mặc định vẫn chạy ra một danh sách hợp lý.
    """
    an = _user(conn, "an")
    task = _task(conn, an["id"])

    save_search_state(
        task, _state(params={"rác": "x" * 5000}), an, conn
    )

    assert list_search_states(task, an, conn)["states"][0]["params"] == {}
