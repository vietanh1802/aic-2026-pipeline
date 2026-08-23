from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any, Iterable, Iterator
import gc
import json
import math
import os
import shutil
import socket
import traceback
import uuid

from .audio import (
    build_physical_windows,
    extract_canonical_wav,
    extract_window_wav,
    inspect_video_source,
    validate_unique_video_ids,
)
from .config import (
    OfflineASRConfig,
    ParakeetConfig,
    parakeet_identity,
    window_policy_identity,
)
from .postprocess import POSTPROCESS_VERSION, rebuild_processed_windows
from .schemas import (
    BoilerplateMatch,
    CanonicalAudioMetadata,
    PerVideoTranscriptArtifact,
    PhysicalWindowSpec,
    ProcessedTranscriptWindow,
    TranscriptSegment,
    TranscriptionError,
    TranscriptionResult,
    VideoSourceMetadata,
)


TRANSCRIPT_ARTIFACT_SCHEMA_VERSION = "1.0"


def utc_now() -> str :
    return datetime.now(timezone.utc).isoformat()


def _finite_float(value : Any) -> float | None :
    try :
        number = float(value)
    except (TypeError, ValueError) :
        return None

    return number if math.isfinite(number) else None


def _json_safe(value : Any) -> Any :
    if (value is None or isinstance(value, (str, int, bool))) :
        return value
    if (isinstance(value, float)) :
        return value if math.isfinite(value) else None
    if (isinstance(value, Path)) :
        return str(value)
    if (isinstance(value, dict)) :
        return {
            str(key) : _json_safe(item)
            for key, item in value.items()
        }
    if (isinstance(value, (list, tuple, set))) :
        return [_json_safe(item) for item in value]

    for method_name in ["detach", "cpu"] :
        if (hasattr(value, method_name)) :
            try :
                value = getattr(value, method_name)()
            except Exception :
                pass

    if (hasattr(value, "tolist")) :
        try :
            return _json_safe(value.tolist())
        except Exception :
            pass

    if (hasattr(value, "item")) :
        try :
            return _json_safe(value.item())
        except Exception :
            pass

    if (hasattr(value, "__dict__")) :
        try :
            return _json_safe(vars(value))
        except Exception :
            pass

    return str(value)


def _canonical_nemo_timestamp_segments(
    timestamps : dict[str, Any] | None,
) -> tuple[TranscriptSegment, ...] :
    if (not isinstance(timestamps, dict)) :
        return ()

    source_segments = timestamps.get("segment", [])

    if (not isinstance(source_segments, list)) :
        return ()

    segments = []

    for index, segment in enumerate(source_segments) :
        if (not isinstance(segment, dict)) :
            continue

        text = segment.get(
            "segment",
            segment.get("text", segment.get("word", "")),
        )
        confidence = _finite_float(segment.get("confidence"))

        segments.append(
            TranscriptSegment(
                segment_id = index,
                start_s = _finite_float(segment.get("start")),
                end_s = _finite_float(segment.get("end")),
                text = str(text).strip(),
                confidence = confidence,
            )
        )

    return tuple(segments)


def _timestamp_warnings(
    segments : tuple[TranscriptSegment, ...],
    duration_s : float,
) -> tuple[str, ...] :
    for segment in segments :
        start = segment.start_s
        end = segment.end_s

        if (start is None and end is None) :
            continue

        if (
            start is None
            or end is None
            or start < -0.25
            or end < start
            or end > duration_s + 1.0
        ) :
            return ("invalid_timestamps",)

    return ()


def _atomic_write_json(path : Path, value : dict[str, Any]) -> None :
    path = Path(path)
    path.parent.mkdir(parents = True, exist_ok = True)
    temporary = path.with_name(
        f"{path.name}.tmp.{os.getpid()}.{uuid.uuid4().hex}"
    )

    try :
        with temporary.open("w", encoding = "utf-8") as file :
            json.dump(
                value,
                file,
                ensure_ascii = False,
                indent = 2,
                allow_nan = False,
            )
            file.flush()
            os.fsync(file.fileno())

        os.replace(temporary, path)
    finally :
        temporary.unlink(missing_ok = True)


