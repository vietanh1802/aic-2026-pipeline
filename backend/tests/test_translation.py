from __future__ import annotations

import io
import json
import urllib.error

import pytest

import app.translation as translation
from app.routers.evaluation import translation_policies
from app.translation import (
    DEFAULT_TRANSLATION_POLICY,
    PROVIDER_GEMINI,
    PROVIDER_GOOGLE_GTX,
    TRANSLATION_POLICIES,
    normalize_translation_policy,
    provider_of_policy,
    translate_vi_to_en,
    translation_policy_options,
    translator_id_for_policy,
)

# literal_v1 was added as a plain baseline after our own experiment found
# visual_faithful scored worst of all tested policies (24% Top-1 / 0.428 MRR
# vs. the plain baseline's 48% Top-1 / 0.542 MRR). literal_visual_v2 is a
# second, non-default option available for selection per run.
EXISTING_FOUR = {"visual_faithful", "scene_clauses", "retrieval_compact", "salience_first"}


def test_default_policy_is_literal_v1() :
    assert DEFAULT_TRANSLATION_POLICY == "literal_v1"


def test_literal_v1_and_literal_visual_v2_are_registered() :
    assert "literal_v1" in TRANSLATION_POLICIES
    assert "literal_visual_v2" in TRANSLATION_POLICIES


def test_existing_four_policies_are_unchanged() :
    assert EXISTING_FOUR <= TRANSLATION_POLICIES.keys()


def test_translation_policy_options_includes_both_new_policies() :
    ids = {option["id"] for option in translation_policy_options()}
    assert {"literal_v1", "literal_visual_v2"} <= ids
    assert EXISTING_FOUR <= ids


def test_translator_id_for_policy_is_distinct_for_new_policies() :
    ids = {translator_id_for_policy(policy) for policy in TRANSLATION_POLICIES}
    assert len(ids) == len(TRANSLATION_POLICIES)


def test_normalize_translation_policy_defaults_to_literal_v1() :
    assert normalize_translation_policy(None) == "literal_v1"


def test_translation_policies_endpoint_default_is_literal_v1() :
    response = translation_policies(None)
    assert response["default"] == "literal_v1"
    ids = {option["id"] for option in response["policies"]}
    assert {"literal_v1", "literal_visual_v2"} <= ids


# google_gtx_v1 mirrors the Search tab's Translate button so a run can measure
# the system the team actually competed with, not just the Gemini variant.
def test_google_policy_is_offered_and_is_not_a_gemini_policy() :
    assert "google_gtx_v1" in TRANSLATION_POLICIES
    assert provider_of_policy("google_gtx_v1") == PROVIDER_GOOGLE_GTX
    assert {option["id"] for option in translation_policy_options()} >= {"google_gtx_v1"}


def test_prompt_policies_stay_on_gemini() :
    for policy in TRANSLATION_POLICIES :
        if (policy == "google_gtx_v1") :
            continue
        assert provider_of_policy(policy) == PROVIDER_GEMINI
        assert translator_id_for_policy(policy).startswith("gemini_3_5_flash_lite_")


def test_google_policy_needs_no_gemini_key_and_joins_segments(monkeypatch) :
    monkeypatch.delenv("GEMINI_API_KEY", raising = False)
    captured : dict[str, str] = {}

    def fake_urlopen(request, timeout = None) :
        captured["url"] = request.full_url
        body = json.dumps([[["A dog runs. ", "Con cho chay. "], ["Then it stops.", "Roi no dung."]]])
        return io.BytesIO(body.encode("utf-8"))

    monkeypatch.setattr(translation.urllib.request, "urlopen", fake_urlopen)
    translated, elapsed_ms = translate_vi_to_en("Con chó chạy. Rồi nó dừng.", policy = "google_gtx_v1")

    assert translated == "A dog runs. Then it stops."
    assert elapsed_ms >= 0.0
    assert "client=gtx" in captured["url"] and "tl=en" in captured["url"]


