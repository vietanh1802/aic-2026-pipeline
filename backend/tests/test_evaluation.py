from __future__ import annotations

import json
import sqlite3

from app.db.migrations import apply_steps, current_version
from app.evaluation import ensemble as evaluation_ensemble
from app.evaluation.scoring import rank_visual_videos, score_video_ranking
from app.evaluation.seed import ROUND1_SEED_PATH, import_seed


def _fresh_conn() -> sqlite3.Connection :
    conn = sqlite3.connect(":memory:", isolation_level = None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("CREATE TABLE packs (id INTEGER PRIMARY KEY)")
    apply_steps(conn)
    return conn


def test_evaluation_migration_and_seed_are_idempotent() -> None :
    conn = _fresh_conn()
    try :
        assert current_version(conn) == 3
        first = import_seed(conn)
        second = import_seed(conn)

        assert first["query_count"] == 25
        assert second["query_count"] == 25
        assert conn.execute("SELECT COUNT(*) FROM evaluation_datasets").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM evaluation_queries").fetchone()[0] == 25
        assert conn.execute("SELECT COUNT(*) FROM evaluation_reference_sets").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM evaluation_references").fetchone()[0] == 25
    finally :
        conn.close()


def test_round1_seed_preserves_task_counts_and_trake_events() -> None :
    seed = json.loads(ROUND1_SEED_PATH.read_text(encoding = "utf-8"))
    assert seed["dataset"]["task_counts"] == {"KIS" : 20, "QA" : 4, "TRAKE" : 1}

    trake = next(query for query in seed["queries"] if query["id"] == "p1-16")
    assert trake["reference"]["video_id"] == "L24_V024"
    assert trake["reference"]["reference_frame_idx"] is None
    assert [event["reference_frame_idx"] for event in trake["trake_events"]] == [9784, 10128, 10190]


def test_first_frame_occurrence_video_ranking() -> None :
    ranked = rank_visual_videos([
        {"video" : "A", "frame" : "A-1"},
        {"video" : "A", "frame" : "A-2"},
        {"video" : "B", "frame" : "B-1"},
        {"video" : "C", "frame" : "C-1"},
        {"video" : "B", "frame" : "B-2"},
    ])
    assert [candidate["video_id"] for candidate in ranked] == ["A", "B", "C"]
    assert [candidate["rank"] for candidate in ranked] == [1, 2, 3]


def test_video_scoring_rank_one_rank_three_and_missing() -> None :
    ranked = [
        {"rank" : 1, "video_id" : "A"},
        {"rank" : 2, "video_id" : "B"},
        {"rank" : 3, "video_id" : "C"},
    ]

    rank_one = score_video_ranking(ranked, "A")
    assert rank_one["hit_at_1"] is True
    assert rank_one["reciprocal_rank"] == 1.0

    rank_three = score_video_ranking(ranked, "C")
    assert rank_three["hit_at_1"] is False
    assert rank_three["hit_at_3"] is True
    assert rank_three["reference_video_rank"] == 3
    assert rank_three["reciprocal_rank"] == 1 / 3

    missing = score_video_ranking(ranked, "Z")
    assert missing["reference_video_rank"] is None
    assert missing["hit_at_10"] is False
    assert missing["reciprocal_rank"] == 0.0
    assert missing["not_retrieved"] is True


def test_ensemble_evaluation_uses_translation_and_real_ensemble_contract(monkeypatch) -> None :
    monkeypatch.setattr(
        evaluation_ensemble,
        "translate_vi_to_en",
        lambda query : ("translated query", 12.5),
    )

    calls = []

    def fake_ensemble(query, **kwargs) :
        calls.append((query, kwargs))
        return [
            {"video" : "WRONG", "frame" : "wrong-1"},
            {"video" : "TARGET", "frame" : "target-1"},
        ]

    result = evaluation_ensemble.evaluate_ensemble_query(
        "truy vấn",
        "TARGET",
        search_fn = fake_ensemble,
    )

    assert calls == [(
        "translated query",
        {
            "top_k" : 100,
            "top_m" : 50,
            "use_rerank" : True,
            "models" : ["beit3", "clip"],
        },
    )]
    assert result["query_en"] == "translated query"
    assert result["metrics"]["reference_video_rank"] == 2
    assert result["metrics"]["hit_at_3"] is True
