from __future__ import annotations

from dataclasses import asdict, dataclass, field
from hashlib import sha256
from pathlib import Path
from typing import Any, Literal
import json


PRODUCTION_SCHEMA_VERSION = "1.0"


@dataclass(frozen = True)
class AudioWindowConfig :
    sample_rate : int = 16_000
    channels : int = 1
    sample_width_bytes : int = 2
    window_samples : int = 960_000
    stride_samples : int = 720_000
    minimum_tail_samples : int = 240_000

    def __post_init__(self) -> None :
        if (self.sample_rate <= 0) :
            raise ValueError("sample_rate must be positive")
        if (self.channels != 1) :
            raise ValueError("canonical audio must be mono")
        if (self.sample_width_bytes != 2) :
            raise ValueError("canonical audio must use 16-bit PCM")
        if (self.window_samples != 60 * self.sample_rate) :
            raise ValueError("window_samples must represent exactly 60 seconds")
        if (self.stride_samples != 45 * self.sample_rate) :
            raise ValueError("stride_samples must represent exactly 45 seconds")
        if (self.minimum_tail_samples != 15 * self.sample_rate) :
            raise ValueError("minimum_tail_samples must represent exactly 15 seconds")
        if (self.stride_samples >= self.window_samples) :
            raise ValueError("stride_samples must be smaller than window_samples")

    @property
    def window_seconds(self) -> float :
        return self.window_samples / self.sample_rate

    @property
    def stride_seconds(self) -> float :
        return self.stride_samples / self.sample_rate

    @property
    def minimum_tail_seconds(self) -> float :
        return self.minimum_tail_samples / self.sample_rate


@dataclass(frozen = True)
class ParakeetConfig :
    model_name : str = "nvidia/parakeet-ctc-0.6b-Vietnamese"
    model_filename : str = "parakeet-ctc-0.6b-vi.nemo"
    revision : str = "b0493142b49458810324e3db8be9e8e07b4ebc17"
    device : Literal["cuda", "cpu"] = "cuda"
    timestamps : bool = True
    decoder : str = "greedy_ctc"
    dtype : str = "float32"
    batch_size : int = 1
    model_cache_dir : Path | None = None

    def __post_init__(self) -> None :
        if (not self.model_name.strip()) :
            raise ValueError("model_name must not be empty")
        if (not self.model_filename.strip()) :
            raise ValueError("model_filename must not be empty")
        if (not self.revision.strip()) :
            raise ValueError("revision must be pinned")
        if (not self.timestamps) :
            raise ValueError("Parakeet production inference requires timestamps=True")
        if (self.batch_size != 1) :
            raise ValueError("Parakeet production inference uses independent batch_size=1 windows")
        if (self.decoder != "greedy_ctc") :
            raise ValueError("Parakeet production decoder must be greedy_ctc")
        if (self.dtype != "float32") :
            raise ValueError("Parakeet production dtype must be float32")


@dataclass(frozen = True)
class OfflineASRConfig :
    schema_version : str = PRODUCTION_SCHEMA_VERSION
    audio : AudioWindowConfig = field(default_factory = AudioWindowConfig)
    parakeet : ParakeetConfig = field(default_factory = ParakeetConfig)

    def __post_init__(self) -> None :
        if (self.schema_version != PRODUCTION_SCHEMA_VERSION) :
            raise ValueError(
                f"Unsupported schema_version {self.schema_version!r}; "
                f"expected {PRODUCTION_SCHEMA_VERSION!r}"
            )


def _canonicalize(value : Any) -> Any :
    if (isinstance(value, Path)) :
        return str(value)
    if (isinstance(value, dict)) :
        return {
            str(key) : _canonicalize(item)
            for key, item in value.items()
        }
    if (isinstance(value, (list, tuple)) ) :
        return [_canonicalize(item) for item in value]
    return value


def config_to_canonical_dict(config : OfflineASRConfig) -> dict[str, Any] :
    payload = asdict(config)
    payload["parakeet"].pop("model_cache_dir", None)
    return _canonicalize(payload)


