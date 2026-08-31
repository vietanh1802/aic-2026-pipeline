from __future__ import annotations

import json
from urllib.parse import parse_qs, urlparse

from app import translation


class _FakeResponse :
    def __init__(self, payload) :
        self.payload = payload

    def __enter__(self) :
        return self

    def __exit__(self, exc_type, exc, tb) :
        return False

    def read(self) -> bytes :
        return json.dumps(self.payload).encode("utf-8")


def test_translate_vi_to_en_matches_current_frontend_google_request(monkeypatch) -> None :
    captured = {}

    def fake_urlopen(url, timeout) :
        captured["url"] = url
        captured["timeout"] = timeout
        return _FakeResponse([[ ["A woman teaching English", "x"] ]])

    monkeypatch.setattr(translation, "urlopen", fake_urlopen)

    translated, elapsed_ms = translation.translate_vi_to_en("Người phụ nữ dạy tiếng Anh")
    params = parse_qs(urlparse(captured["url"]).query)

    assert translated == "A woman teaching English"
    assert elapsed_ms >= 0.0
    assert captured["timeout"] == 10.0
    assert params["client"] == ["gtx"]
    assert params["sl"] == ["auto"]
    assert params["tl"] == ["en"]
    assert params["dt"] == ["t"]
    assert params["q"] == ["Người phụ nữ dạy tiếng Anh"]
