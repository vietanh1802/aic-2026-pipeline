from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any, Iterable, Sequence
import json
import math
import os
import shutil
import uuid

import numpy as np

from .bm25 import PersistentBM25Index, build_bm25_index, load_bm25_index, save_bm25_index
from .config import (
    ArtifactConfig,
    BM25Config,
    CorpusBuildConfig,
    E5Config,
    bm25_identity,
    corpus_build_config_identity,
    e5_identity,
    parakeet_identity,
    window_policy_identity,
)
from .postprocess import POSTPROCESS_VERSION
from .schemas import CorpusManifest, ReleaseVideoRecord, ReleaseWindowRecord


RELEASE_SCHEMA_VERSION = "1.0"
REQUIRED_RELEASE_FILES = (
    "videos.jsonl",
    "windows.jsonl",
    "eligible_window_ids.json",
    "eligible_to_physical.npy",
    "physical_to_eligible.npy",
    "window_to_video.npy",
    "video_window_offsets.npy",
    "video_window_physical_ids.npy",
    "e5_embeddings.npy",
    "bm25/vocabulary.json",
    "bm25/document_lengths.npy",
    "bm25/posting_offsets.npy",
    "bm25/posting_doc_ids.npy",
    "bm25/posting_term_frequencies.npy",
)


def utc_now() -> str :
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path : Path, chunk_size : int = 8 * 1024 * 1024) -> str :
    digest = sha256()
    with Path(path).open("rb") as file :
        while True :
            chunk = file.read(chunk_size)
            if (not chunk) :
                break
            digest.update(chunk)
    return digest.hexdigest()


def canonical_hash(value : Any) -> str :
    serialized = json.dumps(
        value,
        ensure_ascii = False,
        sort_keys = True,
        separators = (",", ":"),
        allow_nan = False,
    ).encode("utf-8")
    return sha256(serialized).hexdigest()


def _atomic_write_text(path : Path, text : str) -> None :
    path = Path(path)
    path.parent.mkdir(parents = True, exist_ok = True)
    temporary = path.with_name(f"{path.name}.tmp.{os.getpid()}.{uuid.uuid4().hex}")
    try :
        with temporary.open("w", encoding = "utf-8") as file :
            file.write(text)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, path)
    finally :
        temporary.unlink(missing_ok = True)


def _write_json(path : Path, value : Any) -> None :
    _atomic_write_text(
        path,
        json.dumps(
            value,
            ensure_ascii = False,
            indent = 2,
            allow_nan = False,
        ),
    )


def _write_jsonl(path : Path, rows : Iterable[dict[str, Any]]) -> None :
    lines = [json.dumps(row, ensure_ascii = False, allow_nan = False) for row in rows]
    _atomic_write_text(path, "\n".join(lines) + ("\n" if lines else ""))


def _read_jsonl(path : Path) -> list[dict[str, Any]] :
    rows = []
    with Path(path).open("r", encoding = "utf-8") as file :
        for line_number, line in enumerate(file, start = 1) :
            text = line.strip()
            if (not text) :
                continue
            value = json.loads(text)
            if (not isinstance(value, dict)) :
                raise ValueError(f"{path}:{line_number} must contain a JSON object")
            rows.append(value)
    return rows


def _manifest_to_dict(manifest : CorpusManifest) -> dict[str, Any] :
    payload = asdict(manifest)
    payload["embedding_shape"] = list(manifest.embedding_shape)
    return payload


def _manifest_from_dict(payload : dict[str, Any]) -> CorpusManifest :
    return CorpusManifest(
        schema_version = str(payload["schema_version"]),
        release_id = str(payload["release_id"]),
        created_at_utc = str(payload["created_at_utc"]),
        corpus_identity = str(payload["corpus_identity"]),
        config_identity = str(payload["config_identity"]),
        source_inventory_hash = str(payload["source_inventory_hash"]),
        video_count = int(payload["video_count"]),
        physical_window_count = int(payload["physical_window_count"]),
        eligible_window_count = int(payload["eligible_window_count"]),
        video_axis_sha256 = str(payload["video_axis_sha256"]),
        physical_window_axis_sha256 = str(payload["physical_window_axis_sha256"]),
        eligible_window_axis_sha256 = str(payload["eligible_window_axis_sha256"]),
        window_policy_identity = str(payload["window_policy_identity"]),
        parakeet_identity = dict(payload["parakeet_identity"]),
        postprocess_version = str(payload["postprocess_version"]),
        bm25_identity = dict(payload["bm25_identity"]),
        e5_identity = dict(payload["e5_identity"]),
        embedding_shape = tuple(int(value) for value in payload["embedding_shape"]),
        embedding_dtype = str(payload["embedding_dtype"]),
        file_hashes = {str(key) : str(value) for key, value in dict(payload["file_hashes"]).items()},
    )


