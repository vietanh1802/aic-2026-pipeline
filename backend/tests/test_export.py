"""Row shapes confirmed against the 2025 ground truth in
docs/Danh_gia_Query_AIC2025.md."""
from app.routers.export import csv_content, export_filename
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
