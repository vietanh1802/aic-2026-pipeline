from __future__ import annotations

import json
import urllib.error
from typing import Any

import pytest

from app import translation


class _FakeResponse :
    def __init__(self, payload : Any) :
        self.payload = payload

    def __enter__(self) :
        return self

    def __exit__(self, exc_type, exc, tb) :
        return False

    def read(self) -> bytes :
        return json.dumps(self.payload).encode("utf-8")


def _gemini_response(text : str) -> dict :
    return {
        "candidates" : [
            {
                "content" : {
                    "parts" : [
                        {
                            "text" : text,
                        }
                    ]
                }
            }
        ]
    }


def test_translator_id_is_gemini() -> None :
    assert translation.TRANSLATOR_ID == "gemini_3_5_flash_lite_vi_en_v1"


def test_translate_vi_to_en_success(monkeypatch) -> None :
    monkeypatch.setenv("GEMINI_API_KEY", "test-api-key")

    captured = {}

    def fake_urlopen(request, timeout) :
        captured["request"] = request
        captured["timeout"] = timeout

        return _FakeResponse(
            _gemini_response(
                "A woman teaching English"
            )
        )

    monkeypatch.setattr(
        translation.urllib.request,
        "urlopen",
        fake_urlopen,
    )

    translated, elapsed_ms = translation.translate_vi_to_en(
        "Người phụ nữ dạy tiếng Anh"
    )

    assert translated == "A woman teaching English"
    assert elapsed_ms >= 0.0
    assert captured["timeout"] == 10


def test_translate_vi_to_en_sends_correct_gemini_request(monkeypatch) -> None :
    monkeypatch.setenv("GEMINI_API_KEY", "test-api-key")

    captured = {}

    def fake_urlopen(request, timeout) :
        captured["request"] = request
        captured["timeout"] = timeout

        return _FakeResponse(
            _gemini_response(
                "A group of more than five people exercising in a line."
            )
        )

    monkeypatch.setattr(
        translation.urllib.request,
        "urlopen",
        fake_urlopen,
    )

    source_text = (
        "Cảnh quay một nhóm hơn 5 người xếp thành hàng tập thể dục, "
        "cùng thực hiện động tác hai tay chạm mũi chân."
    )

    translation.translate_vi_to_en(source_text)

    request = captured["request"]

    assert request.get_method() == "POST"

    assert request.full_url == (
        "https://generativelanguage.googleapis.com/"
        "v1beta/models/gemini-3.5-flash-lite:generateContent"
    )

    headers = {
        key.lower() : value
        for key, value in request.header_items()
    }

    assert headers["x-goog-api-key"] == "test-api-key"
    assert headers["content-type"] == "application/json"

    body = json.loads(request.data.decode("utf-8"))

    assert "contents" in body
    assert len(body["contents"]) == 1

    prompt = body["contents"][0]["parts"][0]["text"]

    assert source_text in prompt
    assert "Translate the following Vietnamese text into English." in prompt
    assert "Return only the English translation." in prompt
    assert "Preserve the original meaning precisely." in prompt
    assert "Do not explain or add information." in prompt

    assert captured["timeout"] == 10


def test_translate_vi_to_en_preserves_unicode_input(monkeypatch) -> None :
    monkeypatch.setenv("GEMINI_API_KEY", "test-api-key")

    captured = {}

    def fake_urlopen(request, timeout) :
        captured["request"] = request

        return _FakeResponse(
            _gemini_response(
                "A group of people is exercising."
            )
        )

    monkeypatch.setattr(
        translation.urllib.request,
        "urlopen",
        fake_urlopen,
    )

    source_text = "Cảnh quay một nhóm người đang tập thể dục."

    translation.translate_vi_to_en(source_text)

    request = captured["request"]
    body    = json.loads(request.data.decode("utf-8"))
    prompt  = body["contents"][0]["parts"][0]["text"]

    assert source_text in prompt
    assert "Cảnh quay" in prompt


def test_translate_vi_to_en_strips_response_whitespace(monkeypatch) -> None :
    monkeypatch.setenv("GEMINI_API_KEY", "test-api-key")

    def fake_urlopen(request, timeout) :
        return _FakeResponse(
            _gemini_response(
                "\n  A woman teaching English.  \n"
            )
        )

    monkeypatch.setattr(
        translation.urllib.request,
        "urlopen",
        fake_urlopen,
    )

    translated, _ = translation.translate_vi_to_en(
        "Người phụ nữ dạy tiếng Anh"
    )

    assert translated == "A woman teaching English."


def test_translate_vi_to_en_fails_when_api_key_missing(monkeypatch) -> None :
    monkeypatch.delenv(
        "GEMINI_API_KEY",
        raising = False,
    )

    def fake_urlopen(request, timeout) :
        raise AssertionError(
            "Gemini must not be called when GEMINI_API_KEY is missing"
        )

    monkeypatch.setattr(
        translation.urllib.request,
        "urlopen",
        fake_urlopen,
    )

    with pytest.raises(
        RuntimeError,
        match = "GEMINI_API_KEY",
    ) :
        translation.translate_vi_to_en(
            "Người phụ nữ dạy tiếng Anh"
        )


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {
            "candidates" : [],
        },
        {
            "candidates" : [
                {}
            ],
        },
        {
            "candidates" : [
                {
                    "content" : {}
                }
            ],
        },
        {
            "candidates" : [
                {
                    "content" : {
                        "parts" : []
                    }
                }
            ],
        },
    ],
)
def test_translate_vi_to_en_fails_when_response_has_no_translation(
    monkeypatch,
    payload,
) -> None :
    monkeypatch.setenv("GEMINI_API_KEY", "test-api-key")

    def fake_urlopen(request, timeout) :
        return _FakeResponse(payload)

    monkeypatch.setattr(
        translation.urllib.request,
        "urlopen",
        fake_urlopen,
    )

    with pytest.raises(
        RuntimeError,
        match = "Gemini returned no translation",
    ) :
        translation.translate_vi_to_en(
            "Người phụ nữ dạy tiếng Anh"
        )


@pytest.mark.parametrize(
    "translated_text",
    [
        "",
        " ",
        "\n",
        "\t",
        "   \n\t   ",
    ],
)
def test_translate_vi_to_en_fails_when_translation_is_empty(
    monkeypatch,
    translated_text,
) -> None :
    monkeypatch.setenv("GEMINI_API_KEY", "test-api-key")

    def fake_urlopen(request, timeout) :
        return _FakeResponse(
            _gemini_response(translated_text)
        )

    monkeypatch.setattr(
        translation.urllib.request,
        "urlopen",
        fake_urlopen,
    )

    with pytest.raises(
        RuntimeError,
        match = "Gemini returned an empty translation",
    ) :
        translation.translate_vi_to_en(
            "Người phụ nữ dạy tiếng Anh"
        )


def test_translate_vi_to_en_propagates_http_errors(monkeypatch) -> None :
    monkeypatch.setenv("GEMINI_API_KEY", "test-api-key")

    def fake_urlopen(request, timeout) :
        raise urllib.error.HTTPError(
            url = request.full_url,
            code = 429,
            msg = "Too Many Requests",
            hdrs = None,
            fp = None,
        )

    monkeypatch.setattr(
        translation.urllib.request,
        "urlopen",
        fake_urlopen,
    )

    with pytest.raises(urllib.error.HTTPError) as error :
        translation.translate_vi_to_en(
            "Người phụ nữ dạy tiếng Anh"
        )

    assert error.value.code == 429