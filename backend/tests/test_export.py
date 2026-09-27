"""Row shapes confirmed against the 2025 ground truth in
docs/Danh_gia_Query_AIC2025.md."""
from app.db.connection import utcnow_iso
from app.routers.export import clean_answer, csv_content, export_filename, validate_export
from app.settings_store import DEFAULTS

SETTINGS = {key: default for key, (default, _) in DEFAULTS.items()}


def task(task_type: str, n_events: int | None = None) -> dict:
    return {"type": task_type, "n_events": n_events}


def answer(video_id: str, frames: list[int], text: str | None = None) -> dict:
    return {"video_id": video_id, "frames": frames, "answer_text": text}


def test_kis_row_is_video_and_frame():
    assert csv_content(SETTINGS, task("kis"), [answer("L21_V015", [25605])]) == (
        "L21_V015,25605\n"
    )


def test_qa_row_appends_the_answer():
    assert csv_content(
        SETTINGS, task("qa"), [answer("L30_V072", [1745], "Xã Giang Ly")]
    ) == "L30_V072,1745,Xã Giang Ly\n"


def test_qa_answer_with_a_comma_goes_out_verbatim():
    """Dấu phẩy trong đáp án KHÔNG còn được bọc nháy nữa.

    Bọc lại là quay về đúng cơ chế đã đẻ ra lỗi ba-dấu-nháy. Đổi lại, bên chấm
    sẽ đọc dòng này thành bốn trường — không có cách nào vừa giữ nguyên chữ vừa
    tránh được điều đó ở một định dạng không có quy ước bọc trường.
    validate_export vẫn báo dấu phẩy để nhóm tự sửa câu văn trước khi nộp.
    """
    out = csv_content(
        SETTINGS, task("qa"), [answer("L27_V010", [5550], "Hoả hồng Nhật Tảo, Kiếm bạch")]
    )
    assert out == "L27_V010,5550,Hoả hồng Nhật Tảo, Kiếm bạch\n"


# ── Dấu nháy trong đáp án ────────────────────────────────────────────────────
#
# Yêu cầu đã ĐỔI. Bản cũ xoá sạch dấu nháy để chữa lỗi ba-dấu-nháy của vòng 1
# (spec.md:35); các test cũ khoá đúng hành vi đó và nằm ngay dưới đây, đã viết
# lại. Xoá dấu nháy chữa được triệu chứng nhưng làm mất nội dung người dùng cố
# ý gõ: gõ "13" thì file phải có "13".
#
# Thủ phạm thật là csv.writer, không phải dấu nháy — xem docstring csv_content.


def test_clean_answer_folds_curly_quotes_but_keeps_them():
    """Nháy cong -> nháy thẳng, KHÔNG biến mất.

    Nắn lại để dán từ đề bài của ban tổ chức và gõ tay ra cùng một byte.
    """
    assert clean_answer("“màu xanh”") == '"màu xanh"' 


def test_clean_answer_keeps_plain_double_quotes():
    assert clean_answer('hồ "Gươm"') == 'hồ "Gươm"' 


def test_clean_answer_passes_ordinary_vietnamese_text_through_unchanged():
    assert clean_answer("màu xanh") == "màu xanh"


def test_clean_answer_handles_none_and_empty_without_crashing():
    assert clean_answer(None) == ""
    assert clean_answer("") == ""


def test_qa_answer_with_quotes_has_exactly_one_quote_each_side():
    """Đúng lỗi người dùng báo: gõ hai dấu nháy, ra file phải là hai.

    Không mất (bản trước xoá sạch) và không nhân lên thành sáu (csv.writer bọc
    cả trường rồi nhân đôi nháy bên trong).
    """
    out = csv_content(
        SETTINGS, task("qa"), [answer("L24_V033", [3333], '"13"')]
    )
    assert out == 'L24_V033,3333,"13"\n'
    assert out.count('"') == 2


def test_qa_answer_with_a_plain_quote_is_neither_removed_nor_escaped():
    out = csv_content(SETTINGS, task("qa"), [answer("L27_V010", [5550], 'hồ "Gươm"')])
    assert out == 'L27_V010,5550,hồ "Gươm"\n'
    assert out.count('"') == 2


def test_a_newline_in_the_answer_becomes_a_space():
    """Thứ DUY NHẤT bắt buộc phải đụng tới.

    Một ký tự xuống dòng lọt vào ô đáp án sẽ cắt một dòng thành hai, đẩy lệch
    toàn bộ thứ hạng phía sau — hỏng nặng hơn nhiều so với việc mất dấu nháy.
    """
    out = csv_content(
        SETTINGS, task("qa"), [answer("L05_V005", [888], "dòng một\ndòng hai")]
    )
    assert out == "L05_V005,888,dòng một dòng hai\n"
    assert out.count("\n") == 1


