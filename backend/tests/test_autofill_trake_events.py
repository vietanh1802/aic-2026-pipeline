# -*- coding: utf-8 -*-
"""TRAKE: khoanh khoảng từng sự kiện, mỗi dòng chỉ đổi MỘT mốc.

Ví dụ gốc của người dùng: dòng hạng 1 là [100, 250, 333, 432]; hành động 1 nằm
đâu đó trong 90→120, hành động 2 trong 230→275, hành động 3 trong 322→350,
hành động 4 trong 420→444.
"""
import json

from app.answers import autofill
from app.db.connection import utcnow_iso


# ── even_positions ──────────────────────────────────────────────────────────


def test_even_positions_puts_both_ends_on_the_ends():
    assert autofill.even_positions(90, 120, 4) == [90, 100, 110, 120]
    assert autofill.even_positions(0, 10, 3) == [0, 5, 10]
    assert autofill.even_positions(5, 5, 4) == [5]
    assert autofill.even_positions(90, 120, 1) == [90]
    assert autofill.even_positions(90, 120, 0) == []


# ── event_variants ──────────────────────────────────────────────────────────


def test_variants_cover_the_whole_window_but_lead_with_the_nearest():
    """Hai tiêu chí kéo ngược nhau, và cả hai đều phải đúng.

    Chọn thì phủ đều khoảng; xếp thì gần mốc gốc trước, vì R@k chỉ nhìn k dòng
    đầu.
    """
    got = autofill.event_variants(100, 90, 120, autofill.BOTH, 4)
    # even_positions(90,120,4) = [90,100,110,120]; bỏ mốc gốc 100, còn ba.
    # Mất một dòng vì mốc gốc trùng một vị trí — chấp nhận, vòng quay ở
    # trake_plan sẽ lấy bù từ sự kiện khác.
    assert got == [90, 110, 120]
    # Giữ ĐÚNG hai đầu khoảng người dùng gõ vào. Bản đầu tôi viết sinh dư một
    # vị trí rồi cắt theo khoảng cách, và cái bị cắt luôn là một trong hai mút.
    assert min(got) == 90 and max(got) == 120
    # Gần mốc gốc đứng trước.
    assert [abs(f - 100) for f in got] == sorted(abs(f - 100) for f in got)

    # Xin nhiều hơn thì phủ dày hơn, hai đầu vẫn còn.
    dense = autofill.event_variants(100, 90, 120, autofill.BOTH, 8)
    assert min(dense) == 90 and max(dense) == 120
    assert len(dense) == 8


def test_the_anchor_value_itself_is_never_offered():
    """Đề xuất lại đúng giá trị đang có là một dòng trùng, không phải phương án."""
    assert 100 not in autofill.event_variants(100, 90, 120, autofill.BOTH, 30)


def test_up_only_shrinks_the_window_instead_of_filtering_after():
    """"Chỉ lên" phải phủ đều NỬA TRÊN, không phải lấy nửa số dòng rồi bỏ đi.

    Lọc sau khi chọn sẽ vứt mất một nửa số vị trí và để trống đúng phần người
    dùng vừa khoanh.
    """
    got = autofill.event_variants(100, 90, 120, autofill.UP, 4)
    assert all(frame > 100 for frame in got)
    # Mút trên vẫn là 120 — khoảng thu về [100, 120] rồi mới chia đều, chứ
    # không phải chia đều [90, 120] rồi vứt nửa dưới. Vứt sau sẽ chỉ còn hai
    # giá trị và bỏ trống phần trên người dùng vừa khoanh.
    assert max(got) == 120
    # Ba chứ không bốn: mốc gốc 100 rơi đúng một vị trí và bị loại.
    assert got == [107, 113, 120]


def test_down_only_shrinks_the_window_the_other_way():
    got = autofill.event_variants(100, 90, 120, autofill.DOWN, 4)
    assert all(frame < 100 for frame in got)
    assert min(got) == 90


