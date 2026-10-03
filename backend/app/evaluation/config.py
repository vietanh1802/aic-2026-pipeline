# backend/app/evaluation/config.py
"""One typed run configuration for the ablation benchmark.

Defaults equal what the production UI sends for a normal search (queryStore.ts and
EnsembleSearchRequest in main.py): all three encoders, per-model neighbour rerank, top_k 100,
top_m 50. The one deliberate difference is text_policy: production has no automatic text
step (the operator presses Translate, Expand or neither), so the benchmark baseline is the
server-side gtx translation, which needs no key.

A run stores this twice in evaluation_runs.configuration_json: the legacy flat keys the
existing Benchmark page reads (models, top_k, top_m, use_rerank, translation_policy) and the
full object under "config". Old runs have no "config" key and keep running through the legacy
path in runner.py.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

ModelName = Literal["beit3", "clip", "siglip2"]
TextPolicy = Literal["raw_vi", "translate_gtx", "expand_gemini"]
RerankMode = Literal["per_model", "after_fusion", "off"]

# Canonical order = MODEL_NAMES in preprocess.py = the order the UI sends. _merge_ensemble breaks
# score ties by insertion order, so the order of `models` is part of the result.
CANONICAL_MODELS : tuple[str, ...] = ("beit3", "clip", "siglip2")

CONFIG_SCHEMA_VERSION = 1


class TrakeConfig(BaseModel) :
    top_videos        : int   = Field(20, ge = 1, le = 100)    # K, the UI sends 20
    gap_c             : int   = Field(60, ge = 1, le = 600)    # g in seconds, the UI sends 60
    min_score         : float = 0.10                           # accepted and unused by the code path
    local_model       : ModelName = "clip"                     # UI default, not an arm
    event_tolerance_s : float = 5.0                            # per-event correctness window


class TextFilterConfig(BaseModel) :
    """Annotation only: OCR and ASR matching never changes a ranking."""
    sources  : list[Literal["ocr", "asr"]] = []
    asr_mode : Literal["substring", "bm25"] = "substring"
    ocr_mode : Literal["substring"] = "substring"
    cue_set  : str | None = None
    what_if  : Literal["inject_exact_top10"] | None = None     # not shipped, labelled in outputs


class QuerySubset(BaseModel) :
    task_types    : list[Literal["KIS", "QA", "TRAKE"]] | None = None
    exclude_flags : list[str] = []
    # The first N queries of each dataset, for smoke tests. Part of the config hash, so a smoke run
    # can never be mistaken for a full one.
    limit_queries : int | None = Field(None, ge = 1)


class RunConfig(BaseModel) :
    name        : str = "baseline"
    models      : list[ModelName] = list(CANONICAL_MODELS)
    rerank_mode : RerankMode = "per_model"
    top_k       : int = Field(100, ge = 1, le = 500)
    top_m       : int = Field(50, ge = 1, le = 200)
    text_policy : TextPolicy = "translate_gtx"
    task_mode   : Literal["ensemble", "trake_n"] = "ensemble"
    trake       : TrakeConfig = Field(default_factory = TrakeConfig)
    text_filter : TextFilterConfig = Field(default_factory = TextFilterConfig)
    subset      : QuerySubset = Field(default_factory = QuerySubset)

    @field_validator("models")
    @classmethod
    def _models(cls, models : list[str]) -> list[str] :
        if (not models) :
            raise ValueError("models must not be empty")
        if (len(set(models)) != len(models)) :
            raise ValueError("models must not contain duplicates")
        return [name for name in CANONICAL_MODELS if name in models]

    @model_validator(mode = "after")
    def _cross_checks(self) -> "RunConfig" :
        if (self.task_mode == "trake_n") :
            # trake_search_candidates runs discovery over every active encoder with rerank on and
            # lives in preprocess.py, so neither can be varied from here.
            if (self.models != list(CANONICAL_MODELS) or self.rerank_mode != "per_model") :
                raise ValueError("trake_n requires all three models and rerank_mode per_model")
            self.subset.task_types = ["TRAKE"]
        if (self.text_filter.what_if and not self.text_filter.sources) :
            raise ValueError("what_if requires text_filter.sources")
        return self

    @property
    def use_rerank(self) -> bool :
        """Legacy boolean for old readers: anything but "off" reranks."""
        return self.rerank_mode != "off"


def canonical_json(config : RunConfig) -> str :
    return json.dumps(config.model_dump(), sort_keys = True, separators = (",", ":"), ensure_ascii = False)


def config_hash(config : RunConfig) -> str :
    # The display name is not part of what was measured.
    payload = config.model_dump()
    payload.pop("name", None)
    canonical = json.dumps(payload, sort_keys = True, separators = (",", ":"), ensure_ascii = False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def to_configuration(config : RunConfig) -> dict[str, Any] :
    """What goes into configuration_json: legacy flat keys plus the full object."""
    return {
        "models"             : list(config.models),
        "top_k"              : config.top_k,
        "top_m"              : config.top_m,
        "use_rerank"         : config.use_rerank,
        "translation_policy" : config.text_policy,
        "schema_version"     : CONFIG_SCHEMA_VERSION,
        "config"             : config.model_dump(),
        "config_hash"        : config_hash(config),
    }


def config_from_configuration(configuration : dict[str, Any] | None) -> RunConfig | None :
    """The RunConfig of a stored run, or None for a legacy run without one."""
    block = (configuration or {}).get("config")
    return RunConfig.model_validate(block) if block else None