def _video_record_to_dict(record : ReleaseVideoRecord) -> dict[str, Any] :
    return asdict(record)


def _window_record_to_dict(record : ReleaseWindowRecord) -> dict[str, Any] :
    payload = asdict(record)
    payload["warning_reasons"] = list(record.warning_reasons)
    payload["rejection_reasons"] = list(record.rejection_reasons)
    return payload


def _video_record_from_dict(payload : dict[str, Any]) -> ReleaseVideoRecord :
    return ReleaseVideoRecord(
        video_index = int(payload["video_index"]),
        video_id = str(payload["video_id"]),
        source_path = str(payload.get("source_path", "")),
        source_size_bytes = int(payload["source_size_bytes"]),
        source_sha256 = str(payload["source_sha256"]),
        audio_stream_index = int(payload["audio_stream_index"]),
        duration_samples = int(payload["duration_samples"]),
        sample_rate = int(payload["sample_rate"]),
        first_physical_window = int(payload["first_physical_window"]),
        physical_window_count = int(payload["physical_window_count"]),
    )


def _window_record_from_dict(payload : dict[str, Any]) -> ReleaseWindowRecord :
    return ReleaseWindowRecord(
        physical_index = int(payload["physical_index"]),
        window_id = str(payload["window_id"]),
        video_id = str(payload["video_id"]),
        video_index = int(payload["video_index"]),
        window_index = int(payload["window_index"]),
        sample_start = int(payload["sample_start"]),
        sample_end = int(payload["sample_end"]),
        duration_samples = int(payload["duration_samples"]),
        sample_rate = int(payload["sample_rate"]),
        status = str(payload["status"]),
        raw_text = str(payload.get("raw_text", "")),
        retrieval_text = str(payload.get("retrieval_text", "")),
        eligible = bool(payload["eligible"]),
        warning_reasons = tuple(str(value) for value in payload.get("warning_reasons", [])),
        rejection_reasons = tuple(str(value) for value in payload.get("rejection_reasons", [])),
        window_pcm_sha256 = str(payload.get("window_pcm_sha256", "")),
        postprocess_version = str(payload.get("postprocess_version", "")),
        document_identity = (
            str(payload["document_identity"])
            if payload.get("document_identity") is not None
            else None
        ),
    )


def _document_identity(payload : dict[str, Any]) -> str :
    return canonical_hash({
        "window_id" : str(payload["window_id"]),
        "window_pcm_sha256" : str(payload.get("window_pcm_sha256", "")),
        "retrieval_text" : str(payload.get("retrieval_text", "")),
        "eligible" : bool(payload.get("eligible", False)),
        "postprocess_version" : str(payload.get("postprocess_version", "")),
    })


