from app import asr_service


def test_search_asr_calls_service(monkeypatch) :
    captured = {}

    def fake_request(method, path, payload = None) :
        captured["method"]  = method
        captured["path"]    = path
        captured["payload"] = payload
        return {
            "query"      : "query",
            "mode"       : "reranked",
            "release_id" : "aic2026-full-20260817-r01",
            "hits"       : [],
            "timings"    : {},
        }

    monkeypatch.setattr(asr_service, "_request_json", fake_request)

    result = asr_service.search_asr(
        "query",
        top_k = 5,
        windows_per_hit = 2,
    )

    assert captured == {
        "method"  : "POST",
        "path"    : "/search",
        "payload" : {
            "query"           : "query",
            "limit"           : 5,
            "windows_per_hit" : 2,
        },
    }
    assert result["release_id"] == "aic2026-full-20260817-r01"


def test_search_asr_rejects_invalid_limit() :
    try :
        asr_service.search_asr("query", top_k = 0)
    except ValueError as error :
        assert str(error) == "top_k must be positive"
    else :
        raise AssertionError("Expected ValueError")


def test_asr_status_calls_service(monkeypatch) :
    expected = {
        "enabled"        : True,
        "state"          : "ready",
        "release_id"     : "aic2026-full-20260817-r01",
        "release_exists" : True,
        "device"         : "cpu",
        "error"          : None,
    }

    monkeypatch.setattr(
        asr_service,
        "_request_json",
        lambda method, path, payload = None : expected,
    )

    assert asr_service.asr_status() == expected


def test_asr_status_reports_service_failure(monkeypatch) :
    def fail_request(*args, **kwargs) :
        raise RuntimeError("ASR service unavailable")

    monkeypatch.setattr(asr_service, "_request_json", fail_request)

    status = asr_service.asr_status()

    assert status["enabled"] is True
    assert status["state"] == "failed"
    assert "unavailable" in status["error"]