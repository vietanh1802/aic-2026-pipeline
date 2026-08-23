from __future__ import annotations

from contextlib import contextmanager
from hashlib import sha256
from pathlib import Path
from typing import Any, Iterator
import json
import os
import re
import subprocess
import uuid
import wave

from .config import AudioWindowConfig
from .schemas import CanonicalAudioMetadata, PhysicalWindowSpec, VideoSourceMetadata


_VIDEO_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def calculate_source_sha256(path : Path, chunk_size : int = 8 * 1024 * 1024) -> str :
    path = Path(path)
    digest = sha256()

    with path.open("rb") as file :
        while True :
            chunk = file.read(chunk_size)

            if (not chunk) :
                break

            digest.update(chunk)

    return digest.hexdigest()


def canonical_video_id(source_video : Path, explicit_video_id : str | None = None) -> str :
    value = str(explicit_video_id or Path(source_video).stem).strip()

    if (not value) :
        raise ValueError("video_id must not be empty")
    if (not _VIDEO_ID_PATTERN.fullmatch(value)) :
        raise ValueError(
            "video_id must contain only letters, digits, '.', '_' or '-': "
            f"{value!r}"
        )

    return value



def validate_unique_video_ids(
    source_videos : list[Path] | tuple[Path, ...],
) -> dict[Path, str] :
    resolved = {
        Path(path) : canonical_video_id(Path(path))
        for path in source_videos
    }
    reverse : dict[str, list[Path]] = {}

    for path, video_id in resolved.items() :
        reverse.setdefault(video_id, []).append(path)

    collisions = {
        video_id : paths
        for video_id, paths in reverse.items()
        if len(paths) > 1
    }

    if (collisions) :
        details = "; ".join(
            f"{video_id}: {[str(path) for path in paths]}"
            for video_id, paths in sorted(collisions.items())
        )
        raise ValueError(
            "Source files resolve to duplicate canonical video IDs; "
            f"provide unique competition IDs before transcription: {details}"
        )

    return resolved

def probe_video(path : Path, timeout_s : int = 180) -> dict[str, Any] :
    path = Path(path)

    if (not path.exists()) :
        raise FileNotFoundError(path)

    command = [
        "ffprobe",
        "-v",
        "error",
        "-show_streams",
        "-show_format",
        "-of",
        "json",
        str(path),
    ]

    process = subprocess.run(
        command,
        capture_output = True,
        text = True,
        timeout = timeout_s,
        check = False,
    )

    if (process.returncode != 0) :
        raise RuntimeError(
            f"FFprobe failed for {path}:\n{process.stderr.strip()}"
        )

    return json.loads(process.stdout)


def select_audio_stream(
    probe : dict[str, Any],
    requested_index : int | None = None,
) -> dict[str, Any] :
    audio_streams = [
        stream
        for stream in probe.get("streams", [])
        if stream.get("codec_type") == "audio"
    ]

    if (not audio_streams) :
        raise RuntimeError("No audio stream found")

    if (requested_index is not None) :
        matches = [
            stream
            for stream in audio_streams
            if int(stream.get("index", -1)) == int(requested_index)
        ]

        if (len(matches) != 1) :
            raise RuntimeError(
                f"Requested audio stream {requested_index} was not found"
            )

        return matches[0]

    return min(audio_streams, key = lambda stream : int(stream.get("index", 0)))


def inspect_video_source(
    source_video : Path,
    explicit_video_id : str | None = None,
    audio_stream_index : int | None = None,
) -> VideoSourceMetadata :
    source_video = Path(source_video).resolve()
    video_id = canonical_video_id(source_video, explicit_video_id)
    probe = probe_video(source_video)
    audio_stream = select_audio_stream(probe, audio_stream_index)
    stat = source_video.stat()

    duration_value = probe.get("format", {}).get("duration")

    try :
        duration_s = float(duration_value) if duration_value is not None else None
    except (TypeError, ValueError) :
        duration_s = None

    return VideoSourceMetadata(
        video_id = video_id,
        source_path = str(source_video),
        source_size_bytes = int(stat.st_size),
        source_sha256 = calculate_source_sha256(source_video),
        audio_stream_index = int(audio_stream["index"]),
        source_duration_s = duration_s,
    )