def _load_transcript_payloads(
    workspace : Path,
    config : CorpusBuildConfig,
) -> list[dict[str, Any]] :
    transcript_root = Path(workspace) / "transcripts"
    paths = sorted(transcript_root.glob("*.json"))
    if (not paths) :
        raise FileNotFoundError(f"No Phase 1 transcript artifacts found under {transcript_root}")

    expected_window_policy = window_policy_identity(config.offline.audio)
    expected_parakeet = parakeet_identity(config.offline.parakeet)
    payloads = []
    video_ids = set()

    for path in paths :
        payload = json.loads(path.read_text(encoding = "utf-8"))
        if (payload.get("schema_version") != "1.0") :
            raise ValueError(f"Unsupported transcript artifact schema: {path}")
        if (not bool(payload.get("complete", False))) :
            raise ValueError(f"Transcript artifact is incomplete: {path}")
        if (payload.get("window_policy_identity") != expected_window_policy) :
            raise ValueError(f"Window policy mismatch in {path}")
        if (payload.get("parakeet_identity") != expected_parakeet) :
            raise ValueError(f"Parakeet identity mismatch in {path}")
        if (payload.get("postprocess_version") != POSTPROCESS_VERSION) :
            raise ValueError(f"Postprocess version mismatch in {path}")

        video = payload.get("video", {})
        video_id = str(video.get("video_id", ""))
        if (not video_id) :
            raise ValueError(f"Transcript artifact has no video_id: {path}")
        if (video_id in video_ids) :
            raise ValueError(f"Duplicate video_id across transcript artifacts: {video_id}")
        video_ids.add(video_id)

        windows = payload.get("windows", [])
        if (not isinstance(windows, list) or not windows) :
            raise ValueError(f"Transcript artifact has no windows: {path}")
        window_ids = [str(item.get("window_id", "")) for item in windows]
        if (len(window_ids) != len(set(window_ids)) or any(not value for value in window_ids)) :
            raise ValueError(f"Transcript artifact contains invalid/duplicate window IDs: {path}")
        expected_indices = list(range(len(windows)))
        observed_indices = [int(item.get("window_index", -1)) for item in windows]
        if (observed_indices != expected_indices) :
            raise ValueError(f"Transcript windows are not in deterministic index order: {path}")

        for window in windows :
            if (str(window.get("video_id", "")) != video_id) :
                raise ValueError(f"Window/video mismatch in {path}")
            status = str(window.get("status", ""))
            retrieval_text = str(window.get("retrieval_text", ""))
            rejections = tuple(str(value) for value in window.get("rejection_reasons", []))
            expected_eligible = status == "ok" and bool(retrieval_text.strip()) and not rejections
            if (bool(window.get("eligible", False)) != expected_eligible) :
                raise ValueError(f"Eligibility mismatch for {window.get('window_id')} in {path}")
            if (str(window.get("postprocess_version", "")) != POSTPROCESS_VERSION) :
                raise ValueError(f"Window postprocess version mismatch in {path}")

        payloads.append(payload)

    return sorted(payloads, key = lambda value : str(value["video"]["video_id"]))


def _build_release_records(
    payloads : Sequence[dict[str, Any]],
) -> tuple[
    tuple[ReleaseVideoRecord, ...],
    tuple[ReleaseWindowRecord, ...],
    np.ndarray,
    np.ndarray,
    np.ndarray,
    np.ndarray,
    np.ndarray,
    tuple[str, ...],
] :
    videos = []
    windows = []
    eligible_to_physical = []
    physical_to_eligible = []
    window_to_video = []
    video_window_offsets = [0]
    video_window_physical_ids = []
    eligible_window_ids = []
    all_window_ids = set()

    for video_index, payload in enumerate(payloads) :
        video = payload["video"]
        audio = payload["canonical_audio"]
        video_id = str(video["video_id"])
        video_windows = payload["windows"]
        first_physical = len(windows)

        videos.append(
            ReleaseVideoRecord(
                video_index = video_index,
                video_id = video_id,
                source_path = str(video.get("source_path", "")),
                source_size_bytes = int(video["source_size_bytes"]),
                source_sha256 = str(video["source_sha256"]),
                audio_stream_index = int(video["audio_stream_index"]),
                duration_samples = int(audio["sample_count"]),
                sample_rate = int(audio["sample_rate"]),
                first_physical_window = first_physical,
                physical_window_count = len(video_windows),
            )
        )

        for item in video_windows :
            physical_index = len(windows)
            window_id = str(item["window_id"])
            if (window_id in all_window_ids) :
                raise ValueError(f"Duplicate physical window ID across corpus: {window_id}")
            all_window_ids.add(window_id)
            eligible = bool(item["eligible"])
            document_identity = _document_identity(item) if eligible else None

            windows.append(
                ReleaseWindowRecord(
                    physical_index = physical_index,
                    window_id = window_id,
                    video_id = video_id,
                    video_index = video_index,
                    window_index = int(item["window_index"]),
                    sample_start = int(item["sample_start"]),
                    sample_end = int(item["sample_end"]),
                    duration_samples = int(item["duration_samples"]),
                    sample_rate = int(item["sample_rate"]),
                    status = str(item["status"]),
                    raw_text = str(item.get("raw_text", "")),
                    retrieval_text = str(item.get("retrieval_text", "")),
                    eligible = eligible,
                    warning_reasons = tuple(str(value) for value in item.get("warning_reasons", [])),
                    rejection_reasons = tuple(str(value) for value in item.get("rejection_reasons", [])),
                    window_pcm_sha256 = str(item.get("window_pcm_sha256", "")),
                    postprocess_version = str(item.get("postprocess_version", "")),
                    document_identity = document_identity,
                )
            )
            window_to_video.append(video_index)
            video_window_physical_ids.append(physical_index)

            if (eligible) :
                eligible_index = len(eligible_to_physical)
                eligible_to_physical.append(physical_index)
                physical_to_eligible.append(eligible_index)
                eligible_window_ids.append(window_id)
            else :
                physical_to_eligible.append(-1)

        video_window_offsets.append(len(video_window_physical_ids))

    if (not eligible_window_ids) :
        raise ValueError("Corpus contains no retrieval-eligible transcript windows")

    return (
        tuple(videos),
        tuple(windows),
        np.asarray(eligible_to_physical, dtype = np.int64),
        np.asarray(physical_to_eligible, dtype = np.int64),
        np.asarray(window_to_video, dtype = np.int32),
        np.asarray(video_window_offsets, dtype = np.int64),
        np.asarray(video_window_physical_ids, dtype = np.int64),
        tuple(eligible_window_ids),
    )


