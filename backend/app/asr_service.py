from __future__ import annotations

from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
import json
import os


def _env_bool(name : str, default : bool) -> bool :
    value = os.environ.get(name)
    if (value is None) :
        return default
    return value.strip().lower() not in {"0", "false", "no", "off"}


def _service_url() -> str :
    return os.environ.get(
        "AIC_ASR_SERVICE_URL",
        "http://127.0.0.1:8001",
    ).rstrip("/")


def _timeout_s() -> float :
    timeout = float(os.environ.get("AIC_ASR_SERVICE_TIMEOUT_S", "600"))
    if (timeout <= 0.0) :
        raise ValueError("AIC_ASR_SERVICE_TIMEOUT_S must be positive")
    return timeout


def _request_json(
    method : str,
    path : str,
    payload : dict[str, Any] | None = None,
) -> dict[str, Any] :
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {"Accept" : "application/json"}

    if (body is not None) :
        headers["Content-Type"] = "application/json"

    request = Request(
        f"{_service_url()}{path}",
        data = body,
        headers = headers,
        method = method,
    )

    try :
        with urlopen(request, timeout = _timeout_s()) as response :
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as error :
        detail = error.read().decode("utf-8", errors = "replace").strip()
        raise RuntimeError(
            f"ASR service returned HTTP {error.code}: {detail}"
        ) from error
    except (URLError, TimeoutError) as error :
        raise RuntimeError(f"ASR service unavailable: {error}") from error


def search_asr(
    query : str,
    *,
    top_k : int | None = None,
    windows_per_hit : int | None = None,
) -> dict[str, Any] :
    if (not _env_bool("AIC_ASR_ENABLED", True)) :
        raise RuntimeError("ASR retrieval is disabled")

    payload : dict[str, Any] = {"query" : query}

    if (top_k is not None) :
        top_k = int(top_k)
        if (top_k <= 0) :
            raise ValueError("top_k must be positive")
        payload["limit"] = top_k

    if (windows_per_hit is not None) :
        windows_per_hit = int(windows_per_hit)
        if (windows_per_hit <= 0) :
            raise ValueError("windows_per_hit must be positive")
        payload["windows_per_hit"] = windows_per_hit

    return _request_json("POST", "/search", payload)


def asr_status() -> dict[str, Any] :
    if (not _env_bool("AIC_ASR_ENABLED", True)) :
        return {
            "enabled" : False,
            "state"   : "disabled",
            "error"   : None,
        }

    try :
        return _request_json("GET", "/status")
    except RuntimeError as error :
        return {
            "enabled" : True,
            "state"   : "failed",
            "error"   : str(error),
        }