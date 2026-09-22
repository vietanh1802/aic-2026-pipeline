# -*- coding: utf-8 -*-
"""
filter_extraction.py — Vietnamese query -> verbatim ASR/OCR filter terms
===========================================================================

One Gemini call that extracts words/phrases a query's target moment would
LITERALLY contain in the ASR transcript (spoken) or OCR text (on screen) --
not a translation, not a description. Feeds the text_signal.py filter
(offline benchmark annotation, and optionally the UI's filter field).

NOT called during normal search -- only when explicitly requested (the
offline annotation script scripts/generate_filter_terms.py, or a future
UI action). Follows expansion.py's Gemini call pattern exactly: same
model, same URL construction, same system_instruction/contents/
generationConfig request shape, same _wait_for_rate_limit/_call_with_retries
pacing from translation.py, same cache shape.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from app.translation import PROVIDER_GEMINI, _call_with_retries, _wait_for_rate_limit

_FILTER_SYSTEM = (
    "You analyze Vietnamese video retrieval queries to extract VERBATIM TEXT TERMS\n"
    "that would appear in the video's speech transcript or on-screen text.\n\n"
    "Your job is NOT to translate or describe the query.\n"
    "Your job is to identify words that would LITERALLY appear in:\n"
    "  (A) the Vietnamese audio transcript (spoken out loud by a narrator or speaker)\n"
    "  (B) text visible on screen as signs, slides, captions, or numbers\n\n"
    "RULES FOR asr_terms (spoken Vietnamese):\n"
    "- Only include if you are CONFIDENT a narrator/speaker says this word.\n"
    "- Must be SPECIFIC enough to discriminate between videos:\n"
    "    GOOD: named places (tỉnh Quảng Nam, đường Hồ Tùng Mậu), dish names\n"
    "          (tôm hùm Cam Ranh, bún gà sào xả), institutions (London Zoo),\n"
    "          fruit/product names (sầu riêng, dâu bòn bon, măng cụt)\n"
    "    BAD: generic words (đầu bếp, nấu ăn, học sinh, giáo viên, xe đạp)\n"
    "- English words spoken in Vietnamese videos: NEVER include.\n"
    "  Whisper ASR garbles English into Vietnamese-sounding fragments.\n"
    "- For TRAKE queries with event sequences: extract terms for each event\n"
    "  if a narrator would announce each event.\n\n"
    "RULES FOR ocr_terms (on-screen text):\n"
    "- Numbers that the query asks about or describes on screen: YES\n"
    "  (37.05, 2018, 13 giây, nhóm 3)\n"
    "- Street signs, institution names, stage text described in query: YES\n"
    "  (SẮC CỔ, đường Hồ Tùng Mậu if shown as a sign)\n"
    "- Exam/slide content described precisely: YES if distinctive\n"
    "  (THPTQG 2018, ĐỀ QG-2018)\n"
    "- Vague descriptions of visual content: NO\n\n"
    "RULES FOR confidence:\n"
    "  'high'   — you are certain at least one term will match\n"
    "  'medium' — one or more terms might match but you are not certain\n"
    "  'none'   — purely visual query, no spoken/text signal expected\n\n"
    "CRITICAL: Return EMPTY lists when unsure. A wrong term is worse than\n"
    "no term. Do NOT invent terms that sound plausible but might not exist\n"
    "in the actual video transcript.\n\n"
    "Return EXACTLY this JSON, nothing else:\n"
    '{"asr_terms": [], "ocr_terms": [], "confidence": "high|medium|none", '
    '"reasoning": "one sentence"}'
)

_GEMINI_MODEL = "gemini-3.5-flash-lite"
_GEMINI_URL = (
    f"https://generativelanguage.googleapis.com/v1beta/models/"
    f"{_GEMINI_MODEL}:generateContent"
)
_TIMEOUT_S = 30.0

_VALID_CONFIDENCE = {"high", "medium", "none"}


@dataclass
class FilterTerms :
    asr_terms : list[str]     # Vietnamese phrases likely spoken near the moment
    ocr_terms : list[str]     # strings likely visible as on-screen text
    confidence : str          # "high" | "medium" | "none"
    reasoning : str           # one sentence from Gemini
    provider : str            # "gemini" | "none"
    elapsed_ms : int
    cached : bool = False


def _clean_terms(raw : Any) -> list[str] :
    if not isinstance(raw, list) :
        return []
    return [str(t).strip() for t in raw if str(t).strip()]


def _parse_filter_json(raw : str) -> FilterTerms :
    """{"asr_terms": [...], "ocr_terms": [...], "confidence": ..., "reasoning": ...}
    from anywhere in `raw`, same tolerant slicing as expansion._parse_expand_json.
    Any missing/invalid field falls back to a safe default rather than raising --
    a wrong term is worse than no term, and a parse hiccup is worse still."""
    start = raw.find("{")
    end = raw.rfind("}")
    if start < 0 or end < start :
        return FilterTerms([], [], "none", "parse error", "gemini", 0)

    try :
        data = json.loads(raw[start : end + 1])
    except json.JSONDecodeError :
        return FilterTerms([], [], "none", "parse error", "gemini", 0)

    if not isinstance(data, dict) :
        return FilterTerms([], [], "none", "parse error", "gemini", 0)

    confidence = str(data.get("confidence") or "").strip().lower()
    if confidence not in _VALID_CONFIDENCE :
        confidence = "none"

    reasoning = str(data.get("reasoning") or "").strip()
    if not reasoning :
        reasoning = "parse error"

    return FilterTerms(
        asr_terms=_clean_terms(data.get("asr_terms")),
        ocr_terms=_clean_terms(data.get("ocr_terms")),
        confidence=confidence,
        reasoning=reasoning,
        provider="gemini",
        elapsed_ms=0,
    )


def _gemini_extract(query_vi : str, task_type : str, api_key : str) -> str :
    _wait_for_rate_limit(PROVIDER_GEMINI)
    payload = {
        "system_instruction" : {"parts" : [{"text" : _FILTER_SYSTEM}]},
        "contents" : [
            {"role" : "user", "parts" : [{"text" : f"[type={task_type}]\n{query_vi}"}]}
        ],
        "generationConfig" : {"temperature" : 0.0},
    }
    request = urllib.request.Request(
        _GEMINI_URL,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type" : "application/json", "x-goog-api-key" : api_key},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=_TIMEOUT_S) as response :
        data = json.loads(response.read().decode("utf-8"))
    candidates = data.get("candidates") if isinstance(data, dict) else None
    if not candidates or not isinstance(candidates[0], dict) :
        raise RuntimeError("Gemini returned no filter-term extraction")
    parts = (candidates[0].get("content") or {}).get("parts")
    if not parts :
        raise RuntimeError("Gemini returned no filter-term extraction")
    text = "".join(
        str(p.get("text") or "") for p in parts if isinstance(p, dict)
    ).strip()
    if not text :
        raise RuntimeError("Gemini returned an empty filter-term extraction")
    return text


# Same shape as expansion.py's _EXPANSION_CACHE: temperature 0 means the same
# (query, task_type) always produces the same output, so caching burns no
# accuracy -- only avoids repeat quota spend when a query is re-annotated.
_FILTER_CACHE : dict[tuple[str, str], FilterTerms] = {}
_CACHE_LIMIT = 512


def extract_filter_terms(query_vi : str, task_type : str = "KIS") -> FilterTerms :
    """Vietnamese query -> FilterTerms. Never raises -- an extraction failure
    (no API key, network error, malformed response) resolves to an empty,
    confidence="none" result rather than propagating an exception, since this
    runs inside an offline annotation loop that must not die on one bad query."""
    started = time.monotonic()
    cache_key = (query_vi, task_type)
    cached = _FILTER_CACHE.get(cache_key)
    if cached is not None :
        return FilterTerms(
            asr_terms=cached.asr_terms, ocr_terms=cached.ocr_terms,
            confidence=cached.confidence, reasoning=cached.reasoning,
            provider=cached.provider, elapsed_ms=0, cached=True,
        )

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key :
        return FilterTerms([], [], "none", "no provider", "none", 0)

    try :
        raw = _call_with_retries(lambda : _gemini_extract(query_vi, task_type, api_key))
        result = _parse_filter_json(raw)
        result.elapsed_ms = int((time.monotonic() - started) * 1000)
    except Exception :
        return FilterTerms([], [], "none", "no provider", "none", 0)

    if len(_FILTER_CACHE) >= _CACHE_LIMIT :
        _FILTER_CACHE.pop(next(iter(_FILTER_CACHE)))
    _FILTER_CACHE[cache_key] = result
    return result
