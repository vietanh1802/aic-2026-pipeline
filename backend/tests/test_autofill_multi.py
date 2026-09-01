# -*- coding: utf-8 -*-
"""Rải quanh NHIỀU mốc: thứ tự, chiều, và bước riêng từng mốc."""
import json

import pytest
from fastapi import HTTPException

from app.answers import autofill
from app.db.connection import utcnow_iso


def _take(anchor_count, steps, direction, n):
    """direction: một chuỗi cho mọi mốc, hoặc một danh sách theo từng mốc."""
    dirs = [direction] if isinstance(direction, str) else direction
    out = []
    for pair in autofill.plan(anchor_count, steps, dirs, n * 4):
        out.append(pair)
        if len(out) >= n:
            break
    return out


def test_three_anchors_go_round_robin_before_the_step_doubles():
    """Đúng thứ tự người dùng mô tả.

    Ba mốc là ba phỏng đoán NGANG NHAU. Rải hết mốc 1 rồi mới tới mốc 2 sẽ dồn
    toàn bộ hạng cao cho một phỏng đoán và đẩy hai cái kia xuống đáy — mà R@k
    chỉ nhìn k dòng đầu.
    """
    assert _take(3, [25], autofill.BOTH, 9) == [
        (0, 25), (1, 25), (2, 25),        # hạng 4, 5, 6 — cả ba mốc, cộng lên
        (0, -25), (1, -25), (2, -25),     # hạng 7, 8, 9 — cả ba mốc, trừ xuống
        (0, 50), (1, 50), (2, 50),        # rồi mới tới bội số 2
    ]


def test_one_anchor_still_alternates_sides():
    """Hành vi cũ phải giữ nguyên: một mốc thì xen kẽ hai bên như trước."""
    assert _take(1, [25], autofill.BOTH, 6) == [
        (0, 25), (0, -25), (0, 50), (0, -50), (0, 75), (0, -75),
    ]


def test_up_only_never_goes_below_the_anchor():
    plan = _take(2, [10], autofill.UP, 6)
    assert plan == [(0, 10), (1, 10), (0, 20), (1, 20), (0, 30), (1, 30)]
    assert all(delta > 0 for _, delta in plan)


def test_down_only_never_goes_above_the_anchor():
    plan = _take(2, [10], autofill.DOWN, 4)
    assert plan == [(0, -10), (1, -10), (0, -20), (1, -20)]
    assert all(delta < 0 for _, delta in plan)


def test_each_anchor_can_carry_its_own_step():
    """Video quay chậm trải dài hơn video quay nhanh — ép chung một bước là
    làm hỏng một trong hai."""
    assert _take(3, [10, 50, 2], autofill.UP, 6) == [
        (0, 10), (1, 50), (2, 2),
        (0, 20), (1, 100), (2, 4),
    ]


def test_a_short_step_list_reuses_its_last_entry():
    """Giao diện gửi thiếu một ô thì mốc còn lại vẫn phải rải, không đứng im."""
    assert _take(3, [10, 50], autofill.UP, 3) == [(0, 10), (1, 50), (2, 50)]


def test_spread_keeps_working_for_the_single_anchor_callers():
    assert autofill.spread(1000, 25, 4) == [1025, 975, 1050, 950]
    assert autofill.spread(10, 25, 3) == [35, 60, 85]  # bỏ số âm
    assert autofill.spread(1000, 25, 0) == []
    assert autofill.spread(1000, 0, 5) == []


# ── Qua endpoint ────────────────────────────────────────────────────────────


def _user(conn, username="an"):
    cursor = conn.execute(
        "INSERT INTO users (username, display_name, role, password_hash, "
        "must_change_password, disabled, created_at) "
        "VALUES (?, ?, 'member', 'x', 0, 0, ?)",
        (username, username.upper(), utcnow_iso()),
    )
    return conn.execute(
        "SELECT * FROM users WHERE id = ?", (cursor.lastrowid,)
    ).fetchone()