def test_a_window_with_no_room_on_that_side_yields_nothing():
    # Mốc gốc đã nằm ở mút trên: không còn gì phía trên để rải.
    assert autofill.event_variants(120, 90, 120, autofill.UP, 5) == []


def test_a_zero_width_window_pins_the_event():
    """lo == hi == mốc gốc nghĩa là sự kiện này đứng yên."""
    assert autofill.event_variants(100, 100, 100, autofill.BOTH, 5) == []


def test_variants_never_go_below_zero():
    assert all(f >= 0 for f in autofill.event_variants(3, -50, 10, autofill.BOTH, 20))


# ── trake_plan ──────────────────────────────────────────────────────────────


def test_events_take_turns_before_any_event_gets_its_second_variant():
    """Rải hết E1 rồi mới tới E2 sẽ dồn 25 hạng đầu cho một mốc duy nhất."""
    variants = [[[11, 12], [21, 22], [31, 32], [41, 42]]]
    assert list(autofill.trake_plan(variants, 8)) == [
        (0, 0, 11), (0, 1, 21), (0, 2, 31), (0, 3, 41),
        (0, 0, 12), (0, 1, 22), (0, 2, 32), (0, 3, 42),
    ]


def test_two_anchors_alternate_so_rank3_comes_from_row1_and_rank4_from_row2():
    """Đúng luật người dùng nêu cho trường hợp hai dòng neo."""
    variants = [
        [[11, 12], [21, 22]],   # dòng neo 1
        [[91, 92], [81, 82]],   # dòng neo 2
    ]
    plan = list(autofill.trake_plan(variants, 4))
    assert plan[0][0] == 0, "hạng 3 lấy từ dòng neo 1"
    assert plan[1][0] == 1, "hạng 4 lấy từ dòng neo 2"
    assert plan == [(0, 0, 11), (1, 0, 91), (0, 1, 21), (1, 1, 81)]


def test_an_exhausted_event_is_skipped_and_the_rest_carry_on():
    variants = [[[11], [21, 22, 23]]]
    assert list(autofill.trake_plan(variants, 9)) == [
        (0, 0, 11), (0, 1, 21), (0, 1, 22), (0, 1, 23),
    ]


def test_all_lists_empty_stops_instead_of_spinning():
    assert list(autofill.trake_plan([[[], [], [], []]], 5)) == []
    assert list(autofill.trake_plan([], 5)) == []


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


def _task(conn, user_id, n_events=4):
    conn.execute(
        "INSERT OR IGNORE INTO packs (id, round_label, source_filename, "
        "filename_pattern, imported_by, imported_at, active) "
        "VALUES (1, 'R1', 'p.zip', 'x', ?, ?, 1)",
        (user_id, utcnow_iso()),
    )
    cursor = conn.execute(
        "INSERT INTO tasks (pack_id, code, type, query_text, n_events) "
        "VALUES (1, '08', 'trake', 'q', ?)",
        (n_events,),
    )
    return cursor.lastrowid


def _pin(conn, task_id, user_id, video, frames, sort_key):
    conn.execute(
        "INSERT INTO answers (task_id, author_id, sort_key, video_id, frames, "
        "answer_text, origin, created_by, updated_by, updated_at, version) "
        "VALUES (?, ?, ?, ?, ?, NULL, 'manual', ?, ?, ?, 1)",
        (task_id, user_id, sort_key, video, json.dumps(frames), user_id,
         user_id, utcnow_iso()),
    )


def _rows(conn, task_id):
    return [
        (r["video_id"], json.loads(r["frames"]))
        for r in conn.execute(
            "SELECT * FROM answers WHERE task_id = ? ORDER BY sort_key, id",
            (task_id,),
        )
    ]