# ===== Pacing + retry (rate-limit pacing, tiered retry on failures) =====
#
# Runner bắn câu kế tiếp ngay khi câu trước xong, không có gì chặn vượt ngưỡng
# ~15 request/phút miễn phí của Gemini — nên pace trước mỗi lần gọi. Đồng hồ
# giả bên dưới để test không phải chờ thật 4.5s pacing hay vài giây backoff.
class _FakeClock :
    def __init__(self) -> None :
        self.now = 0.0
        self.sleeps : list[float] = []

    def monotonic(self) -> float :
        return self.now

    def sleep(self, seconds : float) -> None :
        self.sleeps.append(seconds)
        self.now += seconds


@pytest.fixture
def fake_clock(monkeypatch) :
    clock = _FakeClock()
    monkeypatch.setattr(translation.time, "monotonic", clock.monotonic)
    monkeypatch.setattr(translation.time, "sleep", clock.sleep)
    # Trạng thái pacing là module-level, phải reset để test này không thấy
    # dấu vết của lần gọi thật (hoặc test khác) chạy trước nó.
    monkeypatch.setattr(translation, "_last_call_started_at", {})
    return clock


def _gemini_body(text : str) -> bytes :
    return json.dumps({"candidates" : [{"content" : {"parts" : [{"text" : text}]}}]}).encode("utf-8")


def _gtx_body(text : str) -> bytes :
    return json.dumps([[[text, "orig"]]]).encode("utf-8")


def _make_flaky_urlopen(*, fail_times : int, exc_factory, success_body : bytes) :
    state = {"calls" : 0}

    def fake_urlopen(request, timeout = None) :
        state["calls"] += 1
        if (state["calls"] <= fail_times) :
            raise exc_factory()
        return io.BytesIO(success_body)

    return fake_urlopen, state


# policy=None -> Gemini (literal_v1); policy="google_gtx_v1" -> Google gtx.
# Cả hai đi qua _call_with_retries dùng chung nên tham số hoá theo provider.
_PROVIDER_CASES = [
    pytest.param(None, _gemini_body("Hello"), id = "gemini"),
    pytest.param("google_gtx_v1", _gtx_body("Hello"), id = "google_gtx"),
]


@pytest.mark.parametrize("policy, success_body", _PROVIDER_CASES)
def test_network_failure_retries_then_succeeds(monkeypatch, fake_clock, policy, success_body) :
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    fake_urlopen, state = _make_flaky_urlopen(
        fail_times = 2, exc_factory = lambda : TimeoutError("timed out"), success_body = success_body
    )
    monkeypatch.setattr(translation.urllib.request, "urlopen", fake_urlopen)

    translated, elapsed_ms = translate_vi_to_en("Xin chao", policy = policy)

    assert translated == "Hello"
    assert state["calls"] == 3
    # 2 lần backoff cố định (2s, 5s) nằm TRONG elapsed vì chúng là thời gian
    # thật của lần gọi đang được đo, khác pacing wait ở trên (bị loại ra).
    assert elapsed_ms == pytest.approx(7000.0)


@pytest.mark.parametrize("policy, success_body", _PROVIDER_CASES)
def test_network_failure_exhausts_retries_and_raises(monkeypatch, fake_clock, policy, success_body) :
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    fake_urlopen, state = _make_flaky_urlopen(
        fail_times = 10, exc_factory = lambda : TimeoutError("timed out"), success_body = success_body
    )
    monkeypatch.setattr(translation.urllib.request, "urlopen", fake_urlopen)

    with pytest.raises(TimeoutError) :
        translate_vi_to_en("Xin chao", policy = policy)

    assert state["calls"] == 3


