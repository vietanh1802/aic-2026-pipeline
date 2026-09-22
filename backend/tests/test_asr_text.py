import gzip
import json

import pytest

from app import asr_text


@pytest.fixture(autouse=True)
def reset_module_state(monkeypatch) :
    """asr_text's cache is module-level global state, so a load in one test
    would otherwise leak into the next -- give every test a clean slate."""
    monkeypatch.setattr(asr_text, "_asr_text", {})
    monkeypatch.setattr(asr_text, "_loaded", False)
    monkeypatch.setattr(asr_text, "_load_info", {})


FIXTURE = {
    "L21_V001-0000-26.jpg" : "xin chao cac ban",
    "L25_V041-0062-27090.jpg" : "day la bai hoc tieng anh",
    "L26_V389-0103-7644.jpg" : "mon an ngon voi rau",
}


def _write_fixture_gz(path, data : dict) -> None :
    with gzip.open(path, "wt", encoding="utf-8") as f :
        json.dump(data, f, ensure_ascii=False)


def test_get_text_empty_when_not_loaded(tmp_path, monkeypatch) :
    gz_path = tmp_path / "asr_text_index.json.gz"
    _write_fixture_gz(gz_path, FIXTURE)
    monkeypatch.setattr(asr_text, "ASR_TEXT_PATH", str(gz_path))
    # preload() deliberately not called
    assert asr_text.get_text("L21_V001-0000-26.jpg") == ""


def test_get_text_empty_for_unknown_frame(tmp_path, monkeypatch) :
    gz_path = tmp_path / "asr_text_index.json.gz"
    _write_fixture_gz(gz_path, FIXTURE)
    monkeypatch.setattr(asr_text, "ASR_TEXT_PATH", str(gz_path))
    asr_text.preload()
    assert asr_text.get_text("does_not_exist.jpg") == ""


def test_get_text_returns_correct_text_after_loading(tmp_path, monkeypatch) :
    gz_path = tmp_path / "asr_text_index.json.gz"
    _write_fixture_gz(gz_path, FIXTURE)
    monkeypatch.setattr(asr_text, "ASR_TEXT_PATH", str(gz_path))
    asr_text.preload()
    assert asr_text.get_text("L25_V041-0062-27090.jpg") == "day la bai hoc tieng anh"


def test_status_shape_before_and_after_loading(tmp_path, monkeypatch) :
    gz_path = tmp_path / "asr_text_index.json.gz"
    _write_fixture_gz(gz_path, FIXTURE)
    monkeypatch.setattr(asr_text, "ASR_TEXT_PATH", str(gz_path))

    before = asr_text.status()
    assert before == {"ready" : False, "files_present" : True, "file_path" : str(gz_path),
                       "entries_loaded" : 0, "load_seconds" : 0.0}

    asr_text.preload()
    after = asr_text.status()
    assert after["ready"] is True
    assert after["files_present"] is True
    assert after["file_path"] == str(gz_path)
    assert after["entries_loaded"] == len(FIXTURE)
    assert isinstance(after["load_seconds"], float)


def test_preload_is_idempotent(tmp_path, monkeypatch) :
    gz_path = tmp_path / "asr_text_index.json.gz"
    _write_fixture_gz(gz_path, FIXTURE)
    monkeypatch.setattr(asr_text, "ASR_TEXT_PATH", str(gz_path))

    asr_text.preload()
    # Rewrite the file on disk -- if preload() reloaded, entries_loaded/content
    # would change; it must not, because _loaded is already True.
    _write_fixture_gz(gz_path, {**FIXTURE, "extra.jpg" : "should not appear"})
    asr_text.preload()

    assert asr_text.status()["entries_loaded"] == len(FIXTURE)
    assert asr_text.get_text("extra.jpg") == ""


def test_missing_file_handled_gracefully(tmp_path, monkeypatch) :
    monkeypatch.setattr(asr_text, "ASR_TEXT_PATH", str(tmp_path / "does_not_exist.json.gz"))
    asr_text.preload()  # must not raise
    assert asr_text.status()["ready"] is False
    assert asr_text.status()["files_present"] is False
    assert asr_text.get_text("anything.jpg") == ""