def test_the_users_worked_example_end_to_end(conn):
    """[100, 250, 333, 432] + bốn khoảng -> mỗi dòng đổi đúng một mốc."""
    from app.routers.answers import AutofillRequest, EventRange, autofill_answers

    user = _user(conn)
    task = _task(conn, user["id"])
    _pin(conn, task, user["id"], "L26_V194", [100, 250, 333, 432], 1.0)

    autofill_answers(
        task,
        AutofillRequest(
            limit=9,
            mode="append",
            event_ranges=[
                EventRange(lo=90, hi=120),
                EventRange(lo=230, hi=275),
                EventRange(lo=322, hi=350),
                EventRange(lo=420, hi=444),
            ],
        ),
        user,
        conn,
    )

    got = _rows(conn, task)
    base = [100, 250, 333, 432]
    assert got[0] == ("L26_V194", base)

    for video, frames in got[1:]:
        assert video == "L26_V194"
        # ĐÚNG MỘT mốc khác dòng neo. Đây là toàn bộ điểm của cách rải này:
        # TRAKE chấm từng mốc, nên giữ N−1 mốc đúng của hạng 1 đáng giá hơn
        # nhiều so với đoán lại cả bộ.
        differing = [i for i in range(4) if frames[i] != base[i]]
        assert len(differing) == 1, (frames, differing)

    # Bốn sự kiện thay phiên nhau ở bốn hạng đầu sau dòng neo.
    changed = [
        next(i for i in range(4) if frames[i] != base[i])
        for _, frames in got[1:5]
    ]
    assert changed == [0, 1, 2, 3]

    # Mọi giá trị mới nằm trong đúng khoảng đã khoanh.
    windows = [(90, 120), (230, 275), (322, 350), (420, 444)]
    for _, frames in got[1:]:
        position = next(i for i in range(4) if frames[i] != base[i])
        lo, hi = windows[position]
        assert lo <= frames[position] <= hi


def test_per_event_direction_through_the_endpoint(conn):
    from app.routers.answers import AutofillRequest, EventRange, autofill_answers

    user = _user(conn)
    task = _task(conn, user["id"], n_events=2)
    _pin(conn, task, user["id"], "L26_V194", [100, 250], 1.0)

    autofill_answers(
        task,
        AutofillRequest(
            limit=7,
            mode="append",
            event_ranges=[
                EventRange(lo=90, hi=120, mode="up"),
                EventRange(lo=230, hi=275, mode="down"),
            ],
        ),
        user,
        conn,
    )
    got = _rows(conn, task)[1:]
    for _, frames in got:
        assert frames[0] >= 100, "E1 chỉ lên"
        assert frames[1] <= 250, "E2 chỉ xuống"


def test_an_event_left_unranged_never_moves(conn):
    """Chỉ khoanh E1 thì ba mốc kia đứng yên, không bị đoán bừa."""
    from app.routers.answers import AutofillRequest, EventRange, autofill_answers

    user = _user(conn)
    task = _task(conn, user["id"])
    _pin(conn, task, user["id"], "L26_V194", [100, 250, 333, 432], 1.0)

    autofill_answers(
        task,
        AutofillRequest(
            limit=6, mode="append", event_ranges=[EventRange(lo=90, hi=120)]
        ),
        user,
        conn,
    )
    for _, frames in _rows(conn, task)[1:]:
        assert frames[1:] == [250, 333, 432]


def test_two_anchor_rows_alternate_through_the_endpoint(conn):
    from app.routers.answers import AutofillRequest, EventRange, autofill_answers

    user = _user(conn)
    task = _task(conn, user["id"], n_events=2)
    _pin(conn, task, user["id"], "L26_V194", [100, 250], 1.0)
    _pin(conn, task, user["id"], "L26_V200", [700, 800], 2.0)

    autofill_answers(
        task,
        AutofillRequest(
            limit=6,
            mode="append",
            event_ranges=[
                EventRange(lo=90, hi=120),
                EventRange(lo=230, hi=275),
            ],
        ),
        user,
        conn,
    )
    videos = [video for video, _ in _rows(conn, task)]
    assert videos[:2] == ["L26_V194", "L26_V200"], "hai dòng neo"
    assert videos[2] == "L26_V194", "hạng 3 lấy từ dòng neo 1"
    assert videos[3] == "L26_V200", "hạng 4 lấy từ dòng neo 2"


