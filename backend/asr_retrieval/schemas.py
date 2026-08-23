from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


TranscriptionStatus = Literal["ok", "failed"]


@dataclass(frozen = True)
class VideoSourceMetadata :
    video_id : str
    source_path : str
    source_size_bytes : int
    source_sha256 : str
    audio_stream_index : int
    source_duration_s : float | None


@dataclass(frozen = True)
class CanonicalAudioMetadata :
    video_id : str
    source_sha256 : str
    audio_stream_index : int
    wav_path : str
    wav_sha256 : str
    wav_size_bytes : int
    sample_rate : int
    sample_count : int
    channels : int
    sample_width_bytes : int

    @property
    def duration_s(self) -> float :
        return self.sample_count / self.sample_rate


@dataclass(frozen = True)
class PhysicalWindowSpec :
    window_id : str
    video_id : str
    window_index : int
    sample_start : int
    sample_end : int
    duration_samples : int
    sample_rate : int

    def __post_init__(self) -> None :
        if (not self.window_id) :
            raise ValueError("window_id must not be empty")
        if (not self.video_id) :
            raise ValueError("video_id must not be empty")
        if (self.window_index < 0) :
            raise ValueError("window_index must be non-negative")
        if (self.sample_rate <= 0) :
            raise ValueError("sample_rate must be positive")
        if (self.sample_start < 0) :
            raise ValueError("sample_start must be non-negative")
        if (self.sample_end <= self.sample_start) :
            raise ValueError("sample_end must be greater than sample_start")
        if (self.sample_end - self.sample_start != self.duration_samples) :
            raise ValueError("duration_samples must equal sample_end - sample_start")

    @property
    def start_s(self) -> float :
        return self.sample_start / self.sample_rate

    @property
    def end_s(self) -> float :
        return self.sample_end / self.sample_rate

    @property
    def duration_s(self) -> float :
        return self.duration_samples / self.sample_rate


@dataclass(frozen = True)
class TranscriptSegment :
    segment_id : int
    start_s : float | None
    end_s : float | None
    text : str
    confidence : float | None = None


@dataclass(frozen = True)
class TranscriptionError :
    error_type : str
    message : str
    traceback : str | None = None


@dataclass(frozen = True)
class TranscriptionResult :
    window : PhysicalWindowSpec
    status : TranscriptionStatus
    raw_text : str
    native_segments : tuple[TranscriptSegment, ...]
    window_pcm_sha256 : str
    canonical_wav_sha256 : str
    model_name : str
    model_revision : str
    runtime_s : float
    peak_gpu_memory_bytes : int
    peak_reserved_memory_bytes : int
    warning_reasons : tuple[str, ...]
    resolved_arguments : dict[str, object]
    error : TranscriptionError | None = None


@dataclass(frozen = True)
class BoilerplateMatch :
    phrase : str
    start : int
    end : int


@dataclass(frozen = True)
class PostprocessOutput :
    normalized_text : str
    accent_folded_text : str
    retrieval_text : str
    warning_reasons : tuple[str, ...]
    rejection_reasons : tuple[str, ...]
    boilerplate_coverage : float
    boilerplate_matches : tuple[BoilerplateMatch, ...]
    postprocess_version : str


@dataclass(frozen = True)
class ProcessedTranscriptWindow :
    window : PhysicalWindowSpec
    status : TranscriptionStatus
    raw_text : str
    native_segments : tuple[TranscriptSegment, ...]
    normalized_text : str
    accent_folded_text : str
    retrieval_text : str
    warning_reasons : tuple[str, ...]
    rejection_reasons : tuple[str, ...]
    boilerplate_coverage : float
    boilerplate_matches : tuple[BoilerplateMatch, ...]
    postprocess_version : str
    eligible : bool
    window_pcm_sha256 : str
    canonical_wav_sha256 : str
    model_name : str
    model_revision : str
    runtime_s : float
    peak_gpu_memory_bytes : int
    peak_reserved_memory_bytes : int
    resolved_arguments : dict[str, object]
    error : TranscriptionError | None = None


@dataclass(frozen = True)
class PerVideoTranscriptArtifact :
    schema_version : str
    video : VideoSourceMetadata
    canonical_audio : CanonicalAudioMetadata
    window_policy_identity : str
    parakeet_identity : dict[str, object]
    postprocess_version : str
    created_at_utc : str
    updated_at_utc : str
    windows : tuple[ProcessedTranscriptWindow, ...]
    complete : bool


@dataclass(frozen = True)
class ReleaseVideoRecord :
    video_index : int
    video_id : str
    source_path : str
    source_size_bytes : int
    source_sha256 : str
    audio_stream_index : int
    duration_samples : int
    sample_rate : int
    first_physical_window : int
    physical_window_count : int


@dataclass(frozen = True)
class ReleaseWindowRecord :
    physical_index : int
    window_id : str
    video_id : str
    video_index : int
    window_index : int
    sample_start : int
    sample_end : int
    duration_samples : int
    sample_rate : int
    status : str
    raw_text : str
    retrieval_text : str
    eligible : bool
    warning_reasons : tuple[str, ...]
    rejection_reasons : tuple[str, ...]
    window_pcm_sha256 : str
    postprocess_version : str
    document_identity : str | None

    @property
    def start_s(self) -> float :
        return self.sample_start / self.sample_rate

    @property
    def end_s(self) -> float :
        return self.sample_end / self.sample_rate


@dataclass(frozen = True)
class CorpusManifest :
    schema_version : str
    release_id : str
    created_at_utc : str
    corpus_identity : str
    config_identity : str
    source_inventory_hash : str
    video_count : int
    physical_window_count : int
    eligible_window_count : int
    video_axis_sha256 : str
    physical_window_axis_sha256 : str
    eligible_window_axis_sha256 : str
    window_policy_identity : str
    parakeet_identity : dict[str, object]
    postprocess_version : str
    bm25_identity : dict[str, object]
    e5_identity : dict[str, object]
    embedding_shape : tuple[int, int]
    embedding_dtype : str
    file_hashes : dict[str, str]


SearchMode = Literal["first_stage", "reranked"]


@dataclass(frozen = True)
class ASRWindowHit :
    window_id : str
    video_id : str
    start_s : float
    end_s : float
    transcript : str
    first_stage_score : float
    reranker_score : float | None
    final_score : float | None
    reranked : bool


@dataclass(frozen = True)
class ASRVideoHit :
    rank : int
    video_id : str
    first_stage_rank : int
    first_stage_score : float
    reranker_score : float | None
    final_score : float | None
    reranked : bool
    windows : tuple[ASRWindowHit, ...]


@dataclass(frozen = True)
class SearchTimings :
    total_ms : float
    bm25_ms : float
    e5_encode_ms : float
    dense_search_ms : float
    first_stage_fusion_ms : float
    video_aggregation_ms : float
    candidate_selection_ms : float
    bge_ms : float
    candidate_fusion_ms : float
    result_build_ms : float
    candidate_pair_count : int
    reranker_batch_size : int | None


@dataclass(frozen = True)
class ASRSearchResult :
    query : str
    mode : SearchMode
    release_id : str
    hits : tuple[ASRVideoHit, ...]
    timings : SearchTimings