def config_identity(config : OfflineASRConfig) -> str :
    serialized = json.dumps(
        config_to_canonical_dict(config),
        ensure_ascii = False,
        sort_keys = True,
        separators = (",", ":"),
        allow_nan = False,
    ).encode("utf-8")
    return sha256(serialized).hexdigest()


def window_policy_identity(config : AudioWindowConfig) -> str :
    payload = {
        "sample_rate" : config.sample_rate,
        "channels" : config.channels,
        "sample_width_bytes" : config.sample_width_bytes,
        "window_samples" : config.window_samples,
        "stride_samples" : config.stride_samples,
        "minimum_tail_samples" : config.minimum_tail_samples,
    }
    serialized = json.dumps(
        payload,
        sort_keys = True,
        separators = (",", ":"),
        allow_nan = False,
    ).encode("utf-8")
    return sha256(serialized).hexdigest()


def parakeet_identity(config : ParakeetConfig) -> dict[str, Any] :
    return {
        "model_name" : config.model_name,
        "model_filename" : config.model_filename,
        "revision" : config.revision,
        "timestamps" : config.timestamps,
        "decoder" : config.decoder,
        "dtype" : config.dtype,
        "batch_size" : config.batch_size,
    }


@dataclass(frozen = True)
class BM25Config :
    k1 : float = 1.5
    b : float = 0.75
    unique_query_terms : bool = True
    normalization_id : str = "accent_preserving_whitespace_v1"
    idf_policy : str = "log1p_positive_okapi"

    def __post_init__(self) -> None :
        if (self.k1 <= 0) :
            raise ValueError("BM25 k1 must be positive")
        if (not 0.0 <= self.b <= 1.0) :
            raise ValueError("BM25 b must be within [0, 1]")
        if (not self.unique_query_terms) :
            raise ValueError("Production BM25 requires unique query terms")
        if (self.normalization_id != "accent_preserving_whitespace_v1") :
            raise ValueError("Unsupported BM25 normalization_id")
        if (self.idf_policy != "log1p_positive_okapi") :
            raise ValueError("Unsupported BM25 idf_policy")


@dataclass(frozen = True)
class E5Config :
    model_name : str = "intfloat/multilingual-e5-large-instruct"
    revision : str = "274baa43b0e13e37fafa6428dbc7938e62e5c439"
    query_prefix : str = (
        "Instruct: Given a detailed description of a target video moment, "
        "retrieve transcript passages that are relevant to the described event.\n"
        "Query: "
    )
    document_prefix : str = ""
    dimension : int = 1024
    normalization_id : str = "explicit_l2_float32_v1"
    document_batch_size : int = 16
    minimum_batch_size : int = 1
    device : Literal["cuda", "cpu"] = "cuda"
    model_cache_dir : Path | None = None

    def __post_init__(self) -> None :
        if (not self.model_name.strip()) :
            raise ValueError("E5 model_name must not be empty")
        if (len(self.revision.strip()) != 40) :
            raise ValueError("E5 revision must be an exact 40-character commit SHA")
        if (not self.query_prefix) :
            raise ValueError("E5 query_prefix must not be empty")
        if (self.document_prefix != "") :
            raise ValueError("Production E5 document_prefix must remain empty")
        if (self.dimension <= 0) :
            raise ValueError("E5 dimension must be positive")
        if (self.normalization_id != "explicit_l2_float32_v1") :
            raise ValueError("Unsupported E5 normalization policy")
        if (self.document_batch_size <= 0) :
            raise ValueError("E5 document_batch_size must be positive")
        if (self.minimum_batch_size <= 0 or self.minimum_batch_size > self.document_batch_size) :
            raise ValueError("E5 minimum_batch_size must be within [1, document_batch_size]")


@dataclass(frozen = True)
class ArtifactConfig :
    schema_version : str = "1.0"
    verify_file_hashes : bool = True
    load_embeddings_into_ram : bool = True

    def __post_init__(self) -> None :
        if (self.schema_version != "1.0") :
            raise ValueError("Unsupported artifact schema_version")


