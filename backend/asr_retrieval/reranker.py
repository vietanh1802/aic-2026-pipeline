from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Sequence
import gc
import time

import numpy as np

from .config import BGEConfig


@dataclass(frozen = True)
class RerankerOutput :
    scores : np.ndarray
    runtime_s : float
    pair_count : int
    effective_batch_size : int
    oom_retries : int

    def __post_init__(self) -> None :
        values = np.asarray(self.scores, dtype = np.float32).reshape(-1)
        object.__setattr__(self, "scores", values)
        if (values.shape != (self.pair_count,)) :
            raise ValueError("Reranker score count does not match pair_count")
        if (not np.isfinite(values).all()) :
            raise ValueError("Reranker produced non-finite scores")
        if (self.runtime_s < 0) :
            raise ValueError("Reranker runtime must be nonnegative")
        if (self.effective_batch_size <= 0) :
            raise ValueError("Reranker effective batch size must be positive")
        if (self.oom_retries < 0) :
            raise ValueError("Reranker OOM retry count must be nonnegative")


class BGEReranker :
    def __init__(self, config : BGEConfig) :
        self.config = config
        self.model = None
        self._resolved_revision = config.revision
        self.last_batch_size : int | None = None
        self.oom_count = 0

    @property
    def loaded(self) -> bool :
        return self.model is not None

    @property
    def resolved_revision(self) -> str :
        return self._resolved_revision

    @staticmethod
    def _is_oom(error : RuntimeError) -> bool :
        message = str(error).lower()
        return "out of memory" in message or "cuda error: out of memory" in message

    @staticmethod
    def _clear_cuda() -> None :
        try :
            import torch
            if (torch.cuda.is_available()) :
                torch.cuda.empty_cache()
        except Exception :
            pass

    @staticmethod
    def _synchronize_cuda() -> None :
        try :
            import torch
            if (torch.cuda.is_available()) :
                torch.cuda.synchronize()
        except Exception :
            pass

    def load(self) -> None :
        if (self.model is not None) :
            return

        import torch
        from sentence_transformers import CrossEncoder

        if (self.config.device == "cuda" and not torch.cuda.is_available()) :
            raise RuntimeError(
                "BGE is configured for CUDA, but CUDA is not available. "
                "Select device='cpu' explicitly for CPU execution."
            )

        torch_dtype = torch.float16 if self.config.dtype == "float16" else torch.float32
        model_kwargs = {"torch_dtype" : torch_dtype}
        kwargs = {
            "revision" : self.config.revision,
            "device" : self.config.device,
            "max_length" : self.config.max_length,
            "trust_remote_code" : False,
            "model_kwargs" : model_kwargs,
            "activation_fn" : torch.nn.Identity(),
        }
        if (self.config.model_cache_dir is not None) :
            kwargs["cache_folder"] = str(Path(self.config.model_cache_dir))

        self.model = CrossEncoder(
            self.config.model_name,
            **kwargs,
        )

        inner = getattr(self.model, "model", None)
        model_config = getattr(inner, "config", None)
        resolved = getattr(model_config, "_commit_hash", None)
        if (resolved is not None) :
            self._resolved_revision = str(resolved)
            if (self._resolved_revision != self.config.revision) :
                self.close()
                raise RuntimeError(
                    f"BGE resolved revision {self._resolved_revision!r} does not match "
                    f"pinned revision {self.config.revision!r}"
                )

    def _batch_candidates(self) -> tuple[int, ...] :
        values = (self.config.preferred_batch_size, *self.config.fallback_batch_sizes)
        return tuple(dict.fromkeys(int(value) for value in values))

    def score_pairs(
        self,
        pairs : Sequence[tuple[str, str]],
        show_progress_bar : bool = False,
    ) -> RerankerOutput :
        values = [(str(query), str(document)) for query, document in pairs]
        if (not values) :
            raise ValueError("BGE cannot score an empty pair list")
        if (self.model is None) :
            raise RuntimeError("BGE model is not loaded")

        last_oom : RuntimeError | None = None
        retries = 0

        for batch_size in self._batch_candidates() :
            try :
                self._synchronize_cuda()
                started = time.perf_counter()
                raw = self.model.predict(
                    values,
                    batch_size = batch_size,
                    show_progress_bar = show_progress_bar,
                    convert_to_numpy = True,
                )
                self._synchronize_cuda()
                runtime_s = time.perf_counter() - started
                scores = np.asarray(raw, dtype = np.float32)
                if (scores.ndim == 2 and scores.shape[1] == 1) :
                    scores = scores[:, 0]
                if (scores.ndim != 1 or scores.shape != (len(values),)) :
                    raise ValueError(
                        f"BGE expected one raw scalar per pair, received shape {scores.shape}"
                    )
                if (not np.isfinite(scores).all()) :
                    raise ValueError("BGE produced non-finite raw logits")
                self.last_batch_size = batch_size
                return RerankerOutput(
                    scores = scores,
                    runtime_s = runtime_s,
                    pair_count = len(values),
                    effective_batch_size = batch_size,
                    oom_retries = retries,
                )
            except RuntimeError as error :
                if (not self._is_oom(error)) :
                    raise
                last_oom = error
                retries += 1
                self.oom_count += 1
                self._clear_cuda()

        raise RuntimeError(
            "BGE reranking failed with CUDA OOM at every configured batch size"
        ) from last_oom

    def warmup(self) -> float :
        output = self.score_pairs([
            (
                "một đoạn video có lời nói tiếng Việt",
                "đây là một đoạn lời nói tiếng Việt",
            )
        ])
        return float(output.runtime_s)

    def close(self) -> None :
        self.model = None
        gc.collect()
        self._clear_cuda()

    def __enter__(self) -> "BGEReranker" :
        self.load()
        return self

    def __exit__(self, exc_type, exc_value, exc_traceback) -> None :
        self.close()
