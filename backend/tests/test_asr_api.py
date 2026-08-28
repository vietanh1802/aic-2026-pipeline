from fastapi.testclient import TestClient

from asr_api import runtime
from asr_api.main import app


client = TestClient(app)


def test_health() :
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"ok" : True}


def test_status(monkeypatch) :
    expected = {
        "enabled"        : True,
        "state"          : "cold",
        "release_id"     : None,
        "release_path"   : "/tmp/release",
        "release_exists" : True,
        "device"         : "cpu",
        "error"          : None,
    }

    monkeypatch.setattr(runtime, "asr_status", lambda : expected)

    response = client.get("/status")

    assert response.status_code == 200
    assert response.json() == expected


def test_search(monkeypatch) :
    captured = {}

    def fake_search_asr(query : str, *, top_k : int, windows_per_hit : int) :
        captured["query"]           = query
        captured["top_k"]           = top_k
        captured["windows_per_hit"] = windows_per_hit

        return {
            "query"      : query,
            "mode"       : "reranked",
            "release_id" : "aic2026-full-20260817-r01",
            "hits"       : [],
            "timings"    : {},
        }

    monkeypatch.setattr(runtime, "search_asr", fake_search_asr)

    response = client.post(
        "/search",
        json = {
            "query"           : "người dẫn chương trình nói về tiền hỗ trợ",
            "limit"           : 5,
            "windows_per_hit" : 2,
        },
    )

    assert response.status_code == 200
    assert captured == {
        "query"           : "người dẫn chương trình nói về tiền hỗ trợ",
        "top_k"           : 5,
        "windows_per_hit" : 2,
    }

    result = response.json()
    assert result["release_id"] == "aic2026-full-20260817-r01"


def test_search_rejects_invalid_limit() :
    response = client.post(
        "/search",
        json = {
            "query"           : "query",
            "limit"           : 0,
            "windows_per_hit" : 2,
        },
    )

    assert response.status_code == 422


def test_search_rejects_empty_query() :
    response = client.post(
        "/search",
        json = {
            "query"           : "",
            "limit"           : 5,
            "windows_per_hit" : 2,
        },
    )

    assert response.status_code == 422


def test_search_returns_503_when_runtime_fails(monkeypatch) :
    def fail_search(*args, **kwargs) :
        raise RuntimeError("model failed")

    monkeypatch.setattr(runtime, "search_asr", fail_search)

    response = client.post(
        "/search",
        json = {
            "query"           : "query",
            "limit"           : 5,
            "windows_per_hit" : 2,
        },
    )

    assert response.status_code == 503
    assert response.json() == {"detail" : "ASR retrieval unavailable"}