def test_without_event_ranges_trake_still_shifts_the_whole_tuple(conn):
    """Không khoanh khoảng thì giữ nguyên cách cũ — mọi lời gọi hiện có không đổi."""
    from app.routers.answers import AutofillRequest, autofill_answers

    user = _user(conn)
    task = _task(conn, user["id"], n_events=3)
    _pin(conn, task, user["id"], "L26_V194", [100, 150, 220], 1.0)

    autofill_answers(
        task,
        AutofillRequest(limit=3, step=2, mode="append", direction="up"),
        user,
        conn,
    )
    assert _rows(conn, task) == [
        ("L26_V194", [100, 150, 220]),
        ("L26_V194", [102, 152, 222]),
        ("L26_V194", [104, 154, 224]),
    ]


def test_a_second_anchor_gets_the_window_as_an_offset_not_as_absolute_frames(conn):
    """Khoảng gõ vào là số tuyệt đối, đọc từ dòng neo ĐẦU TIÊN.

    Đem nguyên si áp lên dòng neo thứ hai ở một video khác thì vô nghĩa: nó
    từng cho ra [120, 800, 900, 1000] — lấy khoảng của video này gán cho hành
    động của video kia. Quy về độ lệch quanh mốc gốc rồi mới áp.
    """
    from app.routers.answers import AutofillRequest, EventRange, autofill_answers

    user = _user(conn)
    task = _task(conn, user["id"], n_events=2)
    _pin(conn, task, user["id"], "L26_V194", [100, 250], 1.0)
    _pin(conn, task, user["id"], "L26_V200", [700, 800], 2.0)

    autofill_answers(
        task,
        AutofillRequest(
            limit=8,
            mode="append",
            # E1 của dòng neo 1 là 100, khoảng 90→120 = lệch −10…+20.
            event_ranges=[EventRange(lo=90, hi=120), EventRange(lo=230, hi=275)],
        ),
        user,
        conn,
    )
    for video, frames in _rows(conn, task)[2:]:
        if video == "L26_V194":
            assert 90 <= frames[0] <= 120 and 230 <= frames[1] <= 275
        else:
            # Cùng độ lệch, quanh mốc gốc CỦA NÓ: 700−10…700+20.
            assert 690 <= frames[0] <= 720 and 780 <= frames[1] <= 825


def test_the_window_is_covered_end_to_end_not_just_around_the_anchor(conn):
    """Hạn mức phải chia theo TỪNG sự kiện, không phải cả lượt.

    Truyền hạn mức tổng vào event_variants sinh mọi frame trong khoảng, rồi
    vòng quay chỉ lấy phần gần mốc gốc nhất — cắt đúng hai đầu người dùng vừa
    khoanh. Đo được: E1 dừng ở 115 dù khoanh tới 120.
    """
    from app.routers.answers import AutofillRequest, EventRange, autofill_answers

    user = _user(conn)
    task = _task(conn, user["id"])
    base = [100, 250, 333, 432]
    _pin(conn, task, user["id"], "L26_V194", base, 1.0)

    autofill_answers(
        task,
        AutofillRequest(
            limit=100,
            mode="append",
            event_ranges=[
                EventRange(lo=90, hi=120),
                EventRange(lo=230, hi=275),
                EventRange(lo=322, hi=350),
                EventRange(lo=420, hi=444),
            ],
        ),
        user,
        conn,
    )
    rows = _rows(conn, task)
    assert len(rows) == 100
    windows = [(90, 120), (230, 275), (322, 350), (420, 444)]
    for position, (lo, hi) in enumerate(windows):
        seen = {
            frames[position]
            for _, frames in rows[1:]
            if frames[position] != base[position]
        }
        assert min(seen) == lo, f"E{position + 1} không chạm mút dưới"
        assert max(seen) == hi, f"E{position + 1} không chạm mút trên"
