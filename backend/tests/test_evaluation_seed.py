from __future__ import annotations

import json

import pytest

from app.evaluation.seed import SEEDS_DIR, import_all_seeds, import_seed

ROUND1 = SEEDS_DIR / "round1-v2.json"
ROUND2 = SEEDS_DIR / "round2-v1.json"
ROUND3 = SEEDS_DIR / "round3-v1.json"

# 25 + 30 + 35. Round 3 is 35 and not 36: question 34 is omitted because the
# team chose the wrong video for it, so its submission cannot serve as a label.
TOTAL_QUERIES = 90


def _count(conn, table : str) -> int :
    return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def test_seed_files_are_present() :
    assert ROUND1.exists()
    assert ROUND2.exists()
    assert ROUND3.exists()


def test_import_all_seeds_registers_every_round(conn) :
    results = import_all_seeds(conn)
    versions = {result["dataset_version"] for result in results}
    assert versions == {"round1-v2", "round2-v1", "round3-v1"}

    assert _count(conn, "evaluation_datasets") == 3
    assert _count(conn, "evaluation_queries") == TOTAL_QUERIES
    assert _count(conn, "evaluation_reference_sets") == 3
    assert _count(conn, "evaluation_references") == TOTAL_QUERIES


def test_import_is_idempotent(conn) :
    first = import_all_seeds(conn)
    second = import_all_seeds(conn)
    assert [r["query_count"] for r in first] == [r["query_count"] for r in second]
    assert _count(conn, "evaluation_datasets") == 3
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
    assert counts[("round1-v2", "KIS")] == 20
    assert counts[("round1-v2", "QA")] == 4
    assert counts[("round1-v2", "TRAKE")] == 1
    assert counts[("round2-v1", "KIS")] == 19
    assert counts[("round2-v1", "QA")] == 9
    assert counts[("round2-v1", "TRAKE")] == 2
    assert counts[("round3-v1", "KIS")] == 26
    assert counts[("round3-v1", "QA")] == 8
    assert counts[("round3-v1", "TRAKE")] == 1


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
