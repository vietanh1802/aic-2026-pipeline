from __future__ import annotations

import json
import time
from urllib.parse import urlencode
from urllib.request import urlopen


GOOGLE_TRANSLATE_URL = "https://translate.googleapis.com/translate_a/single"
TRANSLATOR_ID = "google_gtx_vi_en_v1"


def translate_vi_to_en(text : str, timeout_s : float = 10.0) -> tuple[str, float] :
    query = text.strip()
    if (not query) :
        raise ValueError("Translation text must not be empty")

    params = urlencode({
        "client" : "gtx",
        "sl"     : "auto",
        "tl"     : "en",
        "dt"     : "t",
        "q"      : query,
    })
    started = time.monotonic()
    with urlopen(f"{GOOGLE_TRANSLATE_URL}?{params}", timeout = timeout_s) as response :
        data = json.loads(response.read().decode("utf-8"))

    segments = data[0] if isinstance(data, list) and data else []
    translated = "".join(
        str(segment[0]) for segment in segments
        if isinstance(segment, list) and segment and segment[0]
    ).strip()
    if (not translated) :
        raise RuntimeError("Google Translate returned no translated text")

    elapsed_ms = (time.monotonic() - started) * 1000.0
    return translated, elapsed_ms