@dataclass(frozen = True)
class CorpusBuildConfig :
    schema_version : str = PRODUCTION_SCHEMA_VERSION
    offline : OfflineASRConfig = field(default_factory = OfflineASRConfig)
    bm25 : BM25Config = field(default_factory = BM25Config)
    e5 : E5Config = field(default_factory = E5Config)
    artifacts : ArtifactConfig = field(default_factory = ArtifactConfig)

    def __post_init__(self) -> None :
        if (self.schema_version != PRODUCTION_SCHEMA_VERSION) :
            raise ValueError(
                f"Unsupported schema_version {self.schema_version!r}; "
                f"expected {PRODUCTION_SCHEMA_VERSION!r}"
            )


def corpus_build_config_to_canonical_dict(config : CorpusBuildConfig) -> dict[str, Any] :
    payload = asdict(config)
    payload["offline"]["parakeet"].pop("model_cache_dir", None)
    payload["offline"]["parakeet"].pop("device", None)
    payload["e5"].pop("model_cache_dir", None)
    payload["e5"].pop("device", None)
    payload["e5"].pop("document_batch_size", None)
    payload["e5"].pop("minimum_batch_size", None)
    return _canonicalize(payload)


def corpus_build_config_identity(config : CorpusBuildConfig) -> str :
    serialized = json.dumps(
        corpus_build_config_to_canonical_dict(config),
        ensure_ascii = False,
        sort_keys = True,
        separators = (",", ":"),
        allow_nan = False,
    ).encode("utf-8")
    return sha256(serialized).hexdigest()


def bm25_identity(config : BM25Config) -> dict[str, Any] :
    return {
        "k1" : config.k1,
        "b" : config.b,
        "unique_query_terms" : config.unique_query_terms,
        "normalization_id" : config.normalization_id,
        "idf_policy" : config.idf_policy,
    }


def e5_identity(config : E5Config) -> dict[str, Any] :
    return {
        "model_name" : config.model_name,
        "revision" : config.revision,
        "query_prefix" : config.query_prefix,
        "document_prefix" : config.document_prefix,
        "dimension" : config.dimension,
        "normalization_id" : config.normalization_id,
        "embedding_dtype" : "float32",
    }


@dataclass(frozen = True)
class FusionConfig :
    bm25_weight : float = 0.25
    dense_weight : float = 0.75
    first_stage_weight : float = 0.50
    reranker_weight : float = 0.50
    constant_score_tolerance : float = 1e-12

    def __post_init__(self) -> None :
        for name, value in [
            ("bm25_weight", self.bm25_weight),
            ("dense_weight", self.dense_weight),
            ("first_stage_weight", self.first_stage_weight),
            ("reranker_weight", self.reranker_weight),
        ] :
            if (value < 0) :
                raise ValueError(f"{name} must be nonnegative")

        if (abs((self.bm25_weight + self.dense_weight) - 1.0) > 1e-12) :
            raise ValueError("BM25 and dense fusion weights must sum to 1")
        if (abs((self.first_stage_weight + self.reranker_weight) - 1.0) > 1e-12) :
            raise ValueError("First-stage and reranker fusion weights must sum to 1")
        if (self.constant_score_tolerance < 0) :
            raise ValueError("constant_score_tolerance must be nonnegative")


@dataclass(frozen = True)
class CandidateConfig :
    video_k : int = 50
    windows_per_video : int = 3
    max_candidate_pairs : int = 150

    def __post_init__(self) -> None :
        if (self.video_k <= 0) :
            raise ValueError("video_k must be positive")
        if (self.windows_per_video <= 0) :
            raise ValueError("windows_per_video must be positive")
        if (self.max_candidate_pairs <= 0) :
            raise ValueError("max_candidate_pairs must be positive")
        if (self.video_k > self.max_candidate_pairs) :
            raise ValueError(
                "video_k cannot exceed max_candidate_pairs because every candidate "
                "video must be able to receive at least one reranker pair"
            )


