from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
from pathlib import Path
from threading import Lock
from typing import Any
import os


RELEASE_ID = "aic2026-full-20260817-r01"
REPO_ROOT  = Path(__file__).resolve().parents[2]


@dataclass(frozen = True)
class ASRSettings :
    enabled : bool
    release_path : Path
    device : str
    top_k : int
    windows_per_hit : int
    warmup : bool


def _env_bool(name : str, default : bool) -> bool :
    value = os.environ.get(name)
    if (value is None) :
        return default
    return value.strip().lower() not in {"0", "false", "no", "off"}


def get_asr_settings() -> ASRSettings :
    release_path = Path(
        os.environ.get(
            "AIC_ASR_RELEASE_DIR",
            str(REPO_ROOT / "artifacts" / "asr" / "releases" / RELEASE_ID),
        )
    ).expanduser()
    device = os.environ.get("AIC_ASR_DEVICE", "cpu").strip().lower()
    if (device not in {"cpu", "cuda"}) :
        raise ValueError("AIC_ASR_DEVICE must be 'cpu' or 'cuda'")

    top_k          = int(os.environ.get("AIC_ASR_TOP_K", "50"))
    windows_per_hit = int(os.environ.get("AIC_ASR_WINDOWS_PER_HIT", "3"))
    if (top_k <= 0) :
        raise ValueError("AIC_ASR_TOP_K must be positive")
    if (windows_per_hit <= 0) :
        raise ValueError("AIC_ASR_WINDOWS_PER_HIT must be positive")

    return ASRSettings(
        enabled         = _env_bool("AIC_ASR_ENABLED", True),
        release_path    = release_path,
        device          = device,
        top_k           = top_k,
        windows_per_hit = windows_per_hit,
        warmup          = _env_bool("AIC_ASR_WARMUP", True),
    )


_engine = None
_manifest = None
_state = "cold"
_error : str | None = None
_load_lock = Lock()


def _build_engine(settings : ASRSettings) :
    from asr_retrieval.config import BGEConfig, ProductionConfig, RuntimeConfig
    from asr_retrieval.engine import ASRRetrievalEngine

    runtime = RuntimeConfig(
        e5_device               = settings.device,
        load_reranker           = True,
        serialize_gpu_requests  = True,
        default_top_k           = settings.top_k,
        default_windows_per_hit = settings.windows_per_hit,
    )
    bge = (
        BGEConfig(device = "cpu", dtype = "float32")
        if (settings.device == "cpu")
        else BGEConfig()
    )
    config = ProductionConfig(bge = bge, runtime = runtime)
    engine = ASRRetrievalEngine.from_artifacts(
        settings.release_path,
        config = config,
        warmup = settings.warmup,
    )
    manifest = engine.release.manifest
    if (manifest.release_id != RELEASE_ID) :
        engine.close()
        raise ValueError(
            f"Unexpected ASR release {manifest.release_id!r}; expected {RELEASE_ID!r}"
        )
    return manifest, engine


def get_asr_engine() :
    global _engine, _manifest, _state, _error

    settings = get_asr_settings()
    if (not settings.enabled) :
        _state = "disabled"
        raise RuntimeError("ASR retrieval is disabled")
    if (_engine is not None) :
        return _engine

    with _load_lock :
        if (_engine is not None) :
            return _engine

        _state = "loading"
        _error = None
        try :
            _manifest, _engine = _build_engine(settings)
            _state = "ready"
            return _engine
        except Exception as exc :
            _engine = None
            _manifest = None
            _state = "failed"
            _error = f"{type(exc).__name__}: {exc}"
            raise


def _window_to_dict(window) -> dict[str, Any] :
    return {
        "window_id"         : window.window_id,
        "video_id"          : window.video_id,
        "start_s"           : float(window.start_s),
        "end_s"             : float(window.end_s),
        "transcript"        : window.transcript,
        "first_stage_score" : float(window.first_stage_score),
        "reranker_score"    : None if window.reranker_score is None else float(window.reranker_score),
        "final_score"       : None if window.final_score is None else float(window.final_score),
        "reranked"          : bool(window.reranked),
    }


def _hit_to_dict(hit) -> dict[str, Any] :
    return {
        "rank"              : int(hit.rank),
        "video_id"          : hit.video_id,
        "first_stage_rank"  : int(hit.first_stage_rank),
        "first_stage_score" : float(hit.first_stage_score),
        "reranker_score"    : None if hit.reranker_score is None else float(hit.reranker_score),
        "final_score"       : None if hit.final_score is None else float(hit.final_score),
        "reranked"          : bool(hit.reranked),
        "windows"           : [_window_to_dict(window) for window in hit.windows],
    }


def _to_dict(value) -> dict[str, Any] :
    if (is_dataclass(value)) :
        return asdict(value)
    if (hasattr(value, "__dict__")) :
        return dict(vars(value))
    raise TypeError(f"Cannot serialize {type(value).__name__}")


def search_asr(
    query : str,
    *,
    top_k : int | None = None,
    windows_per_hit : int | None = None,
) -> dict[str, Any] :
    settings = get_asr_settings()
    requested_top_k = settings.top_k if top_k is None else int(top_k)
    requested_windows = settings.windows_per_hit if windows_per_hit is None else int(windows_per_hit)
    if (requested_top_k <= 0) :
        raise ValueError("top_k must be positive")
    if (requested_windows <= 0) :
        raise ValueError("windows_per_hit must be positive")

    engine = get_asr_engine()
    result = engine.search(
        query,
        top_k = requested_top_k,
        first_stage_only = False,
        windows_per_hit = requested_windows,
    )

    # Preserve result.hits exactly in the authoritative engine order.
    return {
        "query"      : result.query,
        "mode"       : result.mode,
        "release_id" : result.release_id,
        "hits"       : [_hit_to_dict(hit) for hit in result.hits],
        "timings"    : _to_dict(result.timings),
    }


def asr_status() -> dict[str, Any] :
    global _state

    settings = get_asr_settings()
    if (not settings.enabled and _engine is None) :
        _state = "disabled"

    return {
        "enabled"      : settings.enabled,
        "state"        : _state,
        "release_id"   : None if _manifest is None else _manifest.release_id,
        "release_path" : str(settings.release_path),
        "release_exists" : settings.release_path.is_dir(),
        "device"       : settings.device,
        "error"        : _error,
    }