def _video_axis_hash(videos : Sequence[ReleaseVideoRecord]) -> str :
    return canonical_hash([
        [record.video_index, record.video_id]
        for record in videos
    ])


def _physical_axis_hash(windows : Sequence[ReleaseWindowRecord]) -> str :
    return canonical_hash([
        [
            record.physical_index,
            record.window_id,
            record.video_id,
            record.sample_start,
            record.sample_end,
        ]
        for record in windows
    ])


def _eligible_axis_hash(
    windows : Sequence[ReleaseWindowRecord],
    eligible_to_physical : np.ndarray,
) -> str :
    return canonical_hash([
        [
            eligible_index,
            windows[int(physical_index)].window_id,
            int(physical_index),
            windows[int(physical_index)].document_identity,
        ]
        for eligible_index, physical_index in enumerate(eligible_to_physical.tolist())
    ])


def _source_inventory_hash(videos : Sequence[ReleaseVideoRecord]) -> str :
    return canonical_hash([
        [
            record.video_id,
            record.source_sha256,
            record.source_size_bytes,
            record.duration_samples,
            record.sample_rate,
        ]
        for record in videos
    ])


def _corpus_identity(
    source_inventory_hash : str,
    physical_axis_hash : str,
    eligible_axis_hash : str,
) -> str :
    return canonical_hash({
        "source_inventory_hash" : source_inventory_hash,
        "physical_window_axis_sha256" : physical_axis_hash,
        "eligible_window_axis_sha256" : eligible_axis_hash,
    })


def _bm25_config_from_manifest(manifest : CorpusManifest) -> BM25Config :
    identity = manifest.bm25_identity
    return BM25Config(
        k1 = float(identity["k1"]),
        b = float(identity["b"]),
        unique_query_terms = bool(identity["unique_query_terms"]),
        normalization_id = str(identity["normalization_id"]),
        idf_policy = str(identity["idf_policy"]),
    )


def _validate_embeddings(matrix : np.ndarray, eligible_count : int, dimension : int) -> np.ndarray :
    values = np.asarray(matrix)
    if (values.shape != (eligible_count, dimension)) :
        raise ValueError(
            f"E5 embedding shape {values.shape} does not match "
            f"({eligible_count}, {dimension})"
        )
    if (values.dtype != np.float32) :
        raise ValueError(f"E5 embeddings must be float32, found {values.dtype}")
    if (not np.isfinite(values).all()) :
        raise ValueError("E5 embeddings contain non-finite values")
    norms = np.linalg.norm(values, axis = 1)
    if (not np.allclose(norms, 1.0, atol = 1e-5, rtol = 1e-5)) :
        raise ValueError("E5 document embeddings are not explicitly L2 normalized")
    return values