def _task(conn, user_id, task_type="kis", n_events=None):
    conn.execute(
        "INSERT OR IGNORE INTO packs (id, round_label, source_filename, "
        "filename_pattern, imported_by, imported_at, active) "
        "VALUES (1, 'R1', 'p.zip', 'x', ?, ?, 1)",
        (user_id, utcnow_iso()),
    )
    cursor = conn.execute(
        "INSERT INTO tasks (pack_id, code, type, query_text, n_events) "
        "VALUES (1, '07', ?, 'q', ?)",
        (task_type, n_events),
    )
    return cursor.lastrowid


def _pin(conn, task_id, user_id, video, frames, sort_key):
    cursor = conn.execute(
        "INSERT INTO answers (task_id, author_id, sort_key, video_id, frames, "
        "answer_text, origin, created_by, updated_by, updated_at, version) "
        "VALUES (?, ?, ?, ?, ?, NULL, 'manual', ?, ?, ?, 1)",
        (task_id, user_id, sort_key, video, json.dumps(frames), user_id,
         user_id, utcnow_iso()),
    )
    return cursor.lastrowid


def _rows(conn, task_id):
    return [
        (r["video_id"], json.loads(r["frames"]), r["origin"])
        for r in conn.execute(
            "SELECT * FROM answers WHERE task_id = ? ORDER BY sort_key, id",
            (task_id,),
        )
    ]


def test_autofill_spreads_around_every_pinned_row_not_just_the_first(conn):
    """Đây là lỗi được báo: thấy ba khung cùng đúng, chỉ khung đầu được rải."""
    from app.routers.answers import AutofillRequest, autofill_answers

    user = _user(conn)
    task = _task(conn, user["id"])
    _pin(conn, task, user["id"], "L21_V001", [1000], 1.0)
    _pin(conn, task, user["id"], "L21_V002", [5000], 2.0)
    _pin(conn, task, user["id"], "L22_V009", [9000], 3.0)

    autofill_answers(
        task, AutofillRequest(limit=9, step=25, mode="append"), user, conn
    )

    got = _rows(conn, task)
    assert [(v, f) for v, f, _ in got] == [
        ("L21_V001", [1000]), ("L21_V002", [5000]), ("L22_V009", [9000]),
        ("L21_V001", [1025]), ("L21_V002", [5025]), ("L22_V009", [9025]),
        ("L21_V001", [975]), ("L21_V002", [4975]), ("L22_V009", [8975]),
    ]
    # Mỗi dòng sinh ra phải mang video CỦA CHÍNH MỐC NÓ. Dùng chung video của
    # mốc đầu là nộp một khung không tồn tại — sai video thì mất trắng điểm.
    assert got[4][0] == "L21_V002"


def test_direction_up_only(conn):
    from app.routers.answers import AutofillRequest, autofill_answers

    user = _user(conn)
    task = _task(conn, user["id"])
    _pin(conn, task, user["id"], "L21_V001", [1000], 1.0)

    autofill_answers(
        task,
        AutofillRequest(limit=4, step=10, mode="append", direction="up"),
        user,
        conn,
    )
    assert [f[0] for _, f, _ in _rows(conn, task)] == [1000, 1010, 1020, 1030]


def test_direction_down_only(conn):
    from app.routers.answers import AutofillRequest, autofill_answers

    user = _user(conn)
    task = _task(conn, user["id"])
    _pin(conn, task, user["id"], "L21_V001", [1000], 1.0)

    autofill_answers(
        task,
        AutofillRequest(limit=4, step=10, mode="append", direction="down"),
        user,
        conn,
    )
    assert [f[0] for _, f, _ in _rows(conn, task)] == [1000, 990, 980, 970]


def test_per_anchor_steps(conn):
    from app.routers.answers import AutofillRequest, autofill_answers

    user = _user(conn)
    task = _task(conn, user["id"])
    _pin(conn, task, user["id"], "L21_V001", [1000], 1.0)
    _pin(conn, task, user["id"], "L21_V002", [5000], 2.0)

    autofill_answers(
        task,
        AutofillRequest(
            limit=6, step=25, mode="append", direction="up", steps=[10, 200]
        ),
        user,
        conn,
    )
    assert [(v, f[0]) for v, f, _ in _rows(conn, task)] == [
        ("L21_V001", 1000), ("L21_V002", 5000),
        ("L21_V001", 1010), ("L21_V002", 5200),
        ("L21_V001", 1020), ("L21_V002", 5400),
    ]


