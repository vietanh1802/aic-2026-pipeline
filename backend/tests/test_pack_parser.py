"""Measured against sample-data/query-p1-groupA.zip.

Every assertion here comes from one of the five differences spec §5.2 records
between the real organizer pack and the layout the first importer assumed.
"""
import pathlib

import pytest

from app.packs.parser import DEFAULT_PATTERN, parse_member, parse_zip


def parse(filename, text):
    return parse_member(filename, text, DEFAULT_PATTERN)


def test_filename_yields_phase_code_and_type():
    task = parse("query-p1-15-qa.txt", "x?")
    assert task.matched
    assert (task.phase, task.code, task.type) == ("p1", "15", "qa")


def test_code_is_not_zero_padded():
    assert parse("query-p1-4-trake.txt", "E1: a\nE2: b").code == "4"


def test_unmatched_file_is_reported_not_raised():
    task = parse("readme.txt", "hello")
    assert not task.matched
    assert "does not match" in task.error


def test_csv_extension_does_not_match():
    # The first importer assumed .csv. The organizer ships .txt.
    assert not parse("query-p1-1-kis.csv", "x").matched


def test_kis_keeps_every_line_of_the_file():
    text = "Dòng một.\nDòng hai.\nDòng ba."
    task = parse("query-p1-1-kis.txt", text + "\n")
    assert task.query_text == text
    assert task.lines == 3


# ── Đề bài vào nguyên văn ────────────────────────────────────────────────────
#
# Năm test dưới đây thay cho năm test cũ, vốn chốt hai cơ chế đoán vừa bỏ:
# tách câu hỏi Q&A (câu cuối có dấu "?") và tách mốc TRAKE (regex `^E(\d+)`).
#
# Bộ SOTUYEN2 cho thấy cả hai đều đoán sai theo kiểu im lặng —
# `query-p2-8-trake.txt` mở đầu bằng một dòng dẫn nhập nên bốn mốc bị tách ra
# khỏi `query_text` rồi bị frontend bỏ quên, còn `query-p2-21-trake.txt` viết
# `Cảnh 1:` nên không khớp regex, ra 0 mốc, và câu TRAKE đó xuất một cột frame
# như câu KIS. Số mốc giờ do admin gõ ở màn Import.


def test_qa_keeps_the_whole_file_and_infers_no_question():
    text = (
        "Đoạn video về một chương trình từ thiện của câu lạc bộ FANA. "
        "Câu lạc bộ đang trao quà tại một xã thuộc tỉnh Khánh Hòa. "
        "Hỏi xã này có tên là gì? (tại thời điểm đó)"
    )
    task = parse("query-p1-15-qa.txt", text)
    assert task.query_text == text
    assert task.question_text is None


def test_qa_without_a_question_mark_is_not_a_warning_any_more():
    task = parse("query-p1-99-qa.txt", "Không có dấu hỏi nào ở đây.")
    assert task.query_text == "Không có dấu hỏi nào ở đây."
    assert task.warnings == []


def test_trake_keeps_the_event_lines_inside_the_brief():
    text = "E1: cắt nấm\nE2: cắt củ năng\nE2: cắt đậu hủ\nE4: bật bếp"
    task = parse("query-p1-18-trake.txt", text)
    assert task.query_text == text
    assert task.event_labels == []
    # Số mốc không đoán nữa: E1, E2, E2, E4 là bốn dòng nhưng số cao nhất là 4,
    # và `Cảnh 1:` thì không có số nào để đếm. Người nhập gõ.
    assert task.n_events is None


def test_trake_context_line_stays_with_the_events():
    text = "Đoạn video múa lân màu vàng đen trắng.\nE1: lân xoay vòng\nE2: bốn chân chạm đất"
    task = parse("query-p1-16-trake.txt", text)
    assert task.query_text == text
    assert "lân xoay vòng" in task.query_text


def test_trake_written_with_canh_instead_of_e_is_kept_whole():
    # query-p2-21-trake.txt. Regex cũ khớp 0 dòng ở đây và nuốt mất cả bốn mốc.
    text = (
        "4 cảnh này xảy ra liên tiếp nhau.\n"
        "Cảnh 1: Hai người phụ nữ dán niêm phong một thùng carton.\n"
        "Cảnh 2: Các thùng mì tôm được sắp xếp ngay ngắn."
    )
    task = parse("query-p2-21-trake.txt", text)
    assert task.query_text == text
    assert "Cảnh 2" in task.query_text


def test_no_file_shape_raises_a_warning_any_more():
    task = parse("query-p1-4-trake.txt", "E1: a\nE2: b\nE3: c\nE4: d")
    assert task.warnings == []


@pytest.mark.parametrize("bom", ["", "﻿"])
def test_leading_bom_and_surrounding_blank_lines_are_trimmed(bom):
    task = parse("query-p1-2-kis.txt", bom + "\n\n  nội dung  \n\n")
    assert task.query_text == "nội dung"


SAMPLE = (
    pathlib.Path(__file__).resolve().parents[2] / "sample-data" / "query-p1-groupA.zip"
)


@pytest.mark.skipif(not SAMPLE.exists(), reason="sample pack not checked out")
def test_the_real_pack_parses_the_way_the_spec_measured_it():
    tasks = parse_zip(SAMPLE.read_bytes(), DEFAULT_PATTERN)
    matched = [task for task in tasks if task.matched]

    assert len(tasks) == 24
    assert len(matched) == 24

    kinds: dict[str, int] = {}
    for task in matched:
        kinds[task.type] = kinds.get(task.type, 0) + 1
    assert kinds == {"kis": 18, "trake": 3, "qa": 3}

    codes = [int(task.code) for task in matched]
    assert codes == sorted(codes)
    assert 3 not in codes                      # gaps in the numbering are normal
    assert max(codes) == 25 and len(codes) == 24

    # Không còn cảnh báo nào: cả hai chỗ sinh ra chúng — số mốc không liên tục
    # và Q&A thiếu dấu "?" — đều là kết luận của việc đoán cấu trúc, mà giờ
    # không ai đoán nữa. Task 18 từng là cái duy nhất bị cảnh báo.
    assert [task.code for task in matched if task.warnings] == []

    # Đề bài vào nguyên văn, không file nào bị nuốt mất chữ.
    assert all(task.query_text for task in matched)
    assert all(task.question_text is None for task in matched)
    assert all(task.n_events is None for task in matched)