@dataclass(frozen = True)
class BGEConfig :
    model_name : str = "BAAI/bge-reranker-v2-m3"
    revision : str = "953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e"
    device : Literal["cuda", "cpu"] = "cuda"
    dtype : Literal["float16", "float32"] = "float16"
    max_length : int = 512
    preferred_batch_size : int = 32
    fallback_batch_sizes : tuple[int, ...] = (16, 8, 4)
    model_cache_dir : Path | None = None

    def __post_init__(self) -> None :
        if (not self.model_name.strip()) :
            raise ValueError("BGE model_name must not be empty")
        if (len(self.revision.strip()) != 40) :
            raise ValueError("BGE revision must be an exact 40-character commit SHA")
        if (self.device == "cpu" and self.dtype == "float16") :
            raise ValueError("BGE float16 execution requires CUDA; use float32 on CPU")
        if (self.max_length <= 0) :
            raise ValueError("BGE max_length must be positive")
        if (self.preferred_batch_size <= 0) :
            raise ValueError("BGE preferred_batch_size must be positive")
        if (any(value <= 0 for value in self.fallback_batch_sizes)) :
            raise ValueError("BGE fallback batch sizes must be positive")
        if (any(value >= self.preferred_batch_size for value in self.fallback_batch_sizes)) :
            raise ValueError("BGE fallback batch sizes must be smaller than the preferred batch size")
        if (tuple(sorted(self.fallback_batch_sizes, reverse = True)) != self.fallback_batch_sizes) :
            raise ValueError("BGE fallback batch sizes must be strictly descending")
        if (len(set(self.fallback_batch_sizes)) != len(self.fallback_batch_sizes)) :
            raise ValueError("BGE fallback batch sizes must not contain duplicates")


@dataclass(frozen = True)
class RuntimeConfig :
    e5_device : Literal["cuda", "cpu"] = "cuda"
    load_reranker : bool = True
    serialize_gpu_requests : bool = True
    warmup_query : str = "một đoạn video có lời nói tiếng Việt"
    default_top_k : int = 50
    default_windows_per_hit : int = 3

    def __post_init__(self) -> None :
        if (not self.warmup_query.strip()) :
            raise ValueError("warmup_query must not be empty")
        if (self.default_top_k <= 0) :
            raise ValueError("default_top_k must be positive")
        if (self.default_windows_per_hit <= 0) :
            raise ValueError("default_windows_per_hit must be positive")


@dataclass(frozen = True)
class ProductionConfig :
    fusion : FusionConfig = field(default_factory = FusionConfig)
    candidates : CandidateConfig = field(default_factory = CandidateConfig)
    bge : BGEConfig = field(default_factory = BGEConfig)
    runtime : RuntimeConfig = field(default_factory = RuntimeConfig)
    artifacts : ArtifactConfig = field(default_factory = ArtifactConfig)


def bge_identity(config : BGEConfig) -> dict[str, Any] :
    return {
        "model_name" : config.model_name,
        "revision" : config.revision,
        "dtype" : config.dtype,
        "max_length" : config.max_length,
        "score_activation" : "identity_raw_logit",
    }


def fusion_identity(config : FusionConfig) -> dict[str, Any] :
    return {
        "bm25_weight" : config.bm25_weight,
        "dense_weight" : config.dense_weight,
        "first_stage_weight" : config.first_stage_weight,
        "reranker_weight" : config.reranker_weight,
        "constant_score_tolerance" : config.constant_score_tolerance,
        "normalization" : "per_query_minmax_v1",
    }


def candidate_identity(config : CandidateConfig) -> dict[str, Any] :
    return {
        "video_k" : config.video_k,
        "windows_per_video" : config.windows_per_video,
        "max_candidate_pairs" : config.max_candidate_pairs,
        "allocation" : "breadth_first_by_window_rank_v1",
    }