def test_anchor_ids_narrows_the_set(conn):
    """Ghim bốn khung nhưng chỉ muốn rải quanh hai."""
    from app.routers.answers import AutofillRequest, autofill_answers

    user = _user(conn)
    task = _task(conn, user["id"])
    first = _pin(conn, task, user["id"], "L21_V001", [1000], 1.0)
    _pin(conn, task, user["id"], "L21_V002", [5000], 2.0)
    third = _pin(conn, task, user["id"], "L22_V009", [9000], 3.0)

    autofill_answers(
        task,
        AutofillRequest(
            limit=5, step=10, mode="append", direction="up",
            anchor_ids=[first, third],
        ),
        user,
        conn,
    )
    generated = [(v, f[0]) for v, f, origin in _rows(conn, task) if origin == "auto"]
    assert generated == [("L21_V001", 1010), ("L22_V009", 9010)]
    # L21_V002 vẫn nằm trong giỏ, chỉ là không được dùng làm mốc.
    assert ("L21_V002", [5000], "manual") in _rows(conn, task)


def test_anchor_ids_that_match_nothing_is_refused(conn):
    from app.routers.answers import AutofillRequest, autofill_answers

    user = _user(conn)
    task = _task(conn, user["id"])
    _pin(conn, task, user["id"], "L21_V001", [1000], 1.0)

    with pytest.raises(HTTPException) as raised:
        autofill_answers(
            task,
            AutofillRequest(limit=5, mode="append", anchor_ids=[999999]),
            user,
            conn,
        )
    assert raised.value.status_code == 409


def test_generated_rows_are_never_used_as_anchors(conn):
    """Bấm điền hai lần không được rải quanh chính thứ vừa sinh ra.

    Nếu dòng auto cũng thành mốc thì mỗi lần bấm lại, tâm rải trôi xa dần khỏi
    khung thật người dùng đã ghim.
    """
    from app.routers.answers import AutofillRequest, autofill_answers

    user = _user(conn)
    task = _task(conn, user["id"])
    _pin(conn, task, user["id"], "L21_V001", [1000], 1.0)

    autofill_answers(
        task, AutofillRequest(limit=3, step=10, mode="append"), user, conn
    )
    autofill_answers(
        task, AutofillRequest(limit=6, step=10, mode="append"), user, conn
    )
    frames = [f[0] for _, f, _ in _rows(conn, task)]
    # Tất cả vẫn quanh 1000, không trôi ra 1010 ± 10 rồi 1020 ± 10.
    assert frames == [1000, 1010, 990, 1020, 980, 1030]


def test_trake_shifts_the_whole_tuple_per_anchor(conn):
    from app.routers.answers import AutofillRequest, autofill_answers

    user = _user(conn)
    task = _task(conn, user["id"], task_type="trake", n_events=3)
    _pin(conn, task, user["id"], "L26_V194", [100, 150, 220], 1.0)
    _pin(conn, task, user["id"], "L26_V200", [700, 760, 800], 2.0)

    autofill_answers(
        task,
        AutofillRequest(limit=4, step=2, mode="append", direction="up"),
        user,
        conn,
    )
    assert [(v, f) for v, f, _ in _rows(conn, task)] == [
        ("L26_V194", [100, 150, 220]),
        ("L26_V200", [700, 760, 800]),
        ("L26_V194", [102, 152, 222]),
        ("L26_V200", [702, 762, 802]),
    ]


# ── Chiều RIÊNG cho từng mốc ────────────────────────────────────────────────
#
# Một chiều dùng chung là bắt hai mốc chịu thiệt vì mốc thứ ba: mốc giữa cảnh
# dài cần cả hai phía, mốc ngay đầu cảnh mà rải xuống là ném đi nửa số dòng.