def _build_embeddings(
    windows : Sequence[ReleaseWindowRecord],
    eligible_to_physical : np.ndarray,
    config : CorpusBuildConfig,
    encoder : Any | None,
    previous_release : Path | None,
) -> np.ndarray :
    eligible_count = len(eligible_to_physical)
    output = np.empty((eligible_count, config.e5.dimension), dtype = np.float32)
    filled = np.zeros(eligible_count, dtype = bool)

    if (previous_release is not None) :
        previous = load_release(previous_release, ArtifactConfig(verify_file_hashes = True, load_embeddings_into_ram = True))
        if (previous.manifest.e5_identity == e5_identity(config.e5)) :
            previous_map = {
                record.window_id : (record.document_identity, eligible_index)
                for eligible_index, physical_index in enumerate(previous.eligible_to_physical.tolist())
                for record in [previous.windows[int(physical_index)]]
            }
            for eligible_index, physical_index in enumerate(eligible_to_physical.tolist()) :
                current = windows[int(physical_index)]
                previous_entry = previous_map.get(current.window_id)
                if (previous_entry is None) :
                    continue
                previous_identity, previous_row = previous_entry
                if (previous_identity == current.document_identity) :
                    output[eligible_index] = previous.embeddings[previous_row]
                    filled[eligible_index] = True

    missing_indices = np.flatnonzero(~filled).astype(int).tolist()
    if (missing_indices) :
        if (encoder is None) :
            raise ValueError("An E5 encoder is required because not all document embeddings are reusable")
        encoder_config = getattr(encoder, "config", None)
        if (encoder_config is not None and encoder_config != config.e5) :
            raise ValueError("E5 encoder configuration does not match CorpusBuildConfig")
        if (hasattr(encoder, "loaded") and not bool(encoder.loaded)) :
            raise RuntimeError("E5 encoder must be loaded before build_release")

        ids = [windows[int(eligible_to_physical[index])].window_id for index in missing_indices]
        texts = [windows[int(eligible_to_physical[index])].retrieval_text for index in missing_indices]
        encoded = np.asarray(encoder.encode_documents(ids, texts), dtype = np.float32)
        encoded = _validate_embeddings(encoded, len(missing_indices), config.e5.dimension)
        output[np.asarray(missing_indices, dtype = np.int64)] = encoded
        filled[np.asarray(missing_indices, dtype = np.int64)] = True

    if (not filled.all()) :
        raise RuntimeError("Failed to account for every E5 embedding row")
    return _validate_embeddings(output, eligible_count, config.e5.dimension)


@dataclass(frozen = True)
class LoadedRelease :
    path : Path
    manifest : CorpusManifest
    videos : tuple[ReleaseVideoRecord, ...]
    windows : tuple[ReleaseWindowRecord, ...]
    eligible_window_ids : tuple[str, ...]
    eligible_to_physical : np.ndarray
    physical_to_eligible : np.ndarray
    window_to_video : np.ndarray
    video_window_offsets : np.ndarray
    video_window_physical_ids : np.ndarray
    embeddings : np.ndarray
    bm25 : PersistentBM25Index


