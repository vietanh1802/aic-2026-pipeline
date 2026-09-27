"""Lọc kết quả tìm theo nhóm video (main._clean_groups / main._keep_groups)."""

import pytest
from fastapi import HTTPException

from app.main import EnsembleSearchRequest, SingleSearchRequest, _clean_groups, _keep_groups


def _hit(name, video=None):
    return {"name": name, "video": video if video is not None else name.rsplit("-", 2)[0]}


def test_clean_groups_normalises_and_rejects_unknown():
    assert _clean_groups(None) == ()
    assert _clean_groups([]) == ()
    assert _clean_groups([" n ", "N", "m"]) == ("M", "N")
    with pytest.raises(HTTPException) as err:
        _clean_groups(["N", "X"])
    assert err.value.status_code == 400


def test_keep_groups_keeps_rank_order_and_cuts_to_limit():
    pool = [
        _hit("L21_V001-0000-3.jpg"),
        _hit("N001-V001-0000-24.jpg"),
        _hit("M05_V019-0193-15697.jpg"),
        _hit("N091-V003-0000-9.jpg"),
        _hit("S01-V001-0000-3.jpg"),
        _hit("N016-V005-0000-2220.jpg"),
    ]
    got = _keep_groups(pool, ("N",), 2)
    assert [h["name"] for h in got] == ["N001-V001-0000-24.jpg", "N091-V003-0000-9.jpg"]
    assert [h["name"] for h in _keep_groups(pool, ("M", "S"), 10)] == [
        "M05_V019-0193-15697.jpg", "S01-V001-0000-3.jpg"]


def test_keep_groups_falls_back_to_the_name_when_video_is_missing():
    assert len(_keep_groups([_hit("N001-V001-0000-24.jpg", video="")], ("N",), 5)) == 1


def test_requests_default_to_every_video():
    # Client cũ không gửi field này: phải giữ nguyên hành vi cũ.
    assert EnsembleSearchRequest(query="x").video_groups is None
    assert SingleSearchRequest(query="x", video_groups=["N"]).video_groups == ["N"]
