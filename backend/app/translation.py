import json
import os
import time
import urllib.request


TRANSLATOR_ID = "gemini_3_5_flash_lite_vi_en_v1"

_GEMINI_MODEL = "gemini-3.5-flash-lite"
_GEMINI_URL   = f"https://generativelanguage.googleapis.com/v1beta/models/{_GEMINI_MODEL}:generateContent"


def translate_vi_to_en(text : str) :
    api_key = os.getenv("GEMINI_API_KEY")

    if not api_key :
        raise RuntimeError("GEMINI_API_KEY is not configured")

    prompt = (
        "Translate the following Vietnamese text into English.\n\n"
        "Requirements:\n"
        "- Return only the English translation.\n"
        "- Preserve the original meaning precisely.\n"
        "- Do not explain or add information.\n\n"
        f"Vietnamese:\n{text}"
    )

    payload = {
        "contents" : [
            {
                "parts" : [
                    {"text" : prompt}
                ]
            }
        ]
    }

    request = urllib.request.Request(
        _GEMINI_URL,
        data = json.dumps(payload).encode("utf-8"),
        headers = {
            "Content-Type"   : "application/json",
            "x-goog-api-key" : api_key,
        },
        method = "POST",
    )

    started = time.perf_counter()

    with urllib.request.urlopen(request, timeout = 10) as response :
        body = json.loads(response.read().decode("utf-8"))

    translation_ms = (time.perf_counter() - started) * 1000.0

    try :
        translated = body["candidates"][0]["content"]["parts"][0]["text"].strip()
    except (KeyError, IndexError, TypeError) as error :
        raise RuntimeError("Gemini returned no translation") from error

    if not translated :
        raise RuntimeError("Gemini returned an empty translation")

    return translated, translation_ms