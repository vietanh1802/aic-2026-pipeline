from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from app import translation
from app.db.migrations import apply_steps
from app.evaluation.repository import create_run, get_run
from app.evaluation.runner import process_run
from app.evaluation.seed import import_seed


class _FakeResponse :
    def __init__(self, payload) :
        self.payload = payload

    def __enter__(self) :
        return self

    def __exit__(self, exc_type, exc, tb) :
        return False

    def read(self) -> bytes :
        return json.dumps(self.payload).encode("utf-8")


def _conn(path : Path) -> sqlite3.Connection :
    conn = sqlite3.connect(path, isolation_level = None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("CREATE TABLE IF NOT EXISTS packs (id INTEGER PRIMARY KEY)")
    apply_steps(conn)
    return conn


def _setup_run(path : Path, policy : str) -> int :
    conn = _conn(path)
    try :
        import_seed(conn)
        run = create_run(
            conn,
            "round1-v1",
            "r1-manual-v1",
            created_by_user_id = None,
            translation_policy = policy,
        )
        return int(run["id"])
    finally :
        conn.close()


def _fake_result(query_vi, query_en, reference_video, *, translation_ms) :
    return {
        "frame_results" : [{"video" : reference_video, "frame" : "f1"}],
        "ranked_videos" : [{"rank" : 1, "video_id" : reference_video}],
        "metrics" : {
            "predicted_top1_video" : reference_video,
            "reference_video_rank" : 1,
            "hit_at_1" : True,
            "hit_at_3" : True,
            "hit_at_5" : True,
            "hit_at_10" : True,
            "reciprocal_rank" : 1.0,
            "not_retrieved" : False,
        },
        "timings" : {
            "translation_ms" : translation_ms,
            "retrieval_ms" : 1.0,
            "aggregation_ms" : 1.0,
            "total_ms" : translation_ms + 2.0,
        },
    }


def test_translation_policy_catalog_and_ids() -> None :
    assert translation.DEFAULT_TRANSLATION_POLICY == "visual_faithful"
    assert [item["id"] for item in translation.translation_policy_options()] == [
        "visual_faithful",
        "scene_clauses",
        "retrieval_compact",
        "salience_first",
    ]
    assert translation.translator_id_for_policy("scene_clauses") == (
        "gemini_3_5_flash_lite_vi_en_scene_clauses_v1"
    )


def test_translation_rejects_unknown_policy() -> None :
    try :
        translation.normalize_translation_policy("unknown")
    except ValueError as exc :
        assert "Unknown translation policy" in str(exc)
    else :
        raise AssertionError("Unknown policy was accepted")


def test_gemini_request_uses_selected_policy_and_temperature_zero(monkeypatch) -> None :
    captured = {}

    def fake_urlopen(request, timeout) :
        captured["request"] = request
        captured["timeout"] = timeout
        return _FakeResponse({
            "candidates" : [{
                "content" : {"parts" : [{"text" : "A direct visual description"}]}
            }]
        })

    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(translation.urllib.request, "urlopen", fake_urlopen)

    translated, elapsed_ms = translation.translate_vi_to_en(
        "Cảnh quay bắt đầu bằng một người phụ nữ áo đỏ.",
        policy = "retrieval_compact",
    )

    payload = json.loads(captured["request"].data.decode("utf-8"))
    prompt = payload["contents"][0]["parts"][0]["text"]
    assert translated == "A direct visual description"
    assert elapsed_ms >= 0.0
    assert captured["timeout"] == 10.0
    assert payload["generationConfig"]["temperature"] == 0.0
    assert "compact English visual-search description" in prompt
    assert prompt.endswith("Cảnh quay bắt đầu bằng một người phụ nữ áo đỏ.")


def test_run_persists_policy_and_policy_specific_translator(tmp_path : Path) -> None :
    path = tmp_path / "policy.db"
    run_id = _setup_run(path, "salience_first")
    conn = _conn(path)
    try :
        run = get_run(conn, run_id)
        assert run is not None
        assert run["configuration"]["translation_policy"] == "salience_first"
        assert run["translator"] == "gemini_3_5_flash_lite_vi_en_salience_first_v1"
    finally :
        conn.close()


def test_runner_uses_policy_frozen_on_run(monkeypatch, tmp_path : Path) -> None :
    path = tmp_path / "runner-policy.db"
    run_id = _setup_run(path, "scene_clauses")
    seen = []

    def fake_translate(text, *, policy = None) :
        seen.append(policy)
        return "translated", 1.0

    monkeypatch.setattr("app.evaluation.runner.translate_vi_to_en", fake_translate)
    process_run(
        run_id,
        conn_factory = lambda : _conn(path),
        evaluate_fn = _fake_result,
        runtime_snapshot_fn = lambda : {},
    )

    assert seen
    assert set(seen) == {"scene_clauses"}