@pytest.mark.parametrize("policy, success_body", _PROVIDER_CASES)
def test_rate_limit_429_retries_once_then_succeeds(monkeypatch, fake_clock, policy, success_body) :
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    fake_urlopen, state = _make_flaky_urlopen(
        fail_times = 1,
        exc_factory = lambda : urllib.error.HTTPError("url", 429, "Too Many Requests", None, None),
        success_body = success_body,
    )
    monkeypatch.setattr(translation.urllib.request, "urlopen", fake_urlopen)

    translated, elapsed_ms = translate_vi_to_en("Xin chao", policy = policy)

    assert translated == "Hello"
    assert state["calls"] == 2
    assert elapsed_ms > 0.0


@pytest.mark.parametrize("policy, success_body", _PROVIDER_CASES)
def test_rate_limit_429_twice_gives_up_after_single_retry(monkeypatch, fake_clock, policy, success_body) :
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    fake_urlopen, state = _make_flaky_urlopen(
        fail_times = 10,
        exc_factory = lambda : urllib.error.HTTPError("url", 429, "Too Many Requests", None, None),
        success_body = success_body,
    )
    monkeypatch.setattr(translation.urllib.request, "urlopen", fake_urlopen)

    with pytest.raises(urllib.error.HTTPError) as excinfo :
        translate_vi_to_en("Xin chao", policy = policy)

    assert excinfo.value.code == 429
    # 1 lần thử ban đầu + đúng 1 lần thử lại = 2. Ăn 429 lần hai là dừng, không
    # thử thêm.
    assert state["calls"] == 2


@pytest.mark.parametrize("policy, success_body", _PROVIDER_CASES)
def test_non_429_http_error_is_not_retried(monkeypatch, fake_clock, policy, success_body) :
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    fake_urlopen, state = _make_flaky_urlopen(
        fail_times = 10,
        exc_factory = lambda : urllib.error.HTTPError("url", 400, "Bad Request", None, None),
        success_body = success_body,
    )
    monkeypatch.setattr(translation.urllib.request, "urlopen", fake_urlopen)

    with pytest.raises(urllib.error.HTTPError) as excinfo :
        translate_vi_to_en("Xin chao", policy = policy)

    assert excinfo.value.code == 400
    assert state["calls"] == 1


def test_pacing_spaces_same_provider_calls_by_min_interval(monkeypatch, fake_clock) :
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(
        translation.urllib.request, "urlopen", lambda request, timeout = None : io.BytesIO(_gemini_body("Hi"))
    )

    translate_vi_to_en("Cau mot", policy = None)
    started_first = translation._last_call_started_at[PROVIDER_GEMINI]
    translate_vi_to_en("Cau hai", policy = None)
    started_second = translation._last_call_started_at[PROVIDER_GEMINI]

    assert started_second - started_first == pytest.approx(translation._MIN_CALL_INTERVAL_S)


def test_pacing_does_not_cross_providers(monkeypatch, fake_clock) :
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(
        translation.urllib.request,
        "urlopen",
        lambda request, timeout = None : io.BytesIO(
            _gtx_body("Hi") if ("translate_a" in request.full_url) else _gemini_body("Hi")
        ),
    )

    translate_vi_to_en("Cau mot", policy = "google_gtx_v1")
    translate_vi_to_en("Cau hai", policy = None)

    # Hai provider khác nhau, gọi liên tiếp không được chờ nhau.
    assert fake_clock.sleeps == []


def test_pacing_wait_is_excluded_from_reported_elapsed_time(monkeypatch, fake_clock) :
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(
        translation.urllib.request, "urlopen", lambda request, timeout = None : io.BytesIO(_gemini_body("Hi"))
    )

    translate_vi_to_en("Cau mot", policy = None)
    # Lần gọi thứ hai phải chờ pacing ~4.5s, nhưng elapsed_ms trả về không được
    # tính khoảng chờ đó vào — đây là điều dễ làm sai nhất trong toàn bộ fix.
    _, elapsed_ms = translate_vi_to_en("Cau hai", policy = None)

    assert translation._MIN_CALL_INTERVAL_S in fake_clock.sleeps
    assert elapsed_ms == pytest.approx(0.0)