@contextmanager
def _video_lock(lock_path : Path) -> Iterator[None] :
    lock_path = Path(lock_path)
    lock_path.parent.mkdir(parents = True, exist_ok = True)
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY

    try :
        descriptor = os.open(lock_path, flags)
    except FileExistsError as error :
        raise RuntimeError(
            f"Video is already owned by another transcription worker: {lock_path.stem}"
        ) from error

    try :
        payload = {
            "pid" : os.getpid(),
            "host" : socket.gethostname(),
            "created_at_utc" : utc_now(),
        }
        os.write(
            descriptor,
            json.dumps(payload, ensure_ascii = False).encode("utf-8"),
        )
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
        yield
    finally :
        if (descriptor >= 0) :
            os.close(descriptor)
        lock_path.unlink(missing_ok = True)


class ParakeetTranscriber :
    def __init__(self, config : ParakeetConfig) :
        self.config = config
        self.model = None
        self.local_model_path : Path | None = None
        self._device = None

    @property
    def loaded(self) -> bool :
        return self.model is not None

    @property
    def resolved_revision(self) -> str :
        return self.config.revision

    def load(self) -> None :
        if (self.model is not None) :
            return

        import torch
        from huggingface_hub import hf_hub_download
        import nemo.collections.asr as nemo_asr

        version_parts = tuple(
            int(part)
            for part in torch.__version__.split("+")[0].split(".")[ : 2]
        )

        if (version_parts < (2, 7)) :
            raise RuntimeError(
                "NeMo 2.7.3 requires PyTorch 2.7 or newer. "
                f"Current version: {torch.__version__}."
            )

        if (self.config.device == "cuda" and not torch.cuda.is_available()) :
            raise RuntimeError(
                "Parakeet is configured for CUDA, but CUDA is not available. "
                "Select device='cpu' explicitly for CPU inference."
            )

        token = (
            os.environ.get("HF_TOKEN")
            or os.environ.get("HUGGING_FACE_HUB_TOKEN")
        )

        download_kwargs = {
            "repo_id" : self.config.model_name,
            "filename" : self.config.model_filename,
            "revision" : self.config.revision,
            "token" : token,
        }

        if (self.config.model_cache_dir is not None) :
            download_kwargs["cache_dir"] = str(self.config.model_cache_dir)

        self.local_model_path = Path(
            hf_hub_download(**download_kwargs)
        )
        self._device = torch.device(self.config.device)
        self.model = nemo_asr.models.ASRModel.restore_from(
            restore_path = str(self.local_model_path),
            map_location = self._device,
        )
        self.model.eval()
        self.model = self.model.to(self._device)

    def transcribe_window(
        self,
        window_wav : Path,
        window : PhysicalWindowSpec,
        window_pcm_sha256 : str,
        canonical_wav_sha256 : str,
    ) -> TranscriptionResult :
        if (self.model is None) :
            raise RuntimeError("Parakeet model is not loaded")

        import torch

        if (torch.cuda.is_available() and self.config.device == "cuda") :
            torch.cuda.empty_cache()
            torch.cuda.reset_peak_memory_stats()
            torch.cuda.synchronize()

        started = perf_counter()

        try :
            output = self.model.transcribe(
                audio = [str(window_wav)],
                batch_size = self.config.batch_size,
                timestamps = self.config.timestamps,
                verbose    = False,
            )

            if (torch.cuda.is_available() and self.config.device == "cuda") :
                torch.cuda.synchronize()

            runtime_s = perf_counter() - started
            hypothesis = (
                output[0]
                if isinstance(output, (list, tuple))
                else output
            )

            if (isinstance(hypothesis, str)) :
                text = hypothesis
                timestamps = None
            else :
                text = getattr(hypothesis, "text", "")
                timestamps = getattr(hypothesis, "timestamp", None)

            segments = _canonical_nemo_timestamp_segments(timestamps)
            warnings = _timestamp_warnings(segments, window.duration_s)

            return TranscriptionResult(
                window = window,
                status = "ok",
                raw_text = str(text).strip(),
                native_segments = segments,
                window_pcm_sha256 = window_pcm_sha256,
                canonical_wav_sha256 = canonical_wav_sha256,
                model_name = self.config.model_name,
                model_revision = self.resolved_revision,
                runtime_s = runtime_s,
                peak_gpu_memory_bytes = (
                    int(torch.cuda.max_memory_allocated())
                    if torch.cuda.is_available() and self.config.device == "cuda"
                    else 0
                ),
                peak_reserved_memory_bytes = (
                    int(torch.cuda.max_memory_reserved())
                    if torch.cuda.is_available() and self.config.device == "cuda"
                    else 0
                ),
                warning_reasons = warnings,
                resolved_arguments = {
                    "batch_size" : self.config.batch_size,
                    "timestamps" : self.config.timestamps,
                    "decoder" : self.config.decoder,
                    "dtype" : self.config.dtype,
                },
                error = None,
            )
        except Exception as error :
            runtime_s = perf_counter() - started

            return TranscriptionResult(
                window = window,
                status = "failed",
                raw_text = "",
                native_segments = (),
                window_pcm_sha256 = window_pcm_sha256,
                canonical_wav_sha256 = canonical_wav_sha256,
                model_name = self.config.model_name,
                model_revision = self.resolved_revision,
                runtime_s = runtime_s,
                peak_gpu_memory_bytes = (
                    int(torch.cuda.max_memory_allocated())
                    if torch.cuda.is_available() and self.config.device == "cuda"
                    else 0
                ),
                peak_reserved_memory_bytes = (
                    int(torch.cuda.max_memory_reserved())
                    if torch.cuda.is_available() and self.config.device == "cuda"
                    else 0
                ),
                warning_reasons = (),
                resolved_arguments = {},
                error = TranscriptionError(
                    error_type = type(error).__name__,
                    message = str(error),
                    traceback = traceback.format_exc(),
                ),
            )

    def close(self) -> None :
        self.model = None
        self.local_model_path = None
        self._device = None
        gc.collect()

        try :
            import torch

            if (torch.cuda.is_available()) :
                torch.cuda.empty_cache()
        except Exception :
            pass

    def __enter__(self) -> "ParakeetTranscriber" :
        self.load()
        return self

    def __exit__(self, exc_type, exc_value, exc_traceback) -> None :
        self.close()


