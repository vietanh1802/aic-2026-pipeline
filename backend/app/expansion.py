# -*- coding: utf-8 -*-
"""Query expansion: từ đề bài tiếng Việt tới câu tìm kiếm tiếng Anh đã mở rộng.

Nút "Expand" trên UI (TaskBrief + ô search) gọi đúng một endpoint duy nhất ở
đây. Nó KHÔNG đụng tới BEiT3/CLIP/FAISS — chỉ dịch và suy luận lại câu truy
vấn — nên chạy được kể cả khi các index chưa nạp xong.

Provider chain (đo thật, A/B 91 câu SOTUYEN + 55 câu GT 2025, 2026-09-19):
  1. Gemini flash-lite, MỘT call duy nhất (dịch + mở rộng cùng lúc). Thắng cả
     qwen lẫn gtx-then-rewrite trên hit@1 (92% vs 86%/66%) và nhanh hơn 2.3×
     so với qwen hai bước (1.19s vs 2.74s). Không phụ thuộc gtx — cũng là
     đường sống khi mạng thi bị chặn dịch vụ Google Translate.
  2. Ollama local (AIC_OLLAMA_URL + AIC_OLLAMA_MODEL): hai bước gtx → rewrite,
     đường đo gốc của pipeline lean. Fallback khi Gemini không gọi được —
     chìa khoá để sống sót khi contest chặn API ngoài.

Một lưu ý về provider pacing: Gemini đi qua _wait_for_rate_limit/_call_with_
retries của translation.py — cùng một hàng đợi 4.5s với benchmark, không tự
tạo hàng riêng để đá nhau.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from typing import Any

from app.translation import (
    PROVIDER_GEMINI,
    _call_with_retries,
    _translate_google_gtx,
    _wait_for_rate_limit,
)

# Cùng prompt đã thắng A/B (variant "gem-B"): một call làm cả dịch lẫn mở rộng.
# Quy tắc cứng giữ nguyên từ pipeline lean: không bịa tên/sự kiện, con số và
# màu sắc giữ nguyên văn, chữ trên màn hình giữ nguyên ngữ trong units.
_EXPAND_SYSTEM = (
    "You are given a Vietnamese video-retrieval query. First translate it to English, "
    "then rewrite the translation by ADDING cautious background context if directly "
    "implied (venue types, recency flags, category aliases), and produce English check "
    "units (1-3 words each) that a verifier can use to say yes/no per frame. No invented "
    "names or facts; counts and colors stay exact; on-screen text keeps its own language "
    "in the units list.\n"
    'Return EXACTLY this JSON, nothing else: {"search_query": str, "check_units": [str, ...]}'
)

# Hai bước của nhánh fallback: gtx dịch trước, model local rewrite sau.
_REWRITE_SYSTEM = (
    "You are given a Vietnamese video-retrieval query already translated to English. "
    "Rewrite it by ADDING cautious background context if directly implied (venue types, "
    "recency flags, category aliases), and produce English check units (1-3 words each) "
    "that a verifier can use to say yes/no per frame. No invented names or facts; counts "
    "and colors stay exact; on-screen text keeps its own language in the units list.\n"
    'Return EXACTLY this JSON, nothing else: {"search_query": str, "check_units": [str, ...]}'
)

_GEMINI_MODEL = "gemini-3.5-flash-lite"
_GEMINI_URL = (
    f"https://generativelanguage.googleapis.com/v1beta/models/"
    f"{_GEMINI_MODEL}:generateContent"
)
_TIMEOUT_S = 30.0


def _parse_expand_json(raw : str) -> tuple[str, list[str]] :
    """{"search_query": ..., "check_units": [...]} từ bất kỳ văn bản nào quanh nó.

    Model có lúc mở đầu bằng vài chữ giải thích dù đề bài cấm — cắt tới cặp
    ngoặc cuối cùng thay vì sai cả call vì một chữ thừa.
    """
    start = raw.find("{")
    end = raw.rfind("}")
    if (start < 0 or end < start) :
        raise RuntimeError("expansion response has no JSON object")
    data = json.loads(raw[start : end + 1])
    eng = str(data.get("search_query") or "").strip()
    units_raw = data.get("check_units")
    units = [str(u).strip() for u in units_raw if str(u).strip()] \
        if isinstance(units_raw, list) else []
    if (not eng) :
        raise RuntimeError("expansion response has empty search_query")
    return eng, units


def _gemini_expand(query_text : str, task_type : str, api_key : str) -> str :
    _wait_for_rate_limit(PROVIDER_GEMINI)
    payload = {
        "system_instruction" : {"parts" : [{"text" : _EXPAND_SYSTEM}]},
        "contents" : [
            {"role" : "user", "parts" : [{"text" : f"[type={task_type}]\n{query_text}"}]}
        ],
        "generationConfig" : {"temperature" : 0.0},
    }
    request = urllib.request.Request(
        _GEMINI_URL,
        data = json.dumps(payload, ensure_ascii = False).encode("utf-8"),
        headers = {"Content-Type" : "application/json", "x-goog-api-key" : api_key},
        method = "POST",
    )
    with urllib.request.urlopen(request, timeout = _TIMEOUT_S) as response :
        data = json.loads(response.read().decode("utf-8"))
    candidates = data.get("candidates") if isinstance(data, dict) else None
    if (not candidates or not isinstance(candidates[0], dict)) :
        raise RuntimeError("Gemini returned no expansion")
    parts = (candidates[0].get("content") or {}).get("parts")
    if (not parts) :
        raise RuntimeError("Gemini returned no expansion")
    text = "".join(
        str(p.get("text") or "") for p in parts if isinstance(p, dict)
    ).strip()
    if (not text) :
        raise RuntimeError("Gemini returned an empty expansion")
    return text


def _ollama_generate(prompt : str, system : str, model : str, base_url : str) -> str :
    """Một call tới Ollama local. num_ctx 8192: mọi call của pipeline lean đều
    dùng đúng con số này — đổi số là runner restart giữa chừng, mất cả phút."""
    body = {
        "model" : model,
        "system" : system,
        "prompt" : prompt,
        "stream" : False,
        "think" : False,
        "options" : {"temperature" : 0.0, "num_ctx" : 8192},
    }
    request = urllib.request.Request(
        base_url.rstrip("/") + "/api/generate",
        data = json.dumps(body, ensure_ascii = False).encode("utf-8"),
        headers = {"Content-Type" : "application/json"},
        method = "POST",
    )
    with urllib.request.urlopen(request, timeout = 180) as response :
        data = json.loads(response.read().decode("utf-8"))
    text = str((data or {}).get("response") or "").strip()
    if (not text) :
        raise RuntimeError("Ollama returned an empty response")
    return text


def expand_query(query_text : str, task_type : str = "KIS") -> dict[str, Any] :
    """Đề bài VI → {eng_query, check_units, provider}.

    Gemini trước, Ollama sau. Trả "error" thay vì raise khi cả hai đường cùng
    gục: nút Expand trên UI cần một câu trả lời đọc được, không phải một trang
    500.
    """
    started = time.monotonic()

    def _result(eng : str, units : list[str], provider : str,
                translated : str | None = None) -> dict[str, Any] :
        return {
            "eng_query" : eng,
            "check_units" : units,
            "translated_query" : translated,
            "provider" : provider,
            "elapsed_ms" : int((time.monotonic() - started) * 1000),
        }

    # 1) Gemini one-call
    api_key = os.getenv("GEMINI_API_KEY")
    if (api_key) :
        try :
            raw = _call_with_retries(
                lambda : _gemini_expand(query_text, task_type, api_key)
            )
            eng, units = _parse_expand_json(raw)
            return _result(eng, units, "gemini")
        except Exception :
            pass  # rơi xuống nhánh local — đúng vai trò fallback của nó

    # 2) Ollama hai bước: gtx dịch, model local rewrite
    ollama_url = os.getenv("AIC_OLLAMA_URL")
    if (ollama_url) :
        ollama_model = os.getenv("AIC_OLLAMA_MODEL", "qwen3.8:27b")
        try :
            translated = _call_with_retries(
                lambda : _translate_google_gtx(query_text, _TIMEOUT_S)
            )
            raw = _ollama_generate(
                f"[type={task_type}]\n{translated}", _REWRITE_SYSTEM,
                ollama_model, ollama_url,
            )
            eng, units = _parse_expand_json(raw)
            return _result(eng, units, "ollama", translated)
        except Exception :
            pass

    reason = (
        "GEMINI_API_KEY not set" if not api_key
        else "Gemini unreachable"
    ) + (" and AIC_OLLAMA_URL not set" if not ollama_url else "")
    return {
        **_result("", [], "none"),
        "error" : f"No expansion provider available ({reason})",
    }
