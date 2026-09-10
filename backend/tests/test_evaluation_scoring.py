from __future__ import annotations

from app.evaluation.scoring import (
    R_AT_CUTS,
    collapse_visual_results,
    rank_visual_videos,
    score_frame_intervals,
    score_video_ranking,
    summarize_run,
)


def _frame(video : str, frame_idx : int | None) -> dict :
    return {"video" : video, "frame_idx" : frame_idx}


# ─── video-level ────────────────────────────────────────────────────────────

def test_collapse_keeps_first_occurrence_order() :
    frames = [
        _frame("A", 1), _frame("A", 2), _frame("B", 3),
        _frame("C", 4), _frame("B", 5),
    ]
    ranked = collapse_visual_results(frames)
    assert [video["video_id"] for video in ranked] == ["A", "B", "C"]
    assert [video["rank"] for video in ranked] == [1, 2, 3]
    assert ranked[0]["best_frame_rank"] == 1
    assert ranked[1]["best_frame_rank"] == 3


def test_collapse_caps_frames_per_video() :
    frames = [_frame("A", index) for index in range(10)]
    ranked = collapse_visual_results(frames, max_frames_per_video = 3)
    assert len(ranked) == 1
    assert len(ranked[0]["frames"]) == 3


def test_score_video_ranking_rank_one_three_and_missing() :
    ranked = [
        {"rank" : 1, "video_id" : "A"},
        {"rank" : 2, "video_id" : "B"},
        {"rank" : 3, "video_id" : "C"},
    ]

    at_one = score_video_ranking(ranked, "A")
    assert at_one["hit_at_1"] is True
    assert at_one["reciprocal_rank"] == 1.0

    at_three = score_video_ranking(ranked, "C")
    assert at_three["hit_at_1"] is False
    assert at_three["hit_at_3"] is True
    assert at_three["reference_video_rank"] == 3
    assert at_three["reciprocal_rank"] == 1 / 3

    missing = score_video_ranking(ranked, "Z")
    assert missing["reference_video_rank"] is None
    assert missing["not_retrieved"] is True
    assert missing["reciprocal_rank"] == 0.0
    assert missing["hit_at_10"] is False


# ─── interval-level R-Score ─────────────────────────────────────────────────

def test_interval_hit_at_first_rank() :
    frames = [_frame("L30_V046", 6700), _frame("OTHER", 10)]
    result = score_frame_intervals(frames, "L30_V046", [{"start" : 6613, "end" : 6859}])
    assert result["interval_hit"] is True
    assert result["interval_rank"] == 1
    assert result["matched_interval_index"] == 0
    assert result["final_score"] == 1.0
    assert result["r_at"] == {cut : 1 for cut in R_AT_CUTS}


def test_interval_miss_when_video_right_frame_outside() :
    frames = [_frame("L30_V046", 500)]
    result = score_frame_intervals(frames, "L30_V046", [{"start" : 6613, "end" : 6859}])
    assert result["interval_hit"] is False
    assert result["interval_rank"] is None
    assert result["final_score"] == 0.0


def test_interval_miss_when_wrong_video_inside_range() :
    frames = [_frame("WRONG", 6700)]
    result = score_frame_intervals(frames, "L30_V046", [{"start" : 6613, "end" : 6859}])
    assert result["interval_hit"] is False


def test_interval_boundaries_are_inclusive() :
    intervals = [{"start" : 100, "end" : 200}]
    assert score_frame_intervals([_frame("V", 100)], "V", intervals)["interval_hit"] is True
    assert score_frame_intervals([_frame("V", 200)], "V", intervals)["interval_hit"] is True
    assert score_frame_intervals([_frame("V", 99)], "V", intervals)["interval_hit"] is False
    assert score_frame_intervals([_frame("V", 201)], "V", intervals)["interval_hit"] is False


def test_interval_multi_interval_reports_which_matched() :
    intervals = [
        {"start" : 26060, "end" : 26165},
        {"start" : 26246, "end" : 26330},
    ]
    frames = [_frame("V", 30000), _frame("V", 26300)]
    result = score_frame_intervals(frames, "V", intervals)
    assert result["interval_rank"] == 2
    assert result["matched_interval_index"] == 1


def test_r_at_k_derives_from_interval_rank() :
    # first correct-in-interval frame at rank 4: R@1 = 0, the rest 1
    frames = [_frame("X", 0)] * 3 + [_frame("V", 150)]
    result = score_frame_intervals(frames, "V", [{"start" : 100, "end" : 200}])
    assert result["interval_rank"] == 4
    assert result["r_at"] == {1 : 0, 5 : 1, 20 : 1, 50 : 1, 100 : 1}
    assert result["final_score"] == 4 / 5


def test_frame_without_index_cannot_be_an_interval_hit() :
    frames = [_frame("V", None), _frame("V", 150)]
    result = score_frame_intervals(frames, "V", [{"start" : 100, "end" : 200}])
    assert result["interval_rank"] == 2


def test_trake_is_not_interval_scored() :
    result = score_frame_intervals([_frame("V", 150)], "V", None)
    assert result["interval_hit"] is None
    assert result["interval_rank"] is None
    assert result["final_score"] is None
    assert result["r_at"] == {cut : None for cut in R_AT_CUTS}


# ─── run summary ───────────────────────────────────────────────────────────

def _result(task_type : str, *, status : str = "completed", rank : int | None = 1,
            interval_rank : int | None = 1, total_ms : float = 1000.0) -> dict :
    r_at = {cut : (1 if interval_rank is not None and interval_rank <= cut else 0)
            for cut in R_AT_CUTS}
    return {
        "task_type"            : task_type,
        "status"               : status,
        "reference_video_rank" : rank,
        "hit_at_1"             : rank == 1,
        "hit_at_3"             : rank is not None and rank <= 3,
        "hit_at_5"             : rank is not None and rank <= 5,
        "hit_at_10"            : rank is not None and rank <= 10,
        "reciprocal_rank"      : 1.0 / rank if rank else 0.0,
        "not_retrieved"        : rank is None,
        "interval_hit"         : None if task_type == "TRAKE" else interval_rank is not None,
        "interval_rank"        : None if task_type == "TRAKE" else interval_rank,
        "final_score"          : None if task_type == "TRAKE" else sum(r_at.values()) / len(R_AT_CUTS),
        "total_ms"             : total_ms,
    }


def test_summarize_run_reports_two_final_scores() :
    results = (
        [_result("KIS", interval_rank = 1)] * 2          # KIS: final 1.0 each
        + [_result("QA", interval_rank = None)]          # QA:  final 0.0
        + [_result("TRAKE", rank = 1)]                   # TRAKE: no interval score
    )
    summary = summarize_run(results)
    headline = summary["headline"]

    assert headline["final_score_kis"] == 1.0
    assert headline["final_score_kis_qa"] == 2 / 3
    assert headline["total_queries"] == 4
    assert headline["scored_queries"] == 3
    assert summary["by_task_type"]["TRAKE"]["scoring_tier"] == 0
    assert "interval" not in summary["by_task_type"]["TRAKE"]


def test_summarize_run_counts_failures_as_zero_not_excluded() :
    results = [
        _result("KIS", interval_rank = 1),
        _result("KIS", status = "failed", rank = None, interval_rank = None),
    ]
    headline = summarize_run(results)["headline"]
    # one perfect query, one failed -> Final Score halves, denominator stays 2
    assert headline["final_score_kis"] == 0.5
    assert headline["video"]["hit_at_1"] == 0.5
