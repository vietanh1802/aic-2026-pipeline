from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence
import gc

import numpy as np

from .config import E5Config


@dataclass(frozen = True)
class DenseEncodingSummary :
    item_count : int
    dimension : int
    effective_batch_size : int


class E5Encoder :
    def __init__(self, config : E5Config) :
        self.config = config
        self.model = None
        self._resolved_revision = config.revision

    @property
    def loaded(self) -> bool :
        return self.model is not None

    @property
    def resolved_revision(self) -> str :
        return self._resolved_revision

    def load(self) -> None :
        if (self.model is not None) :
            return

        import torch
        from sentence_transformers import SentenceTransformer

        if (self.config.device == "cuda" and not torch.cuda.is_available()) :
            raise RuntimeError(
                "E5 is configured for CUDA, but CUDA is not available. "
                "Select device='cpu' explicitly for CPU execution."
            )

        kwargs = {
            "revision" : self.config.revision,
            "device" : self.config.device,
        }
        if (self.config.model_cache_dir is not None) :
            kwargs["cache_folder"] = str(self.config.model_cache_dir)

        self.model = SentenceTransformer(
            self.config.model_name,
            **kwargs,
        )

        dimension = self._model_dimension()
        if (dimension != self.config.dimension) :
            raise RuntimeError(
                f"E5 dimension mismatch: model reports {dimension}, "
                f"configuration requires {self.config.dimension}"
            )

    def _model_dimension(self) -> int :
        if (self.model is None) :
            raise RuntimeError("E5 model is not loaded")
        getter = (
            getattr(self.model, "get_embedding_dimension", None)
            or getattr(self.model, "get_sentence_embedding_dimension", None)
        )
        if (getter is None) :
            raise RuntimeError("Could not determine E5 embedding dimension")
        return int(getter())

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
    def normalize_embeddings(values : np.ndarray, label : str) -> np.ndarray :
        embeddings = np.asarray(values, dtype = np.float32)
        if (embeddings.ndim != 2) :
            raise ValueError(f"{label} embeddings must be two-dimensional")
        if (not np.isfinite(embeddings).all()) :
            raise ValueError(f"{label} embeddings contain non-finite values")
        norms = np.linalg.norm(embeddings, axis = 1, keepdims = True)
        if (np.any(~np.isfinite(norms)) or np.any(norms <= 1e-12)) :
            raise ValueError(f"{label} embeddings contain zero or non-finite norms")
        normalized = np.asarray(embeddings / norms, dtype = np.float32)
        observed = np.linalg.norm(normalized, axis = 1)
        if (not np.allclose(observed, 1.0, atol = 1e-5, rtol = 1e-5)) :
            raise ValueError(f"{label} explicit L2 normalization failed")
        return np.ascontiguousarray(normalized, dtype = np.float32)

    def _encode_matrix(
        self,
        texts : Sequence[str],
        prefix : str,
        batch_size : int,
        label : str,
        show_progress_bar : bool,
    ) -> tuple[np.ndarray, int] :
        if (self.model is None) :
            raise RuntimeError("E5 model is not loaded")
        values = [prefix + str(text or "") for text in texts]
        if (not values) :
            raise ValueError(f"Cannot encode an empty {label} collection")

        effective_batch_size = int(batch_size)
        while True :
            try :
                raw = self.model.encode(
                    values,
                    batch_size = effective_batch_size,
                    show_progress_bar = show_progress_bar,
                    convert_to_numpy = True,
                    normalize_embeddings = False,
                )
                matrix = self.normalize_embeddings(np.asarray(raw, dtype = np.float32), label)
                if (matrix.shape[1] != self.config.dimension) :
                    raise ValueError(
                        f"{label} embedding dimension {matrix.shape[1]} "
                        f"does not match configured {self.config.dimension}"
                    )
                return matrix, effective_batch_size
            except RuntimeError as error :
                if (not self._is_oom(error) or effective_batch_size <= self.config.minimum_batch_size) :
                    raise
                next_batch = max(self.config.minimum_batch_size, effective_batch_size // 2)
                if (next_batch == effective_batch_size) :
                    raise
                effective_batch_size = next_batch
                self._clear_cuda()

    def encode_documents(
        self,
        document_ids : Sequence[str],
        texts : Sequence[str],
        show_progress_bar : bool = True,
    ) -> np.ndarray :
        if (len(document_ids) != len(texts)) :
            raise ValueError("E5 document IDs and texts have different lengths")
        if (len(set(str(value) for value in document_ids)) != len(document_ids)) :
            raise ValueError("E5 document IDs contain duplicates")
        matrix, _ = self._encode_matrix(
            texts,
            self.config.document_prefix,
            self.config.document_batch_size,
            "document",
            show_progress_bar,
        )
        return matrix

    def encode_query(self, query : str) -> np.ndarray :
        text = str(query).strip()
        if (not text) :
            raise ValueError("Query must not be empty")
        matrix, _ = self._encode_matrix(
            [text],
            self.config.query_prefix,
            1,
            "query",
            False,
        )
        return matrix[0]

    def close(self) -> None :
        self.model = None
        gc.collect()
        self._clear_cuda()

    def __enter__(self) -> "E5Encoder" :
        self.load()
        return self

    def __exit__(self, exc_type, exc_value, exc_traceback) -> None :
        self.close()


def exact_dense_scores(
    query_embedding : np.ndarray,
    document_embeddings : np.ndarray,
) -> np.ndarray :
    query = np.asarray(query_embedding, dtype = np.float32)
    documents = np.asarray(document_embeddings, dtype = np.float32)
    if (query.ndim != 1) :
        raise ValueError("Query embedding must be one-dimensional")
    if (documents.ndim != 2) :
        raise ValueError("Document embeddings must be two-dimensional")
    if (documents.shape[1] != query.shape[0]) :
        raise ValueError("Dense embedding dimensions do not match")
    if (not np.isfinite(query).all() or not np.isfinite(documents).all()) :
        raise ValueError("Dense embeddings contain non-finite values")
    scores = np.asarray(documents @ query, dtype = np.float32)
    if (not np.isfinite(scores).all()) :
        raise ValueError("Dense scoring produced non-finite values")
    if (np.any(scores < -1.0001) or np.any(scores > 1.0001)) :
        raise ValueError("Dense cosine scores fall outside expected range")
    return scores
