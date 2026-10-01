from __future__ import annotations

import json

import pytest

from app.evaluation.seed import SEEDS_DIR, import_all_seeds, import_seed

ROUND1 = SEEDS_DIR / "round1-v2.json"
ROUND2 = SEEDS_DIR / "round2-v1.json"
ROUND3 = SEEDS_DIR / "round3-v1.json"
FINAL = SEEDS_DIR / "final-v1.json"

# 24 + 29 + 33 + 28, the current (highest-version) seed per round: round1-v3,
# round2-v2, round3-v2, final-v1 -- see import_all_seeds()'s _discover_current_seed_files().
TOTAL_QUERIES = 114


def _count(conn, table : str) -> int :
    return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def test_seed_files_are_present() :
    assert ROUND1.exists()
    assert ROUND2.exists()
    assert ROUND3.exists()
    assert FINAL.exists()


def test_import_all_seeds_registers_every_round(conn) :
    results = import_all_seeds(conn)
    versions = {result["dataset_version"] for result in results}
    assert versions == {"round1-v3", "round2-v2", "round3-v2", "final-v1"}

    assert _count(conn, "evaluation_datasets") == 4
    assert _count(conn, "evaluation_queries") == TOTAL_QUERIES
    assert _count(conn, "evaluation_reference_sets") == 4
    assert _count(conn, "evaluation_references") == TOTAL_QUERIES


def test_import_is_idempotent(conn) :
    first = import_all_seeds(conn)
    second = import_all_seeds(conn)
    assert [r["query_count"] for r in first] == [r["query_count"] for r in second]
    assert _count(conn, "evaluation_datasets") == 4
    assert _count(conn, "evaluation_queries") == TOTAL_QUERIES
    assert _count(conn, "evaluation_references") == TOTAL_QUERIES


def test_task_counts_match_the_declared_breakdown(conn) :
    import_all_seeds(conn)
    rows = conn.execute(
        """
        SELECT d.version, q.task_type, COUNT(*) AS n
        FROM evaluation_queries q
        JOIN evaluation_datasets d ON d.id = q.dataset_id
        GROUP BY d.version, q.task_type
        """
    ).fetchall()
    counts = {(row["version"], row["task_type"]) : row["n"] for row in rows}
    assert counts[("round1-v3", "KIS")] == 19
    assert counts[("round1-v3", "QA")] == 4
    assert counts[("round1-v3", "TRAKE")] == 1
    assert counts[("round2-v2", "KIS")] == 19
    assert counts[("round2-v2", "QA")] == 8
    assert counts[("round2-v2", "TRAKE")] == 2
    assert counts[("round3-v2", "KIS")] == 25
    assert counts[("round3-v2", "QA")] == 6
    assert counts[("round3-v2", "TRAKE")] == 2
    assert counts[("final-v1", "KIS")] == 14
    assert counts[("final-v1", "QA")] == 11
    assert counts[("final-v1", "TRAKE")] == 3


# Round 3 keeps the original question numbers as ordinals, so 34 is simply
# absent rather than the rest being shifted up — a result row still points back
# at the organiser's question number.
def test_round3_keeps_question_numbers_and_drops_question_34(conn) :
    import_seed(conn, ROUND3)
    rows = conn.execute(
        """
        SELECT q.query_key, q.ordinal FROM evaluation_queries q
        JOIN evaluation_datasets d ON d.id = q.dataset_id
        WHERE d.version = 'round3-v1' ORDER BY q.ordinal
        """
    ).fetchall()
    ordinals = [row["ordinal"] for row in rows]
    assert ordinals == [n for n in range(1, 37) if n != 34]
    assert [row["query_key"] for row in rows] == [f"p3-{n}" for n in ordinals]


# The organiser's Round 3 filenames reuse the 'p2-' prefix; ids must not collide
# with round2-v1 or one round's references would overwrite the other's.
def test_round3_ids_do_not_collide_with_round2(conn) :
    import_all_seeds(conn)
    duplicated = conn.execute(
        """
        SELECT query_key, COUNT(DISTINCT dataset_id) AS n
        FROM evaluation_queries GROUP BY query_key HAVING n > 1
        """
    ).fetchall()
    assert duplicated == []


