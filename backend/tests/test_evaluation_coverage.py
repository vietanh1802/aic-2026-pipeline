# backend/tests/test_evaluation_coverage.py
"""coverage.py reads private preprocess globals. A missing one for a loaded model must raise, naming it."""
from __future__ import annotations

import pytest

from app import preprocess
from app.evaluation import coverage


@pytest.fixture()
def tiny_index(monkeypatch) :
    class Index :
        ntotal = 2

    frames = [{"name" : "L01_V001-0-1.jpg", "video" : "L01_V001"}, {"name" : "M01_V001-0-1.jpg", "video" : "M01_V001"}]
    mapping = {"0" : "images/L01_V001-0-1.jpg", "1" : "images/M01_V001-0-1.jpg"}
    monkeypatch.setattr(preprocess, "_name2meta", {f["name"] : f for f in frames})
    monkeypatch.setattr(preprocess, "_video_frames", {"L01_V001" : frames[ : 1], "M01_V001" : frames[1 : ]})
    for model in ("beit3", "clip", "siglip2") :
        monkeypatch.setattr(preprocess, f"_{model}_index", Index())
        monkeypatch.setattr(preprocess, f"_{model}_map", dict(mapping))
    monkeypatch.setattr(preprocess, "ACTIVE_MODELS", ("beit3", "clip", "siglip2"))


def test_index_coverage_counts_a_fully_covered_tiny_index(tiny_index) :
    result = coverage.index_coverage()
    assert result["metadata_frames"] == 2
    for model in ("beit3", "clip", "siglip2") :
        assert result["models"][model]["ntotal"] == 2
        assert result["models"][model]["mapped"] == 2
        assert result["models"][model]["in_metadata"] == 2
        assert result["models"][model]["by_prefix"] == {"L" : {"frames" : 1, "covered" : 1}, "M" : {"frames" : 1, "covered" : 1}}
    assert coverage.loaded_models() == ["beit3", "clip", "siglip2"]


def test_a_renamed_global_of_a_loaded_model_raises_and_names_the_attribute(tiny_index, monkeypatch) :
    monkeypatch.delattr(preprocess, "_clip_map")
    with pytest.raises(AttributeError, match = "_clip_map") :
        coverage.index_coverage()
    with pytest.raises(AttributeError, match = "_clip_map") :
        coverage.video_coverage("L01_V001")


def test_a_missing_metadata_global_raises_instead_of_reporting_zero_frames(tiny_index, monkeypatch) :
    monkeypatch.delattr(preprocess, "_name2meta")
    with pytest.raises(AttributeError, match = "_name2meta") :
        coverage.index_coverage()


def test_a_model_excluded_by_aic_models_may_be_absent(tiny_index, monkeypatch) :
    monkeypatch.setattr(preprocess, "ACTIVE_MODELS", ("beit3", "siglip2"))
    monkeypatch.delattr(preprocess, "_clip_index")
    monkeypatch.delattr(preprocess, "_clip_map")
    result = coverage.index_coverage()
    assert result["models"]["clip"]["loaded"] is False
    assert result["models"]["clip"]["ntotal"] == 0
    assert result["models"]["beit3"]["loaded"] is True
    assert coverage.loaded_models() == ["beit3", "siglip2"]