def inspect_wav(path : Path) -> dict[str, int] :
    path = Path(path)

    with wave.open(str(path), "rb") as wav :
        return {
            "channels" : int(wav.getnchannels()),
            "sample_width_bytes" : int(wav.getsampwidth()),
            "sample_rate" : int(wav.getframerate()),
            "sample_count" : int(wav.getnframes()),
        }


def _validate_canonical_wav(path : Path, config : AudioWindowConfig) -> dict[str, int] :
    information = inspect_wav(path)

    expected = {
        "channels" : config.channels,
        "sample_width_bytes" : config.sample_width_bytes,
        "sample_rate" : config.sample_rate,
    }

    mismatches = {
        key : {
            "expected" : expected_value,
            "found" : information.get(key),
        }
        for key, expected_value in expected.items()
        if information.get(key) != expected_value
    }

    if (mismatches) :
        raise RuntimeError(
            f"Unexpected canonical WAV format for {path}: {mismatches}"
        )
    if (information["sample_count"] <= 0) :
        raise RuntimeError(f"Canonical WAV contains no samples: {path}")

    return information


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


def _audio_meta_path(destination_wav : Path) -> Path :
    return destination_wav.with_suffix(destination_wav.suffix + ".meta.json")


def _canonical_audio_reusable(
    destination_wav : Path,
    meta_path : Path,
    source : VideoSourceMetadata,
    config : AudioWindowConfig,
) -> CanonicalAudioMetadata | None :
    if (not destination_wav.exists() or not meta_path.exists()) :
        return None

    try :
        payload = json.loads(meta_path.read_text(encoding = "utf-8"))
    except Exception :
        return None

    expected = {
        "video_id" : source.video_id,
        "source_sha256" : source.source_sha256,
        "audio_stream_index" : source.audio_stream_index,
        "sample_rate" : config.sample_rate,
        "channels" : config.channels,
        "sample_width_bytes" : config.sample_width_bytes,
    }

    if (any(payload.get(key) != value for key, value in expected.items())) :
        return None

    try :
        information = _validate_canonical_wav(destination_wav, config)
        actual_hash = calculate_source_sha256(destination_wav)
    except Exception :
        return None

    if (actual_hash != payload.get("wav_sha256")) :
        return None

    return CanonicalAudioMetadata(
        video_id = source.video_id,
        source_sha256 = source.source_sha256,
        audio_stream_index = source.audio_stream_index,
        wav_path = str(destination_wav),
        wav_sha256 = actual_hash,
        wav_size_bytes = int(destination_wav.stat().st_size),
        sample_rate = information["sample_rate"],
        sample_count = information["sample_count"],
        channels = information["channels"],
        sample_width_bytes = information["sample_width_bytes"],
    )


def extract_canonical_wav(
    source : VideoSourceMetadata,
    destination_wav : Path,
    config : AudioWindowConfig,
    force_rebuild : bool = False,
    timeout_s : int = 900,
) -> CanonicalAudioMetadata :
    destination_wav = Path(destination_wav)
    meta_path = _audio_meta_path(destination_wav)

    if (not force_rebuild) :
        reusable = _canonical_audio_reusable(
            destination_wav,
            meta_path,
            source,
            config,
        )

        if (reusable is not None) :
            return reusable

    destination_wav.parent.mkdir(parents = True, exist_ok = True)
    temporary_wav = destination_wav.with_name(
        f"{destination_wav.stem}.tmp.{os.getpid()}.{uuid.uuid4().hex}.wav"
    )

    command = [
        "ffmpeg",
        "-nostdin",
        "-v",
        "error",
        "-y",
        "-i",
        source.source_path,
        "-map",
        f"0:{source.audio_stream_index}",
        "-vn",
        "-ac",
        str(config.channels),
        "-ar",
        str(config.sample_rate),
        "-c:a",
        "pcm_s16le",
        str(temporary_wav),
    ]

    try :
        process = subprocess.run(
            command,
            capture_output = True,
            text = True,
            timeout = timeout_s,
            check = False,
        )

        if (process.returncode != 0) :
            raise RuntimeError(
                f"FFmpeg failed for {source.video_id}:\n{process.stderr.strip()}"
            )

        information = _validate_canonical_wav(temporary_wav, config)
        wav_hash = calculate_source_sha256(temporary_wav)
        os.replace(temporary_wav, destination_wav)

        actual_hash = calculate_source_sha256(destination_wav)

        if (actual_hash != wav_hash) :
            raise RuntimeError(
                f"Canonical WAV hash changed after publication for {source.video_id}"
            )

        metadata = CanonicalAudioMetadata(
            video_id = source.video_id,
            source_sha256 = source.source_sha256,
            audio_stream_index = source.audio_stream_index,
            wav_path = str(destination_wav),
            wav_sha256 = actual_hash,
            wav_size_bytes = int(destination_wav.stat().st_size),
            sample_rate = information["sample_rate"],
            sample_count = information["sample_count"],
            channels = information["channels"],
            sample_width_bytes = information["sample_width_bytes"],
        )

        _atomic_write_json(
            meta_path,
            {
                "video_id" : metadata.video_id,
                "source_sha256" : metadata.source_sha256,
                "audio_stream_index" : metadata.audio_stream_index,
                "wav_path" : metadata.wav_path,
                "wav_sha256" : metadata.wav_sha256,
                "wav_size_bytes" : metadata.wav_size_bytes,
                "sample_rate" : metadata.sample_rate,
                "sample_count" : metadata.sample_count,
                "channels" : metadata.channels,
                "sample_width_bytes" : metadata.sample_width_bytes,
            },
        )

        return metadata
    finally :
        temporary_wav.unlink(missing_ok = True)