def build_release(
    workspace : Path,
    releases_root : Path,
    release_id : str,
    config : CorpusBuildConfig,
    encoder : Any | None,
    previous_release : Path | None = None,
) -> Path :
    release_id = str(release_id).strip()
    if (not release_id or release_id in {".", ".."} or "/" in release_id or "\\" in release_id) :
        raise ValueError("release_id must be a simple nonempty directory name")

    releases_root = Path(releases_root)
    final_path = releases_root / release_id
    if (final_path.exists()) :
        raise FileExistsError(f"Immutable release already exists: {final_path}")

    payloads = _load_transcript_payloads(workspace, config)
    (
        videos,
        windows,
        eligible_to_physical,
        physical_to_eligible,
        window_to_video,
        video_window_offsets,
        video_window_physical_ids,
        eligible_window_ids,
    ) = _build_release_records(payloads)

    eligible_texts = [windows[int(index)].retrieval_text for index in eligible_to_physical.tolist()]
    bm25 = build_bm25_index(eligible_window_ids, eligible_texts, config.bm25)
    embeddings = _build_embeddings(
        windows,
        eligible_to_physical,
        config,
        encoder,
        previous_release,
    )

    source_hash = _source_inventory_hash(videos)
    video_axis_hash = _video_axis_hash(videos)
    physical_axis_hash = _physical_axis_hash(windows)
    eligible_axis_hash = _eligible_axis_hash(windows, eligible_to_physical)
    corpus_id = _corpus_identity(source_hash, physical_axis_hash, eligible_axis_hash)

    releases_root.mkdir(parents = True, exist_ok = True)
    building_path = releases_root / f"{release_id}.building.{uuid.uuid4().hex}"
    building_path.mkdir(parents = False, exist_ok = False)

    try :
        _write_jsonl(building_path / "videos.jsonl", (_video_record_to_dict(record) for record in videos))
        _write_jsonl(building_path / "windows.jsonl", (_window_record_to_dict(record) for record in windows))
        _write_json(
            building_path / "eligible_window_ids.json",
            {
                "schema_version" : RELEASE_SCHEMA_VERSION,
                "window_ids" : list(eligible_window_ids),
            },
        )
        np.save(building_path / "eligible_to_physical.npy", eligible_to_physical, allow_pickle = False)
        np.save(building_path / "physical_to_eligible.npy", physical_to_eligible, allow_pickle = False)
        np.save(building_path / "window_to_video.npy", window_to_video, allow_pickle = False)
        np.save(building_path / "video_window_offsets.npy", video_window_offsets, allow_pickle = False)
        np.save(building_path / "video_window_physical_ids.npy", video_window_physical_ids, allow_pickle = False)
        np.save(building_path / "e5_embeddings.npy", embeddings, allow_pickle = False)
        save_bm25_index(bm25, building_path / "bm25")

        file_hashes = {
            relative : sha256_file(building_path / relative)
            for relative in REQUIRED_RELEASE_FILES
        }
        manifest = CorpusManifest(
            schema_version = RELEASE_SCHEMA_VERSION,
            release_id = release_id,
            created_at_utc = utc_now(),
            corpus_identity = corpus_id,
            config_identity = corpus_build_config_identity(config),
            source_inventory_hash = source_hash,
            video_count = len(videos),
            physical_window_count = len(windows),
            eligible_window_count = len(eligible_window_ids),
            video_axis_sha256 = video_axis_hash,
            physical_window_axis_sha256 = physical_axis_hash,
            eligible_window_axis_sha256 = eligible_axis_hash,
            window_policy_identity = window_policy_identity(config.offline.audio),
            parakeet_identity = parakeet_identity(config.offline.parakeet),
            postprocess_version = POSTPROCESS_VERSION,
            bm25_identity = bm25_identity(config.bm25),
            e5_identity = e5_identity(config.e5),
            embedding_shape = tuple(int(value) for value in embeddings.shape),
            embedding_dtype = str(embeddings.dtype),
            file_hashes = file_hashes,
        )
        _write_json(building_path / "manifest.json", _manifest_to_dict(manifest))
        validate_release(building_path, verify_hashes = True)
        os.replace(building_path, final_path)
    except Exception :
        shutil.rmtree(building_path, ignore_errors = True)
        raise

    return final_path