def test_round3_intervals_come_from_the_submitted_span(conn) :
    import_seed(conn, ROUND3)
    row = conn.execute(
        """
        SELECT r.video_id, r.valid_intervals_json, r.interval_count,
               r.reference_frame_idx, r.confidence, r.qa_answer
        FROM evaluation_references r
        JOIN evaluation_queries q ON q.id = r.query_id
        WHERE q.query_key = 'p3-8'
        """
    ).fetchone()
    intervals = json.loads(row["valid_intervals_json"])
    assert row["video_id"] == "L21_V018"
    assert row["confidence"] == "submission_derived_span"
    assert row["qa_answer"] == "SEGA"            # nháy bao quanh đã được bóc
    assert row["interval_count"] == len(intervals) == 1
    # Khung mỏ neo là dòng 1 của file nộp, và phải nằm trong khoảng suy ra.
    assert intervals[0]["start"] <= row["reference_frame_idx"] <= intervals[0]["end"]


# Chung kết chỉ có mốc từ tài liệu phúc khảo (không duyệt tay thành khoảng như
# vòng 1–3): mốc phải nằm trong khoảng suy ra, và qa-query-14 giữ nguyên số frame
# 11310–13140 chứ không bị đổi như ms.
def test_final_intervals_come_from_the_appeal_answers(conn) :
    import_seed(conn, FINAL)
    rows = conn.execute(
        """
        SELECT q.query_key, q.task_type, r.video_id, r.valid_intervals_json,
               r.reference_frame_idx, r.qa_answer
        FROM evaluation_references r
        JOIN evaluation_queries q ON q.id = r.query_id
        """
    ).fetchall()
    by_key = {row["query_key"] : row for row in rows}
    for row in rows :
        if row["task_type"] == "TRAKE" :
            continue
        (interval,) = json.loads(row["valid_intervals_json"])
        assert interval["start"] <= row["reference_frame_idx"] <= interval["end"]
    assert json.loads(by_key["f2-qa-14"]["valid_intervals_json"]) == [{"start" : 11310, "end" : 13140}]
    assert by_key["f2-qa-14"]["qa_answer"] == "LONGTHUY"
    assert by_key["f1-tkis-10"]["video_id"] == "S01-V009"   # tên video S giữ dấu gạch ngang
    assert by_key["f1-trake-01"]["video_id"] == "S01-V011"  # đáp án ghi S01_V011


def test_intervals_are_persisted_as_json_lists(conn) :
    import_seed(conn, ROUND2)
    row = conn.execute(
        """
        SELECT r.valid_intervals_json, r.interval_count
        FROM evaluation_references r
        JOIN evaluation_queries q ON q.id = r.query_id
        WHERE q.query_key = 'p2-24'
        """
    ).fetchone()
    intervals = json.loads(row["valid_intervals_json"])
    assert len(intervals) == 5
    assert row["interval_count"] == 5
    assert all(iv["start"] <= iv["end"] for iv in intervals)


def test_trake_reference_has_no_intervals(conn) :
    import_seed(conn, ROUND1)
    row = conn.execute(
        """
        SELECT r.valid_intervals_json, r.interval_count, r.trake_events_json
        FROM evaluation_references r
        JOIN evaluation_queries q ON q.id = r.query_id
        WHERE q.query_key = 'p1-16'
        """
    ).fetchone()
    assert row["valid_intervals_json"] is None
    assert row["interval_count"] == 0
    assert json.loads(row["trake_events_json"])  # events kept, descriptive only


def test_p1_8_and_p1_14_duplicate_kept_as_is(conn) :
    import_seed(conn, ROUND1)
    rows = conn.execute(
        """
        SELECT q.query_key, q.query_vi, r.video_id, r.valid_intervals_json, r.notes
        FROM evaluation_queries q
        JOIN evaluation_references r ON r.query_id = q.id
        WHERE q.query_key IN ('p1-8', 'p1-14')
        ORDER BY q.query_key
        """
    ).fetchall()
    assert len(rows) == 2
    assert rows[0]["query_vi"] == rows[1]["query_vi"]
    assert rows[0]["video_id"] == rows[1]["video_id"]
    assert rows[0]["valid_intervals_json"] == rows[1]["valid_intervals_json"]
    assert "KNOWN ISSUE" in rows[0]["notes"]
    assert "KNOWN ISSUE" in rows[1]["notes"]