def _window_spec_to_dict(window : PhysicalWindowSpec) -> dict[str, Any] :
    return {
        "window_id" : window.window_id,
        "video_id" : window.video_id,
        "window_index" : window.window_index,
        "sample_start" : window.sample_start,
        "sample_end" : window.sample_end,
        "duration_samples" : window.duration_samples,
        "sample_rate" : window.sample_rate,
        "start_s" : window.start_s,
        "end_s" : window.end_s,
    }


def _processed_window_to_dict(window : ProcessedTranscriptWindow) -> dict[str, Any] :
    return {
        **_window_spec_to_dict(window.window),
        "status" : window.status,
        "raw_text" : window.raw_text,
        "native_segments" : [asdict(segment) for segment in window.native_segments],
        "normalized_text" : window.normalized_text,
        "accent_folded_text" : window.accent_folded_text,
        "retrieval_text" : window.retrieval_text,
        "warning_reasons" : list(window.warning_reasons),
        "rejection_reasons" : list(window.rejection_reasons),
        "boilerplate_coverage" : window.boilerplate_coverage,
        "boilerplate_matches" : [asdict(item) for item in window.boilerplate_matches],
        "postprocess_version" : window.postprocess_version,
        "eligible" : window.eligible,
        "window_pcm_sha256" : window.window_pcm_sha256,
        "canonical_wav_sha256" : window.canonical_wav_sha256,
        "model_name" : window.model_name,
        "model_revision" : window.model_revision,
        "runtime_s" : window.runtime_s,
        "peak_gpu_memory_bytes" : window.peak_gpu_memory_bytes,
        "peak_reserved_memory_bytes" : window.peak_reserved_memory_bytes,
        "resolved_arguments" : _json_safe(window.resolved_arguments),
        "error" : asdict(window.error) if window.error is not None else None,
    }


def _video_to_dict(video : VideoSourceMetadata) -> dict[str, Any] :
    return asdict(video)


def _canonical_audio_to_dict(audio : CanonicalAudioMetadata) -> dict[str, Any] :
    return {
        **asdict(audio),
        "duration_s" : audio.duration_s,
    }