def validate_release(path : Path, verify_hashes : bool = True) -> CorpusManifest :
    path = Path(path)
    manifest_path = path / "manifest.json"
    if (not manifest_path.exists()) :
        raise FileNotFoundError(f"Release manifest not found: {manifest_path}")
    manifest = _manifest_from_dict(json.loads(manifest_path.read_text(encoding = "utf-8")))
    if (manifest.schema_version != RELEASE_SCHEMA_VERSION) :
        raise ValueError("Unsupported release schema_version")
    if (manifest.release_id != path.name and ".building." not in path.name) :
        raise ValueError("Release directory name does not match manifest release_id")

    for relative in REQUIRED_RELEASE_FILES :
        file_path = path / relative
        if (not file_path.exists()) :
            raise FileNotFoundError(f"Required release artifact is missing: {file_path}")
        expected_hash = manifest.file_hashes.get(relative)
        if (expected_hash is None) :
            raise ValueError(f"Manifest has no hash for required file: {relative}")
        if (verify_hashes) :
            actual_hash = sha256_file(file_path)
            if (actual_hash != expected_hash) :
                raise ValueError(f"Release file hash mismatch for {relative}")

    videos = tuple(_video_record_from_dict(row) for row in _read_jsonl(path / "videos.jsonl"))
    windows = tuple(_window_record_from_dict(row) for row in _read_jsonl(path / "windows.jsonl"))
    eligible_payload = json.loads((path / "eligible_window_ids.json").read_text(encoding = "utf-8"))
    if (eligible_payload.get("schema_version") != RELEASE_SCHEMA_VERSION) :
        raise ValueError("Unsupported eligible_window_ids schema")
    eligible_window_ids = tuple(str(value) for value in eligible_payload.get("window_ids", []))

    if (len(videos) != manifest.video_count) :
        raise ValueError("Video count does not match manifest")
    if (len(windows) != manifest.physical_window_count) :
        raise ValueError("Physical window count does not match manifest")
    if (len(eligible_window_ids) != manifest.eligible_window_count) :
        raise ValueError("Eligible window count does not match manifest")
    if ([record.video_index for record in videos] != list(range(len(videos)))) :
        raise ValueError("Video axis indices are not contiguous")
    if ([record.physical_index for record in windows] != list(range(len(windows)))) :
        raise ValueError("Physical window axis indices are not contiguous")
    if (len({record.video_id for record in videos}) != len(videos)) :
        raise ValueError("Video axis contains duplicate video IDs")
    if (len({record.window_id for record in windows}) != len(windows)) :
        raise ValueError("Physical window axis contains duplicate window IDs")

    eligible_to_physical = np.load(path / "eligible_to_physical.npy", allow_pickle = False)
    physical_to_eligible = np.load(path / "physical_to_eligible.npy", allow_pickle = False)
    window_to_video = np.load(path / "window_to_video.npy", allow_pickle = False)
    video_window_offsets = np.load(path / "video_window_offsets.npy", allow_pickle = False)
    video_window_physical_ids = np.load(path / "video_window_physical_ids.npy", allow_pickle = False)
    embeddings = np.load(path / "e5_embeddings.npy", allow_pickle = False)

    if (eligible_to_physical.dtype != np.int64 or eligible_to_physical.shape != (manifest.eligible_window_count,)) :
        raise ValueError("eligible_to_physical has wrong dtype or shape")
    if (physical_to_eligible.dtype != np.int64 or physical_to_eligible.shape != (manifest.physical_window_count,)) :
        raise ValueError("physical_to_eligible has wrong dtype or shape")
    if (window_to_video.dtype != np.int32 or window_to_video.shape != (manifest.physical_window_count,)) :
        raise ValueError("window_to_video has wrong dtype or shape")
    if (video_window_offsets.dtype != np.int64 or video_window_offsets.shape != (manifest.video_count + 1,)) :
        raise ValueError("video_window_offsets has wrong dtype or shape")
    if (video_window_physical_ids.dtype != np.int64 or video_window_physical_ids.shape != (manifest.physical_window_count,)) :
        raise ValueError("video_window_physical_ids has wrong dtype or shape")

    if (manifest.eligible_window_count) :
        if (np.any(eligible_to_physical < 0) or np.any(eligible_to_physical >= manifest.physical_window_count)) :
            raise ValueError("eligible_to_physical contains out-of-range rows")
        if (len(np.unique(eligible_to_physical)) != len(eligible_to_physical)) :
            raise ValueError("eligible_to_physical contains duplicates")
    expected_inverse = np.full(manifest.physical_window_count, -1, dtype = np.int64)
    expected_inverse[eligible_to_physical] = np.arange(manifest.eligible_window_count, dtype = np.int64)
    if (not np.array_equal(physical_to_eligible, expected_inverse)) :
        raise ValueError("physical_to_eligible is not the inverse of eligible_to_physical")

    expected_eligible_ids = tuple(windows[int(index)].window_id for index in eligible_to_physical.tolist())
    if (eligible_window_ids != expected_eligible_ids) :
        raise ValueError("eligible_window_ids does not match eligible axis")
    for eligible_index, physical_index in enumerate(eligible_to_physical.tolist()) :
        record = windows[int(physical_index)]
        if (not record.eligible or not record.retrieval_text.strip() or record.document_identity is None) :
            raise ValueError(f"Eligible axis contains an invalid document at row {eligible_index}")

    expected_window_to_video = np.asarray([record.video_index for record in windows], dtype = np.int32)
    if (not np.array_equal(window_to_video, expected_window_to_video)) :
        raise ValueError("window_to_video does not match windows.jsonl")
    if (video_window_offsets[0] != 0 or video_window_offsets[-1] != manifest.physical_window_count) :
        raise ValueError("video_window_offsets boundaries are invalid")
    if (np.any(video_window_offsets[1:] < video_window_offsets[:-1])) :
        raise ValueError("video_window_offsets is not monotonic")
    expected_flattened = []
    for video in videos :
        start = video.first_physical_window
        end = start + video.physical_window_count
        if (start < 0 or end > len(windows)) :
            raise ValueError("Video physical-window range is invalid")
        ids = list(range(start, end))
        if (any(windows[index].video_index != video.video_index for index in ids)) :
            raise ValueError("Video/window axis membership mismatch")
        expected_flattened.extend(ids)
    if (not np.array_equal(video_window_physical_ids, np.asarray(expected_flattened, dtype = np.int64))) :
        raise ValueError("video_window_physical_ids does not match canonical video grouping")

    if (_video_axis_hash(videos) != manifest.video_axis_sha256) :
        raise ValueError("Video axis hash mismatch")
    if (_physical_axis_hash(windows) != manifest.physical_window_axis_sha256) :
        raise ValueError("Physical window axis hash mismatch")
    if (_eligible_axis_hash(windows, eligible_to_physical) != manifest.eligible_window_axis_sha256) :
        raise ValueError("Eligible window axis hash mismatch")
    source_hash = _source_inventory_hash(videos)
    if (source_hash != manifest.source_inventory_hash) :
        raise ValueError("Source inventory hash mismatch")
    if (_corpus_identity(source_hash, manifest.physical_window_axis_sha256, manifest.eligible_window_axis_sha256) != manifest.corpus_identity) :
        raise ValueError("Corpus identity mismatch")

    e5_id = manifest.e5_identity
    dimension = int(e5_id["dimension"])
    _validate_embeddings(embeddings, manifest.eligible_window_count, dimension)
    if (tuple(embeddings.shape) != manifest.embedding_shape) :
        raise ValueError("Embedding shape does not match manifest")
    if (str(embeddings.dtype) != manifest.embedding_dtype) :
        raise ValueError("Embedding dtype does not match manifest")

    bm25_config = _bm25_config_from_manifest(manifest)
    bm25 = load_bm25_index(path / "bm25", manifest.eligible_window_count, bm25_config)
    if (bm25.document_count != manifest.eligible_window_count) :
        raise ValueError("BM25 document axis does not match eligible axis")

    return manifest