def test_qa_vietnamese_answer_is_unchanged_byte_for_byte():
    out = csv_content(SETTINGS, task("qa"), [answer("L05_V005", [888], "màu xanh")])
    assert out == "L05_V005,888,màu xanh\n"
    assert out.encode("utf-8") == "L05_V005,888,màu xanh\n".encode("utf-8")


def test_qa_answer_none_or_empty_is_an_empty_field_not_a_crash():
    assert csv_content(SETTINGS, task("qa"), [answer("L05_V005", [888], None)]) == (
        "L05_V005,888,\n"
    )
    assert csv_content(SETTINGS, task("qa"), [answer("L05_V005", [888], "")]) == (
        "L05_V005,888,\n"
    )


def test_qa_row_with_quotes_still_starts_with_the_video_id_and_has_no_bom():
    """Dòng phải mở đầu bằng mã video, không phải bằng dấu nháy.

    Đây là thứ phân biệt "giữ nháy trong đáp án" với "bọc nháy cả trường":
    cách sau đẩy một dấu nháy ra đầu trường thứ ba, cách này thì không.
    """
    data = csv_content(
        SETTINGS, task("qa"), [answer("L05_V005", [888], "“màu xanh”")]
    ).encode("utf-8")
    assert data.startswith(b"L05_V005")
    assert not data.startswith(b"\xef\xbb\xbf")
    assert data == 'L05_V005,888,"màu xanh"\n'.encode("utf-8")


def _seed_qa_task(conn, answer_text: str, code: str = "27") -> int:
    """One user, one pack, one qa task with a single answer row. Returns pack_id."""
    conn.execute(
        "INSERT INTO users (username, display_name, role, password_hash, "
        "must_change_password, disabled, created_at) VALUES ('nam','Nam','member','x',0,0,?)",
        (utcnow_iso(),),
    )
    conn.execute(
        "INSERT INTO packs (round_label, source_filename, filename_pattern, "
        "imported_by, imported_at, active) VALUES ('R1','p.zip','x',1,?,1)",
        (utcnow_iso(),),
    )
    pack_id = conn.execute("SELECT id FROM packs").fetchone()["id"]
    # chosen_author_id = 1: bài nộp là MỘT danh sách, nên task phải chỉ ra lấy
    # của ai. Bỏ trống thì validate dừng ngay ở "chưa chọn bài của ai để nộp"
    # và không bao giờ tới được phép kiểm dấu phẩy mà test này nhắm vào.
    conn.execute(
        "INSERT INTO tasks (pack_id, code, type, query_text, chosen_author_id) "
        "VALUES (?, ?, 'qa', 'a', 1)",
        (pack_id, code),
    )
    task_id = conn.execute("SELECT id FROM tasks WHERE code = ?", (code,)).fetchone()["id"]
    conn.execute(
        "INSERT INTO answers (task_id, author_id, sort_key, video_id, frames, "
        "answer_text, origin, created_by, updated_at, version) "
        "VALUES (?, 1, 1.0, 'L27_V010', '[5550]', ?, 'manual', 1, ?, 1)",
        (task_id, answer_text, utcnow_iso()),
    )
    return pack_id


def test_validate_export_warns_about_a_comma_in_a_qa_answer(conn):
    pack_id = _seed_qa_task(conn, "Hoả hồng Nhật Tảo, Kiếm bạch")

    result = validate_export(None, conn, pack_id)

    matches = [
        issue
        for issue in result["issues"]
        if issue["task_code"] == "27" and "phẩy" in issue["message"]
    ]
    assert len(matches) == 1
    assert matches[0]["severity"] == "warning"


def test_validate_export_does_not_warn_when_there_is_no_comma(conn):
    pack_id = _seed_qa_task(conn, "màu xanh")

    result = validate_export(None, conn, pack_id)

    assert not [issue for issue in result["issues"] if "phẩy" in issue["message"]]


def test_trake_row_lists_every_event_frame():
    assert csv_content(
        SETTINGS, task("trake", 4), [answer("L26_V194", [4707, 5100, 5425, 5850])]
    ) == "L26_V194,4707,5100,5425,5850\n"


def test_no_bom_and_lf_line_endings():
    data = csv_content(SETTINGS, task("kis"), [answer("L21_V015", [25605])]).encode("utf-8")
    assert not data.startswith(b"\xef\xbb\xbf")
    assert b"\r" not in data


def test_crlf_is_opt_in():
    settings = {**SETTINGS, "export.line_ending": "CRLF"}
    assert csv_content(settings, task("kis"), [answer("L21_V015", [25605])]).endswith("\r\n")