def build_physical_windows(
    video_id : str,
    sample_count : int,
    config : AudioWindowConfig,
) -> tuple[PhysicalWindowSpec, ...] :
    if (sample_count <= 0) :
        raise ValueError("sample_count must be positive")

    windows = []
    sample_start = 0
    window_index = 0

    while (sample_start < sample_count) :
        remaining = sample_count - sample_start

        if (
            window_index > 0
            and remaining < config.minimum_tail_samples
        ) :
            break

        duration_samples = min(
            config.window_samples,
            remaining,
        )
        sample_end = sample_start + duration_samples

        windows.append(
            PhysicalWindowSpec(
                window_id = f"{video_id}_{window_index:04d}",
                video_id = video_id,
                window_index = window_index,
                sample_start = sample_start,
                sample_end = sample_end,
                duration_samples = duration_samples,
                sample_rate = config.sample_rate,
            )
        )

        sample_start += config.stride_samples
        window_index += 1

    return tuple(windows)


def extract_window_wav(
    canonical_wav : Path,
    window : PhysicalWindowSpec,
    destination_wav : Path,
) -> str :
    canonical_wav = Path(canonical_wav)
    destination_wav = Path(destination_wav)
    destination_wav.parent.mkdir(parents = True, exist_ok = True)

    with wave.open(str(canonical_wav), "rb") as source :
        if (source.getframerate() != window.sample_rate) :
            raise RuntimeError(
                f"Unexpected sample rate for {canonical_wav}: "
                f"{source.getframerate()}, expected {window.sample_rate}"
            )
        if (source.getnchannels() != 1) :
            raise RuntimeError(
                f"Expected canonical mono WAV, found {source.getnchannels()} channels"
            )
        if (source.getsampwidth() != 2) :
            raise RuntimeError(
                f"Expected canonical PCM16 WAV, found sample width {source.getsampwidth()}"
            )

        source.setpos(window.sample_start)
        pcm_bytes = source.readframes(window.duration_samples)

    expected_bytes = window.duration_samples * 2

    if (len(pcm_bytes) != expected_bytes) :
        raise RuntimeError(
            f"{window.window_id} produced {len(pcm_bytes)} PCM bytes, "
            f"expected {expected_bytes}"
        )

    pcm_hash = sha256(pcm_bytes).hexdigest()
    temporary = destination_wav.with_name(
        f"{destination_wav.stem}.tmp.{os.getpid()}.{uuid.uuid4().hex}.wav"
    )

    try :
        with wave.open(str(temporary), "wb") as output :
            output.setnchannels(1)
            output.setsampwidth(2)
            output.setframerate(window.sample_rate)
            output.writeframes(pcm_bytes)

        os.replace(temporary, destination_wav)
    finally :
        temporary.unlink(missing_ok = True)

    return pcm_hash
