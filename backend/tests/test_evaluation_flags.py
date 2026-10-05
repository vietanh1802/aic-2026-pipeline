# backend/tests/test_evaluation_flags.py
"""The label flags only fire when the id spelling in the flag file equals the spelling of the reference
video in the seeds, which in turn is the spelling of the real keyframe metadata (L and M use an
underscore after the video number, N and S use a hyphen; see frontend/src/helpers/frameRef.ts)."""
from __future__ import annotations

import json
import re

from app.evaluation.flags import _load, flags_for
from app.evaluation.seed import SEEDS_DIR

N_ID = re.compile(r"^N\d{3}-V\d{3}$")


def _reference_videos(dataset : str) -> dict[str, str] :
    seed = json.loads((SEEDS_DIR / f"{dataset}.json").read_text(encoding = "utf-8"))
    return {q["id"] : q["reference"]["video_id"] for q in seed["queries"]}


def test_every_vfr_video_id_uses_the_hyphen_spelling_of_the_n_batch() :
    by_video, _ = _load()
    assert len(by_video["vfr_times"]) == 49
    assert all(N_ID.match(v) for v in by_video["vfr_times"])


def test_n_reference_videos_of_the_seeds_have_the_same_spelling_as_the_flag_file() :
    """If a final-v2 N reference video were listed in the flag file it would fire; the spelling cannot hide it."""
    by_video, _ = _load()
    for dataset in ("round1-v3", "round2-v2", "round3-v2", "final-v2") :
        for key, video in _reference_videos(dataset).items() :
            if (video.startswith("N")) :
                assert N_ID.match(video), (dataset, key, video)
    listed = sorted(by_video["vfr_times"])[0]
    assert flags_for("final-v2", "any-key", listed) == ["vfr_times"]
    assert flags_for("final-v2", "any-key", listed.replace("-", "_")) == []   # an underscore spelling would not match


def test_flags_carried_by_the_seeds_today() :
    """Pins the counts the docs state: no vfr_times query in any dataset, one whole_video_interval query in the final (final-v2)."""
    fired = {}
    for dataset in ("round1-v3", "round2-v2", "round3-v2", "final-v2") :
        for key, video in _reference_videos(dataset).items() :
            for flag in flags_for(dataset, key, video) :
                fired.setdefault((dataset, flag), []).append(key)
    assert fired == {("final-v2", "whole_video_interval") : ["f2-qa-03"]}