def test_header_is_off_by_default_and_opt_in():
    rows = [answer("L21_V015", [25605])]
    assert not csv_content(SETTINGS, task("kis"), rows).startswith("video_id")
    settings = {**SETTINGS, "export.header": True}
    assert csv_content(settings, task("kis"), rows).startswith("video_id,frame")


def test_output_filename_reuses_the_input_stem():
    assert export_filename("query-p1-15-qa.txt") == "query-p1-15-qa.csv"
    assert export_filename("query-p1-4-trake.txt") == "query-p1-4-trake.csv"


def test_filename_falls_back_to_the_pattern_when_there_is_no_source():
    assert export_filename("", SETTINGS, "15", "qa") == "query-15-qa.csv"


def test_empty_basket_produces_an_empty_file_not_an_error():
    assert csv_content(SETTINGS, task("kis"), []) == ""


# ── Số vòng trong tên file nộp ───────────────────────────────────────────────
#
# Đây là lỗi đã làm mất một lượt thi thật: export viết cứng "p1", nên gói vòng
# hai xuất ra vẫn mang tên `query-p1-…`. Không có gì trên giao diện báo, và chỉ
# biết khi bài đã bị chấm hỏng.


def test_phase_that_was_never_recorded_falls_back_to_p1(conn):
    from app.routers.export import pack_phase

    pack_id = _seed_qa_task(conn, "x")
    assert pack_phase(conn, pack_id) == "p1"


def test_the_pack_phase_decides_every_filename_in_the_zip(conn):
    """Đặt vòng 2 thì cả gói phải đổi tên, không riêng file nào."""
    import io
    import zipfile

    from app.routers.export import build_zip, set_phase, PhaseRequest

    pack_id = _seed_qa_task(conn, "đáp án")
    user = conn.execute("SELECT * FROM users WHERE id = 1").fetchone()

    set_phase(PhaseRequest(phase="2"), user, conn, pack_id)

    names = zipfile.ZipFile(io.BytesIO(build_zip(conn, pack_id))).namelist()
    assert names == ["query-p2-27-qa.csv"]


def test_a_bare_number_and_a_p_prefix_mean_the_same_thing(conn):
    """Người ta gõ "2" khi được hỏi "vòng mấy", không gõ "p2"."""
    from app.routers.export import normalize_phase

    assert normalize_phase("2") == "p2"
    assert normalize_phase("p2") == "p2"
    assert normalize_phase("P2") == "p2"
    assert normalize_phase(" p3 ") == "p3"
    # Giá trị này đi thẳng vào tên file nộp, nên rác phải bị chặn chứ không
    # được đi tiếp thành `query-p../../etc-15-qa.csv`.
    assert normalize_phase("../etc") == "p1"
    assert normalize_phase("") == "p1"
    assert normalize_phase(None) == "p1"


def test_the_zip_is_always_called_submission_zip(conn):
    """Tên gói ngoài cố định, không đổi theo nhãn vòng.

    Nhãn vòng tiếng Việt từng làm Starlette ném UnicodeEncodeError khi ghi
    header — header HTTP chỉ mã hoá được latin-1 — nên nút "Tải zip" trả 500
    đúng vào lúc cần nộp nhất.
    """
    from app.routers.export import export_zip

    pack_id = _seed_qa_task(conn, "x")
    conn.execute(
        "UPDATE packs SET round_label = 'Vòng sơ tuyển — thử' WHERE id = ?",
        (pack_id,),
    )

    disposition = export_zip(None, conn, pack_id).headers["content-disposition"]
    assert 'filename="submission.zip"' in disposition
    disposition.encode("latin-1")  # nổ ở đây nghĩa là lỗi 500 đã quay lại


def test_a_task_nobody_touched_becomes_an_empty_file_not_a_refusal(conn):
    """Gói nộp luôn phải đủ 25 file.

    Bản trước từ chối cả gói khi một câu chưa có người được chọn — kể cả câu
    chưa ai làm, thứ vĩnh viễn không thể chọn được ai. Chỉ cần một câu bỏ trống
    là không tải được zip.
    """
    import io
    import zipfile

    from app.routers.export import build_zip

    pack_id = _seed_qa_task(conn, "x")
    conn.execute(
        "INSERT INTO tasks (pack_id, code, type, query_text) "
        "VALUES (?, '28', 'kis', 'chưa ai làm')",
        (pack_id,),
    )

    archive = zipfile.ZipFile(io.BytesIO(build_zip(conn, pack_id)))
    assert archive.namelist() == ["query-p1-27-qa.csv", "query-p1-28-kis.csv"]
    assert archive.read("query-p1-28-kis.csv") == b""