def test_round2_null_sha256_is_replaced_by_a_content_hash(conn, tmp_path) :
    import_seed(conn, ROUND2)
    stored = conn.execute(
        "SELECT source_sha256 FROM evaluation_datasets WHERE version = 'round2-v1'"
    ).fetchone()["source_sha256"]
    assert stored is not None and len(stored) == 64

    # re-seeding the untouched file still matches
    import_seed(conn, ROUND2)

    # an edited query list is refused
    edited = json.loads(ROUND2.read_text(encoding = "utf-8"))
    edited["queries"][0]["query_vi"] += " (edited)"
    edited_path = tmp_path / "round2-v1.json"
    edited_path.write_text(json.dumps(edited, ensure_ascii = False), encoding = "utf-8")
    with pytest.raises(ValueError, match = "different source") :
        import_seed(conn, edited_path)


def test_round1_declared_sha256_is_used_verbatim(conn) :
    import_seed(conn, ROUND1)
    stored = conn.execute(
        "SELECT source_sha256 FROM evaluation_datasets WHERE version = 'round1-v2'"
    ).fetchone()["source_sha256"]
    declared = json.loads(ROUND1.read_text(encoding = "utf-8"))["dataset"]["source"]["sha256"]
    assert stored == declared


def test_reject_schema_version_1(conn, tmp_path) :
    bad = tmp_path / "old.json"
    bad.write_text(json.dumps({"schema_version" : 1, "dataset" : {}, "queries" : []}), encoding = "utf-8")
    with pytest.raises(ValueError, match = "schema_version") :
        import_seed(conn, bad)


# filter_terms is descriptive metadata for the calibration/filter-extraction
# work -- seed.py's importer never reads it, so nothing here touches the DB.
# round2-v2 and round3-v2 use the newer grouped {concept, terms} shape;
# round1-v3 was deliberately left on its original flat string-list shape
# (asr_terms/ocr_terms as plain list[str]) rather than migrated, since
# retrofitting "concept" labels onto already-authored round1 terms would mean
# inventing groupings nobody actually made -- see CLAUDE.md and the round1-v3
# entries themselves for the flat format still in use there.
def test_filter_terms_use_grouped_schema_in_round2_and_round3() :
    for filename in ("round2-v2.json", "round3-v2.json") :
        data = json.loads((SEEDS_DIR / filename).read_text(encoding = "utf-8"))
        for query in data["queries"] :
            ft = query.get("filter_terms")
            assert ft is not None, f"{filename}:{query['id']} missing filter_terms"
            assert ft["confidence"] in ("none", "low", "medium", "high")
            groups = ft["asr_terms"] + ft["ocr_terms"]
            for group in groups :
                assert isinstance(group["concept"], str) and group["concept"]
                assert isinstance(group["terms"], list) and len(group["terms"]) > 0
                assert all(isinstance(term, str) and term for term in group["terms"])
            if ft["confidence"] != "none" :
                assert groups, f"{filename}:{query['id']} has confidence={ft['confidence']!r} but no asr/ocr term groups"


def test_filter_terms_round1_keeps_the_original_flat_schema() :
    """Documents the deliberate divergence: round1-v3 was not migrated to the
    grouped schema (see test above), so its filter_terms.asr_terms/ocr_terms
    are still plain list[str], not list[{"concept", "terms"}]."""
    data = json.loads((SEEDS_DIR / "round1-v3.json").read_text(encoding = "utf-8"))
    for query in data["queries"] :
        ft = query.get("filter_terms")
        assert ft is not None, f"round1-v3.json:{query['id']} missing filter_terms"
        for term in ft["asr_terms"] + ft["ocr_terms"] :
            assert isinstance(term, str)
