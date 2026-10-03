# backend/tests/test_evaluation_suite_api.py
"""The suite endpoints through the FastAPI test client: create, poll to completion, cancel, resume.

Search and the text cache are stubbed (no index, no network), the real worker thread executes the
runs. The stub blocks inside the first query until released, which makes the cancel deterministic.
"""
from __future__ import annotations

import threading
import time

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.auth.deps import require_admin
from app.db.connection import utcnow_iso
from app.evaluation import shared_search, text_cache
from app.evaluation.seed import SEEDS_DIR, import_seed
from app.routers import evaluation as evaluation_router

BASE = "/api/admin/evaluation"
CONFIGS = [
    {"name" : "A clip only", "models" : ["clip"], "subset" : {"limit_queries" : 2}},
    {"name" : "B beit3 only", "models" : ["beit3"], "subset" : {"limit_queries" : 2}},
]


def _poll(client : TestClient, suite_id : str, until, timeout : float = 30.0) -> dict :
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline :
        body = client.get(f"{BASE}/suites/{suite_id}").json()
        if (until(body)) :
            return body
        time.sleep(0.05)
    raise AssertionError(f"suite did not reach the expected state: {body['suite']}")


def test_suite_runs_to_completion_then_cancel_and_resume(conn, monkeypatch) :
    cursor = conn.execute(
        "INSERT INTO users (username, display_name, role, password_hash, "
        "must_change_password, disabled, created_at) VALUES ('admin', 'admin', 'admin', 'x', 0, 0, ?)",
        (utcnow_iso(),),
    )
    admin = conn.execute("SELECT * FROM users WHERE id = ?", (cursor.lastrowid,)).fetchone()
    import_seed(conn, SEEDS_DIR / "round1-v3.json")
    for row in text_cache.query_rows(conn, "round1-v3") :
        text_cache.store(conn, text_cache.make_key("translate_gtx", row["query_vi"]), row["query_vi"], {"text" : "EN"}, "google_gtx")

    release = threading.Event()

    def stub_search(text, models, top_k, top_m, rerank_mode) :
        release.wait(timeout = 10)
        return [{"video" : "L21_V001", "name" : "L21_V001-0001-1.jpg", "frame_idx" : 1, "distance" : 1.0}]

    monkeypatch.setattr(shared_search, "search", stub_search)

    app = FastAPI()
    app.include_router(evaluation_router.router)
    app.dependency_overrides[require_admin] = lambda : admin
    client = TestClient(app)

    created = client.post(f"{BASE}/suites", json = {"name" : "t", "configs" : CONFIGS, "datasets" : ["round1-v3"]})
    assert created.status_code == 202
    suite_id = created.json()["suite"]["suite_id"]
    assert len(created.json()["suite"]["run_ids"]) == 2
    assert client.post(f"{BASE}/suites", json = {"configs" : CONFIGS, "datasets" : ["round1-v3"]}).status_code == 409

    # The first run is inside its first query, blocked in the stub: cancel now.
    _poll(client, suite_id, lambda b : any(r["status"] == "running" for r in b["runs"]))
    cancelled = client.post(f"{BASE}/suites/{suite_id}/cancel")
    assert cancelled.status_code == 200 and cancelled.json()["cancelled"] == 2
    release.set()
    body = _poll(client, suite_id, lambda b : b["suite"]["finished"])
    assert body["suite"]["by_status"] == {"cancelled" : 2}

    # Resume puts both runs back and the worker finishes them; the stub no longer blocks.
    resumed = client.post(f"{BASE}/suites/{suite_id}/resume")
    assert resumed.status_code == 202 and len(resumed.json()["resumed"]) == 2
    body = _poll(client, suite_id, lambda b : b["suite"]["finished"])
    assert body["suite"]["by_status"] == {"completed" : 2}
    assert [r["completed_count"] for r in body["runs"]] == [2, 2]
    assert body["suite"]["queries_done"] == 4
    assert client.get(f"{BASE}/suites/nope").status_code == 404