def load_release(
    path : Path,
    config : ArtifactConfig | None = None,
) -> LoadedRelease :
    config = config or ArtifactConfig()
    path = Path(path)
    manifest = validate_release(path, verify_hashes = config.verify_file_hashes)
    videos = tuple(_video_record_from_dict(row) for row in _read_jsonl(path / "videos.jsonl"))
    windows = tuple(_window_record_from_dict(row) for row in _read_jsonl(path / "windows.jsonl"))
    eligible_payload = json.loads((path / "eligible_window_ids.json").read_text(encoding = "utf-8"))
    eligible_window_ids = tuple(str(value) for value in eligible_payload["window_ids"])
    eligible_to_physical = np.load(path / "eligible_to_physical.npy", allow_pickle = False)
    physical_to_eligible = np.load(path / "physical_to_eligible.npy", allow_pickle = False)
    window_to_video = np.load(path / "window_to_video.npy", allow_pickle = False)
    video_window_offsets = np.load(path / "video_window_offsets.npy", allow_pickle = False)
    video_window_physical_ids = np.load(path / "video_window_physical_ids.npy", allow_pickle = False)
    embeddings = np.load(
        path / "e5_embeddings.npy",
        allow_pickle = False,
        mmap_mode = None if config.load_embeddings_into_ram else "r",
    )
    bm25 = load_bm25_index(
        path / "bm25",
        manifest.eligible_window_count,
        _bm25_config_from_manifest(manifest),
    )
    return LoadedRelease(
        path = path,
        manifest = manifest,
        videos = videos,
        windows = windows,
        eligible_window_ids = eligible_window_ids,
        eligible_to_physical = eligible_to_physical,
        physical_to_eligible = physical_to_eligible,
        window_to_video = window_to_video,
        video_window_offsets = video_window_offsets,
        video_window_physical_ids = video_window_physical_ids,
        embeddings = embeddings,
        bm25 = bm25,
    )


def activate_release(releases_root : Path, release_id : str) -> None :
    releases_root = Path(releases_root)
    release_path = releases_root / str(release_id)
    validate_release(release_path, verify_hashes = True)
    _atomic_write_text(releases_root / "CURRENT", str(release_id).strip() + "\n")


def resolve_active_release(releases_root : Path) -> Path :
    releases_root = Path(releases_root)
    current = releases_root / "CURRENT"
    if (not current.exists()) :
        raise FileNotFoundError(f"No active release pointer: {current}")
    release_id = current.read_text(encoding = "utf-8").strip()
    if (not release_id) :
        raise ValueError("CURRENT release pointer is empty")
    path = releases_root / release_id
    validate_release(path, verify_hashes = True)
    return path