def _artifact_to_dict(artifact : PerVideoTranscriptArtifact) -> dict[str, Any] :
    return {
        "schema_version" : artifact.schema_version,
        "video" : _video_to_dict(artifact.video),
        "canonical_audio" : _canonical_audio_to_dict(artifact.canonical_audio),
        "window_policy_identity" : artifact.window_policy_identity,
        "parakeet_identity" : _json_safe(artifact.parakeet_identity),
        "postprocess_version" : artifact.postprocess_version,
        "created_at_utc" : artifact.created_at_utc,
        "updated_at_utc" : artifact.updated_at_utc,
        "complete" : artifact.complete,
        "windows" : [
            _processed_window_to_dict(window)
            for window in artifact.windows
        ],
    }


def _window_spec_from_dict(payload : dict[str, Any]) -> PhysicalWindowSpec :
    return PhysicalWindowSpec(
        window_id = str(payload["window_id"]),
        video_id = str(payload["video_id"]),
        window_index = int(payload["window_index"]),
        sample_start = int(payload["sample_start"]),
        sample_end = int(payload["sample_end"]),
        duration_samples = int(payload["duration_samples"]),
        sample_rate = int(payload["sample_rate"]),
    )


def _processed_window_from_dict(payload : dict[str, Any]) -> ProcessedTranscriptWindow :
    error_payload = payload.get("error")
    error = (
        TranscriptionError(
            error_type = str(error_payload.get("error_type", "")),
            message = str(error_payload.get("message", "")),
            traceback = error_payload.get("traceback"),
        )
        if isinstance(error_payload, dict)
        else None
    )

    return ProcessedTranscriptWindow(
        window = _window_spec_from_dict(payload),
        status = str(payload["status"]),
        raw_text = str(payload.get("raw_text", "")),
        native_segments = tuple(
            TranscriptSegment(
                segment_id = int(item.get("segment_id", index)),
                start_s = _finite_float(item.get("start_s")),
                end_s = _finite_float(item.get("end_s")),
                text = str(item.get("text", "")),
                confidence = _finite_float(item.get("confidence")),
            )
            for index, item in enumerate(payload.get("native_segments", []))
            if isinstance(item, dict)
        ),
        normalized_text = str(payload.get("normalized_text", "")),
        accent_folded_text = str(payload.get("accent_folded_text", "")),
        retrieval_text = str(payload.get("retrieval_text", "")),
        warning_reasons = tuple(str(item) for item in payload.get("warning_reasons", [])),
        rejection_reasons = tuple(str(item) for item in payload.get("rejection_reasons", [])),
        boilerplate_coverage = float(payload.get("boilerplate_coverage", 0.0)),
        boilerplate_matches = tuple(
            BoilerplateMatch(
                phrase = str(item.get("phrase", "")),
                start = int(item.get("start", 0)),
                end = int(item.get("end", 0)),
            )
            for item in payload.get("boilerplate_matches", [])
            if isinstance(item, dict)
        ),
        postprocess_version = str(payload.get("postprocess_version", "")),
        eligible = bool(payload.get("eligible", False)),
        window_pcm_sha256 = str(payload.get("window_pcm_sha256", "")),
        canonical_wav_sha256 = str(payload.get("canonical_wav_sha256", "")),
        model_name = str(payload.get("model_name", "")),
        model_revision = str(payload.get("model_revision", "")),
        runtime_s = float(payload.get("runtime_s", 0.0)),
        peak_gpu_memory_bytes = int(payload.get("peak_gpu_memory_bytes", 0)),
        peak_reserved_memory_bytes = int(payload.get("peak_reserved_memory_bytes", 0)),
        resolved_arguments = dict(payload.get("resolved_arguments", {})),
        error = error,
    )


def _processed_to_transcription(
    window : ProcessedTranscriptWindow,
) -> TranscriptionResult :
    return TranscriptionResult(
        window = window.window,
        status = window.status,
        raw_text = window.raw_text,
        native_segments = window.native_segments,
        window_pcm_sha256 = window.window_pcm_sha256,
        canonical_wav_sha256 = window.canonical_wav_sha256,
        model_name = window.model_name,
        model_revision = window.model_revision,
        runtime_s = window.runtime_s,
        peak_gpu_memory_bytes = window.peak_gpu_memory_bytes,
        peak_reserved_memory_bytes = window.peak_reserved_memory_bytes,
        warning_reasons = tuple(
            reason
            for reason in window.warning_reasons
            if reason not in {
                "consecutive_duplicate_segment",
                "known_boilerplate",
                "partial_known_boilerplate",
                "empty_output",
                "consecutive_duplicate_window",
            }
        ),
        resolved_arguments = window.resolved_arguments,
        error = window.error,
    )


