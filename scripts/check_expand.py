# scripts/check_expand.py
"""One real Expand call, made the way the suite will make it, before the 145 are fetched.

The core2 preset searches the LLM-prepared English text (expansion.expand_query, Gemini). A key that is present
but invalid, a quota that is used up, or a host that cannot reach Google would otherwise show up only after
minutes of paced calls. This takes ONE query of a seed, calls expand_query(text, task_type) exactly as
text_cache.prefetch does, and prints what came back. It exits non-zero unless the provider is Gemini: no Ollama
or other fallback is acceptable for the paper's baseline, and text_cache refuses such an answer too.

expand_query swallows the Gemini exception and only reports "Gemini unreachable", so on a failure this makes one
more direct call to print the exception type and HTTP status (the key is sent in a header, never printed).

    docker exec $CID python /tmp/ablation/scripts/check_expand.py
    docker exec $CID python /tmp/ablation/scripts/check_expand.py --dataset round3-v2 --index 4
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
# Before any `import app`: the checkout this script lives in must win over an `app` package already in the image.
sys.path.insert(0, str(REPO_ROOT / "backend"))

if hasattr(sys.stdout, "reconfigure") :
    sys.stdout.reconfigure(encoding = "utf-8")

from app import expansion  # noqa: E402
from app.evaluation.seed import SEEDS_DIR  # noqa: E402


def redact(text : str) -> str :
    key = os.getenv("GEMINI_API_KEY") or ""
    return text.replace(key, "<key>") if key else text


def diagnose(text : str, task_type : str) -> None :
    """The cause expand_query hides: one direct Gemini call, with the exception type and HTTP status."""
    key = os.getenv("GEMINI_API_KEY")
    if (not key) :
        print("cause: GEMINI_API_KEY is not set in this process")
        return
    try :
        raw = expansion._call_with_retries(lambda : expansion._gemini_expand(text, task_type, key))
        expansion._parse_expand_json(raw)
        print("cause: the direct Gemini call worked this time (a transient failure); run this check again")
    except Exception as exc :
        body = ""
        if (hasattr(exc, "read")) :
            body = redact(exc.read().decode("utf-8", "replace"))[ : 300]
        print(f"cause: {type(exc).__name__} status {getattr(exc, 'code', None)}: {redact(str(exc))[ : 200]} {body}")


def main() -> int :
    parser = argparse.ArgumentParser(description = __doc__.split("\n")[0])
    parser.add_argument("--dataset", default = "round1-v3", help = "seed file to take the query from")
    parser.add_argument("--index", type = int, default = 0, help = "position of the query in the seed")
    args = parser.parse_args()

    seed = json.loads((SEEDS_DIR / f"{args.dataset}.json").read_text(encoding = "utf-8"))
    query = seed["queries"][args.index]
    task_type = query["task_type"]
    print(f"model {expansion._GEMINI_MODEL}; GEMINI_API_KEY set: {bool(os.getenv('GEMINI_API_KEY'))}; AIC_OLLAMA_URL set: {bool(os.getenv('AIC_OLLAMA_URL'))}")
    print(f"query {query['id']} ({task_type}): {query['query_vi'][ : 80]}")

    # The same call text_cache._fetch_one makes (task type "KIS" only when a row has none).
    result = expansion.expand_query(query["query_vi"], task_type or "KIS")
    provider = result.get("provider")
    eng = result.get("eng_query") or ""
    print(f"provider {provider}, elapsed_ms {result.get('elapsed_ms')}, eng_query words {len(eng.split())}, check_units {len(result.get('check_units') or [])}")
    if (eng) :
        print(f"eng_query: {eng[ : 300]}")
    if (result.get("error")) :
        print(f"error: {result['error']}")
    if (provider != "gemini") :
        print(f"FAIL: the provider is {provider!r}, not 'gemini'; the paper's baseline must not use a fallback")
        diagnose(query["query_vi"], task_type or "KIS")
        return 1
    print("OK: Gemini answered")
    return 0


if (__name__ == "__main__") :
    raise SystemExit(main())
