from __future__ import annotations

import pytest

from app.multimodal import collapse_visual_results, fuse_video_rankings, multimodal_search


def test_collapse_visual_results_uses_first_video_occurrence() :
    frames = [
        {"video" : "A", "name" : "A-1", "distance" : 99.0},
        {"video" : "A", "name" : "A-2", "distance" : 98.0},
        {"video" : "B", "name" : "B-1", "distance" : 97.0},
        {"video" : "C", "name" : "C-1", "distance" : 96.0},
        {"video" : "B", "name" : "B-2", "distance" : 95.0},
    ]

    videos = collapse_visual_results(frames, max_frames_per_video = 2)

    assert [video["video_id"] for video in videos] == ["A", "B", "C"]
    assert [video["rank"] for video in videos] == [1, 2, 3]
    assert [frame["name"] for frame in videos[0]["frames"]] == ["A-1", "A-2"]
    assert [frame["name"] for frame in videos[1]["frames"]] == ["B-1", "B-2"]


def test_weighted_rrf_combines_rank_not_raw_scores() :
    visual = [
        {"rank" : 1, "video_id" : "A", "frames" : []},
        {"rank" : 2, "video_id" : "B", "frames" : []},
        {"rank" : 3, "video_id" : "C", "frames" : []},
    ]
    asr = [
        {"rank" : 1, "video_id" : "C", "final_score" : -1000.0, "windows" : []},
        {"rank" : 2, "video_id" : "D", "final_score" : 999999.0, "windows" : []},
        {"rank" : 3, "video_id" : "A", "final_score" : -999999.0, "windows" : []},
    ]

    fused = fuse_video_rankings(
        visual,
        asr,
        visual_weight = 0.5,
        asr_weight = 0.5,
        rrf_k = 60,
        limit = 10,
    )

    assert fused[0]["video_id"] == "A"
    assert fused[1]["video_id"] == "C"
    assert fused[0]["visual"]["rank"] == 1
    assert fused[0]["asr"]["rank"] == 3
    assert fused[1]["asr"]["final_score"] == -1000.0


def test_fusion_preserves_single_modality_candidates() :
    visual = [{"rank" : 1, "video_id" : "A", "frames" : [{"name" : "A-1"}]}]
    asr    = [{"rank" : 1, "video_id" : "B", "windows" : [{"transcript" : "speech"}]}]

    fused = fuse_video_rankings(visual, asr, rrf_k = 60, limit = 10)
    by_video = {candidate["video_id"] : candidate for candidate in fused}

    assert by_video["A"]["visual"] is not None
    assert by_video["A"]["asr"] is None
    assert by_video["B"]["visual"] is None
    assert by_video["B"]["asr"]["windows"][0]["transcript"] == "speech"


def test_multimodal_search_skips_zero_weight_route() :
    calls = {"visual" : 0, "asr" : 0}

    def fake_visual(query, **kwargs) :
        calls["visual"] += 1
        return [{"video" : "A", "name" : "A-1"}]

    def fake_asr(query, **kwargs) :
        calls["asr"] += 1
        return {"hits" : [{"rank" : 1, "video_id" : "B", "windows" : []}]}

    result = multimodal_search(
        "query",
        visual_weight = 1.0,
        asr_weight = 0.0,
        visual_search = fake_visual,
        asr_search = fake_asr,
    )

    assert calls == {"visual" : 1, "asr" : 0}
    assert result["results"][0]["video_id"] == "A"
    assert result["fusion"]["visual_weight"] == 1.0
    assert result["fusion"]["asr_weight"] == 0.0


def test_fusion_ties_are_deterministic() :
    visual = [{"rank" : 1, "video_id" : "B", "frames" : []}]
    asr    = [{"rank" : 1, "video_id" : "A", "windows" : []}]

    first  = fuse_video_rankings(visual, asr, visual_weight = 0.5, asr_weight = 0.5)
    second = fuse_video_rankings(visual, asr, visual_weight = 0.5, asr_weight = 0.5)

    assert [row["video_id"] for row in first] == [row["video_id"] for row in second]


def test_invalid_weights_are_rejected() :
    with pytest.raises(ValueError) :
        fuse_video_rankings([], [], visual_weight = 0.0, asr_weight = 0.0)