def _load_existing_windows(path : Path) -> tuple[dict[str, Any] | None, dict[str, ProcessedTranscriptWindow]] :
    if (not path.exists()) :
        return None, {}

    payload = json.loads(path.read_text(encoding = "utf-8"))
    windows = {
        window.window.window_id : window
        for window in (
            _processed_window_from_dict(item)
            for item in payload.get("windows", [])
        )
    }
    return payload, windows


def _validate_existing_artifact_identity(
    payload : dict[str, Any],
    video : VideoSourceMetadata,
    config : OfflineASRConfig,
) -> None :
    expected = {
        "schema_version" : TRANSCRIPT_ARTIFACT_SCHEMA_VERSION,
        "video_id" : video.video_id,
        "source_sha256" : video.source_sha256,
        "audio_stream_index" : video.audio_stream_index,
        "window_policy_identity" : window_policy_identity(config.audio),
        "parakeet_identity" : parakeet_identity(config.parakeet),
    }
    found_video = payload.get("video", {})
    found = {
        "schema_version" : payload.get("schema_version"),
        "video_id" : found_video.get("video_id"),
        "source_sha256" : found_video.get("source_sha256"),
        "audio_stream_index" : found_video.get("audio_stream_index"),
        "window_policy_identity" : payload.get("window_policy_identity"),
        "parakeet_identity" : payload.get("parakeet_identity"),
    }
    mismatches = {
        key : {
            "expected" : expected_value,
            "found" : found.get(key),
        }
        for key, expected_value in expected.items()
        if found.get(key) != expected_value
    }

    if (mismatches) :
        raise RuntimeError(
            "Existing transcript artifact is incompatible with this run:\n"
            + json.dumps(mismatches, ensure_ascii = False, indent = 2)
        )


def _window_reusable(
    existing : ProcessedTranscriptWindow,
    expected : PhysicalWindowSpec,
    canonical_wav_sha256 : str,
    config : ParakeetConfig,
    retry_failed : bool,
    retry_empty : bool,
) -> bool :
    if (existing.window != expected) :
        return False
    if (existing.canonical_wav_sha256 != canonical_wav_sha256) :
        return False
    if (existing.model_name != config.model_name) :
        return False
    if (existing.model_revision != config.revision) :
        return False
    if (not existing.window_pcm_sha256) :
        return False

    if (existing.status == "ok" and existing.raw_text.strip()) :
        return True
    if (existing.status == "ok" and not existing.raw_text.strip()) :
        return not retry_empty
    if (existing.status == "failed") :
        return not retry_failed

    return False


def _make_artifact(
    video : VideoSourceMetadata,
    canonical_audio : CanonicalAudioMetadata,
    config : OfflineASRConfig,
    results : Iterable[TranscriptionResult],
    expected_window_count : int,
    created_at_utc : str,
) -> PerVideoTranscriptArtifact :
    processed = rebuild_processed_windows(tuple(results))

    return PerVideoTranscriptArtifact(
        schema_version = TRANSCRIPT_ARTIFACT_SCHEMA_VERSION,
        video = video,
        canonical_audio = canonical_audio,
        window_policy_identity = window_policy_identity(config.audio),
        parakeet_identity = parakeet_identity(config.parakeet),
        postprocess_version = POSTPROCESS_VERSION,
        created_at_utc = created_at_utc,
        updated_at_utc = utc_now(),
        windows = processed,
        complete = len(processed) == expected_window_count,
    )


