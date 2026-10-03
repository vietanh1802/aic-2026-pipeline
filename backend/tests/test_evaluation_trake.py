# backend/tests/test_evaluation_trake.py
"""TRAKE-N scoring on a small fixture: video rank always, per-event tolerance when every event is labelled.

Three shortlisted videos in score order: OTHER_1, the reference video, OTHER_2. The reference video's
chain picked frames 100, 205 and 400 for events whose team reference frames are 100, 200 and 800; at 25 fps
a 5 s tolerance is 125 frames, so the first two events are correct and the third is not.
"""
from __future__ import annotations

import pytest

from app.evaluation.config import RunConfig
from app.evaluation.presets import preset_configs
from app.evaluation.trake import evaluate_trake_n, score_trake

REFERENCE = "L10_V001"


def _chain(video : str, frames : list[int]) -> dict :
    return {"video" : video, "combined_score" : 1.0, "events" : [{"name" : f"{video}-{i}.jpg", "frame_idx" : f} for i, f in enumerate(frames)]}


RESULTS = [_chain("OTHER_1", [1, 2, 3]), _chain(REFERENCE, [100, 205, 400]), _chain("OTHER_2", [7, 8, 9])]
LABELLED = [{"event_id" : f"E{i + 1}", "reference_frame_idx" : f} for i, f in enumerate([100, 200, 800])]


def test_video_rank_and_per_event_tolerance() :
    scored = score_trake(RESULTS, REFERENCE, LABELLED, fps = 25.0, tolerance_s = 5.0)
    assert scored["video_metrics"]["reference_video_rank"] == 2
    assert scored["video_metrics"]["hit_at_1"] is False and scored["video_metrics"]["hit_at_3"] is True
    events = scored["events"]
    assert [e["correct"] for e in events["rows"]] == [True, True, False]
    assert events["rows"][1]["error_s"] == 0.2
    assert (events["correct"], events["total"]) == (2, 3)
    assert events["accuracy"] == pytest.approx(2 / 3)


def test_missing_reference_frames_fall_back_to_video_level_and_are_named() :
    unlabelled = [LABELLED[0], {"event_id" : "E2", "reference_frame_idx" : None}, {"event_id" : "E3"}]
    scored = score_trake(RESULTS, REFERENCE, unlabelled, fps = 25.0, tolerance_s = 5.0)
    assert scored["video_metrics"]["reference_video_rank"] == 2
    assert scored["events"] is None and scored["missing_labels"] == ["E2", "E3"]


def test_reference_video_not_shortlisted_scores_zero_and_the_call_uses_production_parameters() :
    seen = {}

    def search(texts, **kwargs) :
        seen.update(kwargs, texts = texts)
        return [_chain("OTHER_1", [1, 2, 3])]

    config = RunConfig(name = "T01", task_mode = "trake_n")
    result = evaluate_trake_n("q", ["a", "b", "c"], REFERENCE, LABELLED, config, search_fn = search, fps_fn = lambda video : 25.0)
    assert result["video_metrics"]["not_retrieved"] is True
    assert result["trake"]["events"]["accuracy"] == 0.0
    # K 20, g 60 s, top_m 50, CLIP: what the UI sends to /trake-search-text.
    assert (seen["top_videos"], seen["gap_c"], seen["top_m"], seen["model_name"]) == (20, 60, 50, "clip")
    assert seen["texts"] == ["a", "b", "c"]
    assert [c.name for c in preset_configs("trake")] == ["T01 TRAKE-N", "T02 TRAKE queries, plain ensemble"]
