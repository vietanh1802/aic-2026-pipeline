# -*- coding: utf-8 -*-
"""Chỗ làm việc của mỗi người trên một câu, để người khác mở lại được."""
import pytest
from fastapi import HTTPException

from app.db.connection import utcnow_iso
from app.routers.answers import clear_answers, delete_answer
from app.routers.search_state import (
    MAX_PICKS,
    SearchStateRequest,
    clear_search_history,
    list_search_history,
    list_search_states,
    save_search_state,
)


def _user(conn, username="an", role="member"):
    cursor = conn.execute(
        "INSERT INTO users (username, display_name, role, password_hash, "
        "must_change_password, disabled, created_at) "
        "VALUES (?, ?, ?, 'x', 0, 0, ?)",
        (username, username.upper(), role, utcnow_iso()),
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


# --- Dọn lịch sử tìm -------------------------------------------------------


def _history(conn, task, user, *queries):
    for query in queries:
        save_search_state(task, _state(query_text=query), user, conn)


def test_clearing_my_history_leaves_everyone_elses_alone(conn):
    """Luật author_id của repo, áp cho bảng lịch sử.

    Đường tìm của người khác là dữ liệu của họ; một người bấm dọn bàn mình
    không được kéo theo đường đi mà cả nhóm còn đang dựa vào.
    """
    an = _user(conn, "an")
    vanh = _user(conn, "vanh")
    task = _task(conn, an["id"])
    _history(conn, task, an, "của An một", "của An hai")
    _history(conn, task, vanh, "của Vanh")

    assert clear_search_history(task, an, conn, scope="mine") == {"removed": 2}

    left = list_search_history(task, an, conn)["entries"]
    assert [entry["query_text"] for entry in left] == ["của Vanh"]


def test_a_member_cannot_clear_the_whole_task(conn):
    an = _user(conn, "an")
    vanh = _user(conn, "vanh")
    task = _task(conn, an["id"])
    _history(conn, task, vanh, "của Vanh")

    with pytest.raises(HTTPException) as raised:
        clear_search_history(task, an, conn, scope="all")
    assert raised.value.status_code == 403
    assert len(list_search_history(task, an, conn)["entries"]) == 1


def test_admin_clearing_all_wipes_the_task_for_everyone(conn):
    admin = _user(conn, "admin", role="admin")
    vanh = _user(conn, "vanh")
    task = _task(conn, admin["id"])
    _history(conn, task, admin, "của Admin")
    _history(conn, task, vanh, "của Vanh")

    assert clear_search_history(task, admin, conn, scope="all") == {"removed": 2}
    assert list_search_history(task, admin, conn)["entries"] == []


def test_clearing_one_task_keeps_the_other_task_history(conn):
    """Nút nằm trong màn của MỘT câu, nên nó chỉ được dọn đúng câu đó."""
    an = _user(conn, "an")
    first = _task(conn, an["id"], code="07")
    second = _task(conn, an["id"], code="12")
    _history(conn, first, an, "câu bảy")
    _history(conn, second, an, "câu mười hai")

    clear_search_history(first, an, conn, scope="mine")

    assert list_search_history(first, an, conn)["entries"] == []
    assert len(list_search_history(second, an, conn)["entries"]) == 1


def test_clearing_does_not_touch_the_live_search_state(conn):
    """Lịch sử và "đang tìm gì" là hai bảng, và chỉ một cái bị dọn.

    Xoá cả hai thì bảng "cả nhóm đang tìm câu này" trống trơn trong khi mọi
    người vẫn đang gõ — nhìn như cả nhóm vừa bỏ câu.
    """
    an = _user(conn, "an")
    task = _task(conn, an["id"])
    _history(conn, task, an, "vẫn đang tìm")

    clear_search_history(task, an, conn, scope="mine")

    states = list_search_states(task, an, conn)["states"]
    assert len(states) == 1
    assert states[0]["query_text"] == "vẫn đang tìm"


def test_an_unknown_scope_is_refused_rather_than_treated_as_mine(conn):
    """Gõ sai `scope` không được âm thầm xoá thứ khác với thứ người ta định."""
    an = _user(conn, "an")
    task = _task(conn, an["id"])
    _history(conn, task, an, "giữ nguyên")

    with pytest.raises(HTTPException) as raised:
        clear_search_history(task, an, conn, scope="everything")
    assert raised.value.status_code == 400
    assert len(list_search_history(task, an, conn)["entries"]) == 1


def test_clearing_a_task_that_does_not_exist_is_refused(conn):
    an = _user(conn, "an")
    with pytest.raises(HTTPException) as raised:
        clear_search_history(999999, an, conn, scope="mine")
    assert raised.value.status_code == 404

# --- Nhiều khung trên MỘT truy vấn -----------------------------------------


def _pick(query, video, frame, name=None):
    return _state(
        query_text=query,
        picked_frame=name,
        picked_video=video,
        picked_frame_idx=frame,
    )


def test_three_frames_picked_on_one_query_all_survive(conn):
    """Lỗi được báo: gõ một câu rồi bấm ba thẻ, bảng chỉ còn thẻ thứ ba.

    Ba cột picked_* là số ít nên mỗi lần chốt ghi đè lần trước. Hai khung đầu
    biến mất khỏi lịch sử dù cả ba đã nằm trong giỏ.
    """
    an = _user(conn, "an")
    task = _task(conn, an["id"])

    save_search_state(task, _pick("nhóm 5 người", "L24_V035", 448), an, conn)
    save_search_state(task, _pick("nhóm 5 người", "L24_V035", 2236), an, conn)
    save_search_state(task, _pick("nhóm 5 người", "L24_V035", 9112), an, conn)

    entries = list_search_history(task, an, conn)["entries"]
    assert len(entries) == 1
    assert [p["frame"] for p in entries[0]["picks"]] == [448, 2236, 9112]


def test_the_order_of_picks_is_the_order_they_were_clicked(conn):
    """Thứ tự bấm là thứ tự người dùng tự xếp hạng, nên nối vào CUỐI."""
    an = _user(conn, "an")
    task = _task(conn, an["id"])

    for frame in (9112, 448, 2236):
        save_search_state(task, _pick("một câu", "L24_V035", frame), an, conn)

    picks = list_search_history(task, an, conn)["entries"][0]["picks"]
    assert [p["frame"] for p in picks] == [9112, 448, 2236]


def test_clicking_the_same_frame_twice_does_not_repeat_it(conn):
    an = _user(conn, "an")
    task = _task(conn, an["id"])

    save_search_state(task, _pick("một câu", "L24_V035", 448), an, conn)
    save_search_state(task, _pick("một câu", "L24_V035", 448), an, conn)

    picks = list_search_history(task, an, conn)["entries"][0]["picks"]
    assert [p["frame"] for p in picks] == [448]


def test_the_same_frame_number_in_another_video_is_its_own_pick(conn):
    """Khoá theo cặp (video, frame), không riêng frame."""
    an = _user(conn, "an")
    task = _task(conn, an["id"])

    save_search_state(task, _pick("một câu", "L24_V035", 448), an, conn)
    save_search_state(task, _pick("một câu", "L21_V002", 448), an, conn)

    picks = list_search_history(task, an, conn)["entries"][0]["picks"]
    assert [(p["video"], p["frame"]) for p in picks] == [
        ("L24_V035", 448),
        ("L21_V002", 448),
    ]


def test_a_new_query_starts_its_own_list_of_picks(conn):
    """Đổi truy vấn là một mục mới; khung của câu cũ ở lại câu cũ."""
    an = _user(conn, "an")
    task = _task(conn, an["id"])

    save_search_state(task, _pick("câu một", "L24_V035", 448), an, conn)
    save_search_state(task, _pick("câu hai", "L24_V035", 9112), an, conn)

    entries = list_search_history(task, an, conn)["entries"]
    by_query = {e["query_text"]: [p["frame"] for p in e["picks"]] for e in entries}
    assert by_query == {"câu một": [448], "câu hai": [9112]}


def test_a_write_with_no_pick_does_not_wipe_the_ones_already_there(conn):
    """Đổi tham số rồi bấm Search lại cũng đi qua đây với picked_* rỗng.

    Để lượt đó xoá ba khung vừa chọn thì đúng bằng lỗi cũ, chỉ khác đường tới.
    """
    an = _user(conn, "an")
    task = _task(conn, an["id"])

    save_search_state(task, _pick("một câu", "L24_V035", 448), an, conn)
    save_search_state(task, _pick("một câu", "L24_V035", 2236), an, conn)
    save_search_state(
        task,
        _state(
            query_text="một câu",
            picked_frame=None,
            picked_video=None,
            picked_frame_idx=None,
        ),
        an,
        conn,
    )

    picks = list_search_history(task, an, conn)["entries"][0]["picks"]
    assert [p["frame"] for p in picks] == [448, 2236]


def test_the_newest_pick_still_reaches_the_single_columns(conn):
    """Ba cột cũ vẫn mang khung mới nhất.

    search_states dùng chung hình dạng đó, và bỏ nó đi sẽ làm bảng "cả nhóm
    đang tìm gì" mất chỗ chỉ khung.
    """
    an = _user(conn, "an")
    task = _task(conn, an["id"])

    save_search_state(task, _pick("một câu", "L24_V035", 448), an, conn)
    save_search_state(task, _pick("một câu", "L24_V035", 9112), an, conn)

    entry = list_search_history(task, an, conn)["entries"][0]
    assert entry["picked_frame_idx"] == 9112
    assert list_search_states(task, an, conn)["states"][0]["picked_frame_idx"] == 9112


def test_a_row_written_before_the_picks_column_still_shows_its_frame(conn):
    """Dòng cũ có `picks` rỗng nhưng vẫn mang một khung ở picked_*.

    Dựng lại thành danh sách một phần tử để giao diện chỉ phải biết một hình
    dạng — nếu không, mọi lịch sử có từ trước bản này mất sạch nút mở video.
    """
    an = _user(conn, "an")
    task = _task(conn, an["id"])
    save_search_state(task, _pick("một câu", "L24_V035", 448), an, conn)
    # Giả lập dòng ghi trước bước 6.
    conn.execute("UPDATE search_history SET picks = '[]'")

    picks = list_search_history(task, an, conn)["entries"][0]["picks"]
    assert [(p["video"], p["frame"]) for p in picks] == [("L24_V035", 448)]


def test_the_pick_list_stops_growing_at_the_cap(conn):
    """Trần bằng số dòng tối đa của một câu.

    Không chặn thì một phiên dài biến cột JSON này thành vài chục KB, đọc lại
    mỗi 5 giây theo nhịp poll của bảng lịch sử.
    """
    an = _user(conn, "an")
    task = _task(conn, an["id"])

    for frame in range(MAX_PICKS + 10):
        save_search_state(task, _pick("một câu", "L24_V035", frame), an, conn)

    picks = list_search_history(task, an, conn)["entries"][0]["picks"]
    assert len(picks) == MAX_PICKS
    # Giữ những khung ĐẦU: thứ tự bấm là thứ hạng, nên phần đầu đáng giá hơn.
    assert picks[0]["frame"] == 0


def test_a_corrupt_pick_list_does_not_lose_the_click_being_made(conn):
    an = _user(conn, "an")
    task = _task(conn, an["id"])
    save_search_state(task, _pick("một câu", "L24_V035", 448), an, conn)
    conn.execute("UPDATE search_history SET picks = 'không phải JSON'")

    save_search_state(task, _pick("một câu", "L24_V035", 2236), an, conn)

    picks = list_search_history(task, an, conn)["entries"][0]["picks"]
    assert [p["frame"] for p in picks] == [2236]

# --- Giỏ cạn thì khép lượt -------------------------------------------------


def _answer(conn, task, user, frame):
    conn.execute(
        "INSERT INTO answers (task_id, author_id, sort_key, video_id, frames, "
        "answer_text, origin, created_by, updated_by, updated_at, version) "
        "VALUES (?, ?, ?, 'L24_V035', ?, NULL, 'manual', ?, NULL, ?, 1)",
        (task, user["id"], float(frame), f"[{frame}]", user["id"], utcnow_iso()),
    )


def _pick_and_pin(conn, task, user, frame):
    """Chốt một khung: vừa ghi lịch sử vừa thêm một dòng vào giỏ."""
    save_search_state(task, _pick("cùng một câu", "L24_V035", frame), user, conn)
    _answer(conn, task, user, frame)


def test_clearing_the_basket_starts_a_new_attempt_on_the_same_query(conn):
    """Đúng kịch bản chủ repo mô tả.

    Chốt ba khung, thấy sai cả ba, xoá sạch giỏ rồi chốt hai khung khác. Hai
    lượt đó tách bạch dù truy vấn y hệt — gộp lại thì đọc không ra được rằng
    ba khung đầu đã bị chính người đó loại.
    """
    an = _user(conn, "an")
    task = _task(conn, an["id"])

    for frame in (448, 2236, 9112):
        _pick_and_pin(conn, task, an, frame)
    clear_answers(task, an, conn)
    for frame in (500, 600):
        _pick_and_pin(conn, task, an, frame)

    entries = list_search_history(task, an, conn)["entries"]
    assert [[p["frame"] for p in e["picks"]] for e in entries] == [
        [500, 600],
        [448, 2236, 9112],
    ]


def test_deleting_one_of_three_is_a_correction_not_a_restart(conn):
    """Giỏ còn hai dòng thì lượt chưa khép.

    Tách dòng ở mỗi lần xoá chỉ làm bảng vụn ra: bỏ một khung chọn nhầm rồi
    chốt khung thay thế vẫn là cùng một lượt tìm.
    """
    an = _user(conn, "an")
    task = _task(conn, an["id"])
    for frame in (448, 2236, 9112):
        _pick_and_pin(conn, task, an, frame)

    row = conn.execute(
        "SELECT id FROM answers WHERE frames = '[2236]'"
    ).fetchone()
    delete_answer(row["id"], an, conn)
    _pick_and_pin(conn, task, an, 500)

    entries = list_search_history(task, an, conn)["entries"]
    assert len(entries) == 1
    assert [p["frame"] for p in entries[0]["picks"]] == [448, 2236, 9112, 500]


def test_deleting_the_rows_one_by_one_still_closes_the_attempt(conn):
    """Bấm x cho tới dòng cuối cũng là dọn sạch giỏ.

    Chỉ nghe nút "Xoá sạch" thì cùng một hành động, làm theo cách khác, lại ra
    kết quả khác — mà người dùng không có cách nào đoán được điều đó.
    """
    an = _user(conn, "an")
    task = _task(conn, an["id"])
    for frame in (448, 2236):
        _pick_and_pin(conn, task, an, frame)

    for row in conn.execute("SELECT id FROM answers").fetchall():
        delete_answer(row["id"], an, conn)
    _pick_and_pin(conn, task, an, 500)

    entries = list_search_history(task, an, conn)["entries"]
    assert [[p["frame"] for p in e["picks"]] for e in entries] == [[500], [448, 2236]]


def test_one_persons_clearing_does_not_close_another_persons_attempt(conn):
    """Khoá theo author_id, cùng luật với mọi đường ghi khác trong repo."""
    an = _user(conn, "an")
    vanh = _user(conn, "vanh")
    task = _task(conn, an["id"])
    _pick_and_pin(conn, task, an, 448)
    _pick_and_pin(conn, task, vanh, 900)

    clear_answers(task, an, conn)
    _pick_and_pin(conn, task, vanh, 901)

    of_vanh = [
        e for e in list_search_history(task, vanh, conn)["entries"]
        if e["user"]["id"] == vanh["id"]
    ]
    assert len(of_vanh) == 1
    assert [p["frame"] for p in of_vanh[0]["picks"]] == [900, 901]


def test_clearing_an_empty_basket_does_not_leave_a_blank_entry(conn):
    """Chỉ khép mục CÓ khung.

    Khép một mục chưa chốt gì thì không giữ lại được gì, mà lại đẻ thêm một
    dòng rỗng nữa ngay sau đó.
    """
    an = _user(conn, "an")
    task = _task(conn, an["id"])
    save_search_state(
        task,
        _state(query_text="chưa chốt gì", picked_frame=None,
               picked_video=None, picked_frame_idx=None),
        an,
        conn,
    )

    clear_answers(task, an, conn)
    _pick_and_pin(conn, task, an, 448)

    entries = list_search_history(task, an, conn)["entries"]
    assert len(entries) == 2  # "chưa chốt gì" và "cùng một câu" — khác truy vấn
    assert [p["frame"] for p in entries[0]["picks"]] == [448]


def test_a_closed_attempt_is_never_appended_to_again(conn):
    """Kể cả khi truy vấn, kiểu tìm và tham số trùng khớp hoàn toàn."""
    an = _user(conn, "an")
    task = _task(conn, an["id"])
    _pick_and_pin(conn, task, an, 448)
    clear_answers(task, an, conn)
    _pick_and_pin(conn, task, an, 500)
    _pick_and_pin(conn, task, an, 600)

    entries = list_search_history(task, an, conn)["entries"]
    assert [[p["frame"] for p in e["picks"]] for e in entries] == [[500, 600], [448]]

# --- Bộ N mốc của một dòng TRAKE -------------------------------------------


def _trake_pick(query, video, frames):
    return _state(
        query_text=query,
        picked_frame=None,
        picked_video=video,
        picked_frame_idx=frames[0],
        picked_frames=frames,
    )


def test_committing_a_trake_row_records_all_four_events(conn):
    """Lỗi được báo: bấm "Chọn" xong, lịch sử có truy vấn mà không có khung nào.

    Dòng TRAKE mang cả bốn mốc, còn ba cột picked_* là số ít — nên phải gửi cả
    bộ, và bảng lịch sử phải bày ra bốn nút chứ không phải một.
    """
    an = _user(conn, "an")
    task = _task(conn, an["id"])

    save_search_state(
        task,
        _trake_pick("bốn loại trái cây", "L27_V011", [3811, 3880, 4019, 4100]),
        an,
        conn,
    )

    entry = list_search_history(task, an, conn)["entries"][0]
    assert [p["frame"] for p in entry["picks"]] == [3811, 3880, 4019, 4100]
    assert {p["video"] for p in entry["picks"]} == {"L27_V011"}


def test_the_event_order_is_kept_exactly_as_sent(conn):
    """Thứ tự mốc LÀ thứ tự sự kiện E1..E4, không phải thứ tự tăng dần.

    Sắp lại ở đây thì nút thứ hai không còn là E2, mà bảng thì không có gì nói
    ra điều đó.
    """
    an = _user(conn, "an")
    task = _task(conn, an["id"])
    save_search_state(
        task, _trake_pick("câu", "L27_V011", [900, 100, 500, 300]), an, conn
    )

    picks = list_search_history(task, an, conn)["entries"][0]["picks"]
    assert [p["frame"] for p in picks] == [900, 100, 500, 300]


def test_a_batch_does_not_write_its_first_frame_twice(conn):
    """`picked_frame_idx` là mốc ĐẦU của cùng bộ đó, không phải một khung nữa.

    Nhận cả hai thì E1 vào danh sách hai lần.
    """
    an = _user(conn, "an")
    task = _task(conn, an["id"])
    save_search_state(
        task, _trake_pick("câu", "L27_V011", [3811, 3880]), an, conn
    )

    picks = list_search_history(task, an, conn)["entries"][0]["picks"]
    assert [p["frame"] for p in picks] == [3811, 3880]


def test_the_single_columns_still_carry_the_first_event(conn):
    """Bảng "cả nhóm đang tìm gì" chỉ có chỗ cho MỘT khung."""
    an = _user(conn, "an")
    task = _task(conn, an["id"])
    save_search_state(
        task, _trake_pick("câu", "L27_V011", [3811, 3880, 4019]), an, conn
    )

    assert list_search_states(task, an, conn)["states"][0]["picked_frame_idx"] == 3811


def test_a_second_trake_row_on_the_same_query_appends_its_events(conn):
    """Chốt thêm một hàng nữa cho cùng truy vấn: nối tiếp, không ghi đè."""
    an = _user(conn, "an")
    task = _task(conn, an["id"])
    save_search_state(task, _trake_pick("câu", "L27_V011", [10, 20]), an, conn)
    save_search_state(task, _trake_pick("câu", "L27_V011", [30, 40]), an, conn)

    picks = list_search_history(task, an, conn)["entries"][0]["picks"]
    assert [p["frame"] for p in picks] == [10, 20, 30, 40]


def test_a_repeated_event_frame_is_not_added_twice(conn):
    """Hai hàng TRAKE dùng chung một mốc thì mốc đó chỉ hiện một lần."""
    an = _user(conn, "an")
    task = _task(conn, an["id"])
    save_search_state(task, _trake_pick("câu", "L27_V011", [10, 20]), an, conn)
    save_search_state(task, _trake_pick("câu", "L27_V011", [20, 30]), an, conn)

    picks = list_search_history(task, an, conn)["entries"][0]["picks"]
    assert [p["frame"] for p in picks] == [10, 20, 30]


def test_a_batch_without_a_video_records_nothing(conn):
    """Không có video thì không dựng lại được nút mở, nên đó không phải lần chốt."""
    an = _user(conn, "an")
    task = _task(conn, an["id"])
    save_search_state(
        task,
        _state(
            query_text="câu",
            picked_frame=None,
            picked_video=None,
            picked_frame_idx=None,
            picked_frames=[10, 20],
        ),
        an,
        conn,
    )

    assert list_search_history(task, an, conn)["entries"][0]["picks"] == []


def test_a_batch_longer_than_the_cap_is_cut_not_refused(conn):
    an = _user(conn, "an")
    task = _task(conn, an["id"])
    save_search_state(
        task,
        _trake_pick("câu", "L27_V011", list(range(MAX_PICKS + 20))),
        an,
        conn,
    )

    picks = list_search_history(task, an, conn)["entries"][0]["picks"]
    assert len(picks) == MAX_PICKS
    assert picks[0]["frame"] == 0


def test_leaving_picked_frames_out_keeps_the_old_single_frame_path(conn):
    """Mọi lời gọi hiện có không đổi hành vi."""
    an = _user(conn, "an")
    task = _task(conn, an["id"])
    save_search_state(task, _pick("câu", "L24_V035", 448), an, conn)

    picks = list_search_history(task, an, conn)["entries"][0]["picks"]
    assert [p["frame"] for p in picks] == [448]