def test_each_anchor_carries_its_own_direction():
    """Mốc 1 hai phía, mốc 2 chỉ lên, mốc 3 chỉ xuống."""
    plan = _take(3, [10], [autofill.BOTH, autofill.UP, autofill.DOWN], 6)
    assert plan == [
        # lượt dấu +: mốc 1 và mốc 2 nhận, mốc 3 không
        (0, 10), (1, 10),
        # lượt dấu −: mốc 1 và mốc 3 nhận, mốc 2 không
        (0, -10), (2, -10),
        # bội số 2, cùng luật
        (0, 20), (1, 20),
    ]


def test_an_anchor_that_declines_a_sign_is_skipped_not_reordered():
    """Mốc bị bỏ qua KHÔNG lấn chỗ của mốc sau.

    Nếu mốc 2 chỉ cộng lên thì ở lượt dấu trừ nó vắng mặt, và vị trí đó thuộc
    về mốc 3 — chứ không phải mốc 2 được kéo lên trước bằng một dấu khác.
    """
    plan = _take(3, [10], [autofill.UP, autofill.UP, autofill.BOTH], 5)
    assert plan == [(0, 10), (1, 10), (2, 10), (2, -10), (0, 20)]


def test_directions_shorter_than_the_anchor_list_reuse_the_last_one():
    plan = _take(3, [10], [autofill.UP, autofill.DOWN], 4)
    # Mốc 3 thừa hưởng "down" của mốc 2.
    assert plan == [(0, 10), (1, -10), (2, -10), (0, 20)]


def test_no_usable_anchor_stops_instead_of_spinning_forever():
    """Không mốc nào dùng được thì phải DỪNG, không quay không tải.

    Đây là lỗi thật đã bắt được lúc viết: bước 0 làm thân vòng lặp bỏ qua mọi
    mốc, `produced` đứng im ở 0, điều kiện dừng mãi mãi đúng và k tăng vô tận.
    Request treo cứng, không báo lỗi, không timeout — bộ test đứng luôn.
    """
    assert _take(2, [0, 0], autofill.BOTH, 5) == []
    assert list(autofill.plan(0, [10], [autofill.BOTH], 5)) == []
    assert list(autofill.plan(2, [], [autofill.BOTH], 5)) == []
    assert list(autofill.plan(2, [10], [], 5)) == []


def test_per_anchor_direction_through_the_endpoint(conn):
    from app.routers.answers import AutofillRequest, autofill_answers

    user = _user(conn)
    task = _task(conn, user["id"])
    _pin(conn, task, user["id"], "L21_V001", [1000], 1.0)
    _pin(conn, task, user["id"], "L21_V002", [5000], 2.0)
    _pin(conn, task, user["id"], "L22_V009", [9000], 3.0)

    autofill_answers(
        task,
        AutofillRequest(
            limit=9, step=10, mode="append",
            directions=["both", "up", "down"],
        ),
        user,
        conn,
    )
    assert [(v, f[0]) for v, f, _ in _rows(conn, task)] == [
        ("L21_V001", 1000), ("L21_V002", 5000), ("L22_V009", 9000),
        ("L21_V001", 1010), ("L21_V002", 5010),
        ("L21_V001", 990), ("L22_V009", 8990),
        ("L21_V001", 1020), ("L21_V002", 5020),
    ]


def test_a_misspelled_direction_falls_back_instead_of_failing(conn):
    """Giá trị tới từ giao diện; một chuỗi sai chính tả không đáng mất cả lượt."""
    from app.routers.answers import AutofillRequest, autofill_answers

    user = _user(conn)
    task = _task(conn, user["id"])
    _pin(conn, task, user["id"], "L21_V001", [1000], 1.0)

    autofill_answers(
        task,
        AutofillRequest(
            limit=3, step=10, mode="append",
            direction="up", directions=["nguoc"],
        ),
        user,
        conn,
    )
    # "nguoc" không hợp lệ nên rơi về `direction` = "up".
    assert [f[0] for _, f, _ in _rows(conn, task)] == [1000, 1010, 1020]
