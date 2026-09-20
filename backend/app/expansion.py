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

# Prompt expansion sau khi soi thực tế (2026-09-19): bản đầu chỉ nói "ADD
# cautious background context" nên Gemini chơi an toàn tới mức退化 thành dịch
# — không lọc noise, không làm giàu. Bản này ghép hai quy tắc nhóm đã đúc kết:
# luật CLEAN của policy visual_faithful (translation.py — bỏ wrapper kể chuyện)
# và luật clean 2025 (bỏ tính từ cảm xúc, discriminator đứng trước).
_EXPAND_SYSTEM = (
    "You are preparing a Vietnamese video-retrieval query for a text-to-image search index.\n"
    "Translate it into ONE fluent English search command, then curate it:\n\n"
    "CLEAN — remove what hurts search:\n"
    "- video-narration boilerplate ('the video begins with', 'the clip shows', "
    "'đoạn video về', 'ta thấy', 'hãy tìm chính xác') — state the visual content directly\n"
    "- subjective mood words no camera can match ('rực rỡ', 'ấn tượng', 'yên bình', "
    "'majestic', 'impressive') and storytelling padding\n\n"
    "ENRICH — add what the text directly implies:\n"
    "- name the scene type (cooking tutorial, weather forecast, news report, "
    "school lecture, traffic camera...)\n"
    "- add a common retrieval alias for cultural/regional items "
    "(lân sư rồng → lion dance; múa lân)\n"
    "- add venue/recency flags when implied\n\n"
    "KEEP — the retrieval anchors, exactly:\n"
    "- every countable detail: counts, colors, clothing, positions, actions, "
    "on-screen text (verbatim, keep its own language), camera viewpoint, temporal order\n"
    "- every number, quantity and measurement in the original MUST appear in the output\n"
    "- NEVER invent named entities, brands, numbers or facts\n\n"
    "The search_query is ONE fluent, grammatical sentence (articles and prepositions "
    "included) — never a keyword list.\n"
    "Most discriminative details first; generic context last.\n"
    "Also produce English check units (1-3 words each) that a verifier can use "
    "to say yes/no per frame.\n"
    'Return EXACTLY this JSON, nothing else: {"search_query": str, "check_units": [str, ...]}'
)

# Nhánh fallback hai bước: gtx dịch trước nên wrapper và tính từ cảm xúc còn
# nguyên — nhánh rewrite này phải có đủ luật CLEAN, không chỉ luật ENRICH.
_REWRITE_SYSTEM = (
    "You are given a Vietnamese video-retrieval query already translated to English. "
    "Rewrite it into ONE fluent English search command, curated for retrieval:\n\n"
    "CLEAN — remove video-narration boilerplate ('the video begins with', 'the clip shows', "
    "'đoạn video về', 'ta thấy', 'hãy tìm chính xác') and subjective mood words no camera "
    "can match ('rực rỡ', 'majestic', 'impressive').\n\n"
    "ENRICH — name the scene type if implied (cooking tutorial, weather forecast, news "
    "report, school lecture...), add retrieval aliases for cultural items, add venue/recency "
    "flags when implied.\n\n"
    "KEEP every countable detail exactly: counts, colors, clothing, positions, actions, "
    "on-screen text (verbatim, keep its own language), camera viewpoint, temporal order; "
    "every number MUST appear in the output. "
    "NEVER invent named entities, brands, numbers or facts. Most discriminative details "
    "first. The search_query is ONE fluent, grammatical sentence — never a keyword list.\n"
    "Also produce English check units (1-3 words each) that a verifier can use to say "
    "yes/no per frame.\n"
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


# Cache kết quả expand theo (query_text, task_type). Temperature 0 nên cùng
# đề luôn cho cùng output — cache là bản ghi quota miễn phí: double-click, bấm
# lại trên cùng task, hay đổi máy tab đều không đốt thêm request Gemini.
# Giới hạn 512 mục: đề của một vòng thi là vài chục câu, 512 là dư và vẫn nhỏ.
_EXPANSION_CACHE : dict[tuple[str, str], dict[str, Any]] = {}
_CACHE_LIMIT = 512


def expand_query(query_text : str, task_type : str = "KIS") -> dict[str, Any] :
    """Đề bài VI → {eng_query, check_units, provider}.

    Gemini trước, Ollama sau. Trả "error" thay vì raise khi cả hai đường cùng
    gục: nút Expand trên UI cần một câu trả lời đọc được, không phải một trang
    500.
    """
    started = time.monotonic()

    cache_key = (query_text, task_type)
    cached = _EXPANSION_CACHE.get(cache_key)
    if (cached is not None and "error" not in cached) :
        # Trả bản cache với elapsed_ms reset: thời gian thật của lần này là
        # ~0, không phải thời gian của lần sinh kết quả.
        return {**cached, "cached" : True, "elapsed_ms" : 0}

    def _result(eng : str, units : list[str], provider : str,
                translated : str | None = None) -> dict[str, Any] :
        return {
            "eng_query" : eng,
            "check_units" : units,
            "translated_query" : translated,
            "provider" : provider,
            "elapsed_ms" : int((time.monotonic() - started) * 1000),
        }

    def _remember(result : dict[str, Any]) -> dict[str, Any] :
        if ("error" not in result) :
            if (len(_EXPANSION_CACHE) >= _CACHE_LIMIT) :
                _EXPANSION_CACHE.pop(next(iter(_EXPANSION_CACHE)))
            _EXPANSION_CACHE[cache_key] = result
        return result

    # 1) Gemini one-call
    api_key = os.getenv("GEMINI_API_KEY")
    if (api_key) :
        try :
            raw = _call_with_retries(
                lambda : _gemini_expand(query_text, task_type, api_key)
            )
            eng, units = _parse_expand_json(raw)
            return _remember(_result(eng, units, "gemini"))
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
            return _remember(_result(eng, units, "ollama", translated))
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
