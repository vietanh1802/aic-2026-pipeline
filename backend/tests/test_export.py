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


def test_qa_answer_with_a_comma_is_quoted():
    out = csv_content(
        SETTINGS, task("qa"), [answer("L27_V010", [5550], "Hoả hồng Nhật Tảo, Kiếm bạch")]
    )
    assert out == 'L27_V010,5550,"Hoả hồng Nhật Tảo, Kiếm bạch"\n'


# ── smart-quote / plain-quote cleanup (round-1 feedback, spec.md:35) ────────


def test_clean_answer_folds_curly_double_quotes_and_drops_them():
    assert clean_answer("“màu xanh”") == "màu xanh"


def test_clean_answer_removes_plain_double_quotes():
    assert clean_answer('hồ "Gươm"') == "hồ Gươm"


def test_clean_answer_passes_ordinary_vietnamese_text_through_unchanged():
    assert clean_answer("màu xanh") == "màu xanh"


def test_clean_answer_handles_none_and_empty_without_crashing():
    assert clean_answer(None) == ""
    assert clean_answer("") == ""


def test_qa_answer_with_smart_quotes_has_no_quote_characters_in_the_row():
    # This is the bug in spec.md:35: a " " in the answer used to come back
    # from csv.writer as a run of three consecutive quote characters.
    out = csv_content(
        SETTINGS, task("qa"), [answer("L05_V005", [888], "“màu xanh”")]
    )
    assert out == "L05_V005,888,màu xanh\n"
    assert '"' not in out


def test_qa_answer_with_a_plain_quote_is_removed_not_escaped():
    out = csv_content(SETTINGS, task("qa"), [answer("L27_V010", [5550], 'hồ "Gươm"')])
    assert out == "L27_V010,5550,hồ Gươm\n"
    assert '"' not in out


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
    data = csv_content(
        SETTINGS, task("qa"), [answer("L05_V005", [888], "“màu xanh”")]
    ).encode("utf-8")
    assert data.startswith(b"L05_V005")
    assert not data.startswith(b"\xef\xbb\xbf")


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
    conn.execute(
        "INSERT INTO tasks (pack_id, code, type, query_text) VALUES (?, ?, 'qa', 'a')",
        (pack_id, code),
    )
    task_id = conn.execute("SELECT id FROM tasks WHERE code = ?", (code,)).fetchone()["id"]
    conn.execute(
        "INSERT INTO answers (task_id, sort_key, video_id, frames, answer_text, "
        "origin, created_by, updated_at, version) VALUES (?, 1.0, 'L27_V010', '[5550]', ?, "
        "'manual', 1, ?, 1)",
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