def transcribe_video(
    source_video : Path,
    workspace : Path,
    config : OfflineASRConfig,
    transcriber : ParakeetTranscriber,
    video_id : str | None = None,
    audio_stream_index : int | None = None,
    retry_failed : bool = False,
    retry_empty : bool = False,
    force_rebuild : bool = False,
    remove_canonical_audio_after : bool = False,
) -> PerVideoTranscriptArtifact :
    if (not transcriber.loaded) :
        raise RuntimeError("ParakeetTranscriber must be loaded before transcribe_video")
    if (transcriber.config != config.parakeet) :
        raise ValueError("Transcriber configuration does not match OfflineASRConfig")

    workspace = Path(workspace)
    video = inspect_video_source(
        source_video,
        explicit_video_id = video_id,
        audio_stream_index = audio_stream_index,
    )
    transcript_path = workspace / "transcripts" / f"{video.video_id}.json"
    canonical_wav = workspace / "canonical_audio" / f"{video.video_id}.wav"
    lock_path = workspace / "locks" / f"{video.video_id}.lock"
    temp_root = workspace / "window_audio_tmp" / video.video_id

    with _video_lock(lock_path) :
        existing_payload = None
        existing_windows : dict[str, ProcessedTranscriptWindow] = {}

        if (transcript_path.exists() and not force_rebuild) :
            existing_payload, existing_windows = _load_existing_windows(transcript_path)
            assert existing_payload is not None
            _validate_existing_artifact_identity(existing_payload, video, config)
        elif (force_rebuild) :
            transcript_path.unlink(missing_ok = True)

        canonical_audio = extract_canonical_wav(
            source = video,
            destination_wav = canonical_wav,
            config = config.audio,
            force_rebuild = force_rebuild,
        )
        expected_windows = build_physical_windows(
            video.video_id,
            canonical_audio.sample_count,
            config.audio,
        )
        expected_ids = {window.window_id for window in expected_windows}

        if (existing_windows and not set(existing_windows).issubset(expected_ids)) :
            raise RuntimeError(
                f"Existing transcript artifact for {video.video_id} contains "
                "windows outside the current deterministic window set"
            )

        created_at = (
            str(existing_payload.get("created_at_utc"))
            if existing_payload is not None
            else utc_now()
        )
        result_map : dict[str, TranscriptionResult] = {}

        for expected in expected_windows :
            existing = existing_windows.get(expected.window_id)

            if (
                existing is not None
                and _window_reusable(
                    existing,
                    expected,
                    canonical_audio.wav_sha256,
                    config.parakeet,
                    retry_failed,
                    retry_empty,
                )
            ) :
                result_map[expected.window_id] = _processed_to_transcription(existing)
                continue

            window_wav = temp_root / f"{expected.window_id}.wav"

            try :
                pcm_hash = extract_window_wav(
                    canonical_wav,
                    expected,
                    window_wav,
                )
                result_map[expected.window_id] = transcriber.transcribe_window(
                    window_wav,
                    expected,
                    pcm_hash,
                    canonical_audio.wav_sha256,
                )
            finally :
                window_wav.unlink(missing_ok = True)

            ordered_results = [
                result_map[window.window_id]
                for window in expected_windows
                if window.window_id in result_map
            ]
            checkpoint = _make_artifact(
                video,
                canonical_audio,
                config,
                ordered_results,
                len(expected_windows),
                created_at,
            )
            _atomic_write_json(
                transcript_path,
                _artifact_to_dict(checkpoint),
            )

        ordered_results = [
            result_map[window.window_id]
            for window in expected_windows
        ]
        artifact = _make_artifact(
            video,
            canonical_audio,
            config,
            ordered_results,
            len(expected_windows),
            created_at,
        )
        _atomic_write_json(
            transcript_path,
            _artifact_to_dict(artifact),
        )

        shutil.rmtree(temp_root, ignore_errors = True)

        if (remove_canonical_audio_after) :
            canonical_wav.unlink(missing_ok = True)
            canonical_wav.with_suffix(canonical_wav.suffix + ".meta.json").unlink(
                missing_ok = True
            )

        return artifact


def transcribe_videos(
    source_videos : Iterable[Path],
    workspace : Path,
    config : OfflineASRConfig,
    transcriber : ParakeetTranscriber,
    retry_failed : bool = False,
    retry_empty : bool = False,
) -> tuple[PerVideoTranscriptArtifact, ...] :
    sources = tuple(Path(source_video) for source_video in source_videos)
    validate_unique_video_ids(sources)
    artifacts = []

    for source_video in sources :
        artifacts.append(
            transcribe_video(
                source_video = source_video,
                workspace = workspace,
                config = config,
                transcriber = transcriber,
                retry_failed = retry_failed,
                retry_empty = retry_empty,
            )
        )

    return tuple(artifacts)
