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


def test_qa_question_is_the_last_sentence_ending_in_a_question_mark():
    text = (
        "Đoạn video về một chương trình từ thiện của câu lạc bộ FANA. "
        "Câu lạc bộ đang trao quà tại một xã thuộc tỉnh Khánh Hòa. "
        "Hỏi xã này có tên là gì? (tại thời điểm đó)"
    )
    task = parse("query-p1-15-qa.txt", text)
    assert task.question_text == "Hỏi xã này có tên là gì? (tại thời điểm đó)"
    assert task.query_text == text


def test_qa_without_a_question_mark_says_so():
    task = parse("query-p1-99-qa.txt", "Không có dấu hỏi nào ở đây.")
    assert task.question_text is None
    assert any("?" in warning for warning in task.warnings)


def test_trake_counts_event_lines_not_the_highest_number():
    # query-p1-18-trake.txt really does carry E1, E2, E2, E4.
    text = "E1: cắt nấm\nE2: cắt củ năng\nE2: cắt đậu hủ\nE4: bật bếp"
    task = parse("query-p1-18-trake.txt", text)
    assert task.n_events == 4
    assert task.event_labels == ["cắt nấm", "cắt củ năng", "cắt đậu hủ", "bật bếp"]
    assert any("not sequential" in warning for warning in task.warnings)


def test_trake_context_before_the_first_event_becomes_the_query():
    text = "Đoạn video múa lân màu vàng đen trắng.\nE1: lân xoay vòng\nE2: bốn chân chạm đất"
    task = parse("query-p1-16-trake.txt", text)
    assert task.query_text == "Đoạn video múa lân màu vàng đen trắng."
    assert task.n_events == 2


def test_trake_accepts_a_dot_after_the_event_number():
    task = parse("query-p1-20-trake.txt", "E1. một\nE2. hai")
    assert task.n_events == 2


def test_sequential_events_raise_no_warning():
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

    warned = [task for task in matched if task.warnings]
    assert [task.code for task in warned] == ["18"]

    # Every Q&A question was inferred; none fell back to null.
    assert all(task.question_text for task in matched if task.type == "qa")
