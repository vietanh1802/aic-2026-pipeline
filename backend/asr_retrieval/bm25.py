from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence
import json
import math

import numpy as np

from .config import BM25Config
from .postprocess import normalize_for_matching


BM25_FORMAT_VERSION = "1.0"


def tokenize(text : str) -> tuple[str, ...] :
    normalized = normalize_for_matching(text)
    return tuple(token for token in normalized.split() if token)


@dataclass(frozen = True)
class PersistentBM25Index :
    vocabulary : tuple[str, ...]
    token_to_id : dict[str, int]
    document_lengths : np.ndarray
    posting_offsets : np.ndarray
    posting_doc_ids : np.ndarray
    posting_term_frequencies : np.ndarray
    average_document_length : float
    k1 : float
    b : float

    def __post_init__(self) -> None :
        document_lengths = np.asarray(self.document_lengths)
        posting_offsets = np.asarray(self.posting_offsets)
        posting_doc_ids = np.asarray(self.posting_doc_ids)
        posting_term_frequencies = np.asarray(self.posting_term_frequencies)

        if (not self.vocabulary) :
            raise ValueError("BM25 vocabulary must not be empty")
        if (len(self.vocabulary) != len(set(self.vocabulary))) :
            raise ValueError("BM25 vocabulary contains duplicates")
        if (self.token_to_id != {token : index for index, token in enumerate(self.vocabulary)}) :
            raise ValueError("BM25 token_to_id does not match vocabulary order")
        if (document_lengths.ndim != 1 or len(document_lengths) == 0) :
            raise ValueError("BM25 document_lengths must be a nonempty vector")
        if (np.any(document_lengths <= 0)) :
            raise ValueError("BM25 document lengths must be positive")
        if (posting_offsets.shape != (len(self.vocabulary) + 1,)) :
            raise ValueError("BM25 posting_offsets length mismatch")
        if (posting_offsets[0] != 0) :
            raise ValueError("BM25 posting_offsets must start at zero")
        if (np.any(posting_offsets[1:] < posting_offsets[:-1])) :
            raise ValueError("BM25 posting_offsets must be monotonic")
        posting_count = int(posting_offsets[-1])
        if (posting_doc_ids.shape != (posting_count,)) :
            raise ValueError("BM25 posting_doc_ids length mismatch")
        if (posting_term_frequencies.shape != (posting_count,)) :
            raise ValueError("BM25 posting_term_frequencies length mismatch")
        if (posting_count and (np.any(posting_doc_ids < 0) or np.any(posting_doc_ids >= len(document_lengths)))) :
            raise ValueError("BM25 posting document ID outside document axis")
        if (np.any(posting_term_frequencies <= 0)) :
            raise ValueError("BM25 posting term frequencies must be positive")
        if (not math.isfinite(self.average_document_length) or self.average_document_length <= 0) :
            raise ValueError("BM25 average_document_length must be positive and finite")
        if (self.k1 <= 0 or not 0 <= self.b <= 1) :
            raise ValueError("Invalid BM25 parameters")

        for token_id in range(len(self.vocabulary)) :
            start = int(posting_offsets[token_id])
            end = int(posting_offsets[token_id + 1])
            ids = posting_doc_ids[start : end]
            if (len(ids) > 1 and np.any(ids[1:] <= ids[:-1])) :
                raise ValueError("BM25 postings must use strictly increasing document IDs")

    @property
    def document_count(self) -> int :
        return int(len(self.document_lengths))

    def score(self, query : str) -> np.ndarray :
        return score_bm25(self, query)


def build_bm25_index(
    eligible_document_ids : Sequence[str],
    documents : Sequence[str],
    config : BM25Config,
) -> PersistentBM25Index :
    document_ids = [str(value) for value in eligible_document_ids]
    texts = [str(value or "") for value in documents]

    if (len(document_ids) != len(texts)) :
        raise ValueError("BM25 document IDs and texts have different lengths")
    if (not document_ids) :
        raise ValueError("BM25 requires at least one eligible document")
    if (len(document_ids) != len(set(document_ids))) :
        raise ValueError("BM25 document IDs contain duplicates")

    tokenized = [tokenize(text) for text in texts]
    if (any(not tokens for tokens in tokenized)) :
        raise ValueError("Eligible BM25 documents must remain nonempty after tokenization")

    document_lengths = np.asarray(
        [len(tokens) for tokens in tokenized],
        dtype = np.uint32,
    )
    vocabulary = tuple(sorted({token for tokens in tokenized for token in tokens}))
    token_to_id = {token : index for index, token in enumerate(vocabulary)}
    postings_docs : list[list[int]] = [[] for _ in vocabulary]
    postings_tf : list[list[int]] = [[] for _ in vocabulary]

    for document_index, tokens in enumerate(tokenized) :
        counts = Counter(tokens)
        for token, frequency in counts.items() :
            token_id = token_to_id[token]
            postings_docs[token_id].append(document_index)
            postings_tf[token_id].append(int(frequency))

    posting_offsets = np.zeros(len(vocabulary) + 1, dtype = np.uint64)
    posting_doc_values = []
    posting_tf_values = []

    for token_id in range(len(vocabulary)) :
        posting_doc_values.extend(postings_docs[token_id])
        posting_tf_values.extend(postings_tf[token_id])
        posting_offsets[token_id + 1] = len(posting_doc_values)

    posting_doc_ids = np.asarray(posting_doc_values, dtype = np.uint32)
    posting_term_frequencies = np.asarray(posting_tf_values, dtype = np.uint32)

    return PersistentBM25Index(
        vocabulary = vocabulary,
        token_to_id = token_to_id,
        document_lengths = document_lengths,
        posting_offsets = posting_offsets,
        posting_doc_ids = posting_doc_ids,
        posting_term_frequencies = posting_term_frequencies,
        average_document_length = float(document_lengths.astype(np.float64).mean()),
        k1 = float(config.k1),
        b = float(config.b),
    )


def score_bm25(index : PersistentBM25Index, query : str) -> np.ndarray :
    scores = np.zeros(index.document_count, dtype = np.float32)
    query_tokens = tokenize(query)
    unique_tokens = tuple(dict.fromkeys(query_tokens))
    document_lengths = index.document_lengths.astype(np.float64, copy = False)

    for token in unique_tokens :
        token_id = index.token_to_id.get(token)
        if (token_id is None) :
            continue

        start = int(index.posting_offsets[token_id])
        end = int(index.posting_offsets[token_id + 1])
        if (start == end) :
            continue

        doc_ids = index.posting_doc_ids[start : end].astype(np.int64, copy = False)
        frequencies = index.posting_term_frequencies[start : end].astype(np.float64, copy = False)
        df = end - start
        n = index.document_count
        idf = math.log(1.0 + (n - df + 0.5) / (df + 0.5))
        lengths = document_lengths[doc_ids]
        denominator = frequencies + index.k1 * (
            1.0 - index.b
            + index.b * lengths / index.average_document_length
        )
        contributions = idf * (
            frequencies * (index.k1 + 1.0)
            / denominator
        )
        scores[doc_ids] += contributions.astype(np.float32)

    if (not np.isfinite(scores).all()) :
        raise ValueError("BM25 produced non-finite scores")
    if (np.any(scores < 0)) :
        raise ValueError("BM25 produced negative scores")
    return scores


def save_bm25_index(index : PersistentBM25Index, directory : Path) -> None :
    directory = Path(directory)
    directory.mkdir(parents = True, exist_ok = True)
    (directory / "vocabulary.json").write_text(
        json.dumps(
            {
                "format_version" : BM25_FORMAT_VERSION,
                "tokens" : list(index.vocabulary),
            },
            ensure_ascii = False,
            indent = 2,
            allow_nan = False,
        ),
        encoding = "utf-8",
    )
    np.save(directory / "document_lengths.npy", np.asarray(index.document_lengths, dtype = np.uint32), allow_pickle = False)
    np.save(directory / "posting_offsets.npy", np.asarray(index.posting_offsets, dtype = np.uint64), allow_pickle = False)
    np.save(directory / "posting_doc_ids.npy", np.asarray(index.posting_doc_ids, dtype = np.uint32), allow_pickle = False)
    np.save(directory / "posting_term_frequencies.npy", np.asarray(index.posting_term_frequencies, dtype = np.uint32), allow_pickle = False)


def load_bm25_index(
    directory : Path,
    expected_document_count : int,
    config : BM25Config,
) -> PersistentBM25Index :
    directory = Path(directory)
    vocabulary_payload = json.loads((directory / "vocabulary.json").read_text(encoding = "utf-8"))
    if (vocabulary_payload.get("format_version") != BM25_FORMAT_VERSION) :
        raise ValueError("Unsupported BM25 artifact format")
    vocabulary = tuple(str(token) for token in vocabulary_payload.get("tokens", []))
    token_to_id = {token : index for index, token in enumerate(vocabulary)}
    document_lengths = np.load(directory / "document_lengths.npy", allow_pickle = False)
    posting_offsets = np.load(directory / "posting_offsets.npy", allow_pickle = False)
    posting_doc_ids = np.load(directory / "posting_doc_ids.npy", allow_pickle = False)
    posting_term_frequencies = np.load(directory / "posting_term_frequencies.npy", allow_pickle = False)

    if (len(document_lengths) != int(expected_document_count)) :
        raise ValueError("BM25 document axis does not match eligible window count")

    return PersistentBM25Index(
        vocabulary = vocabulary,
        token_to_id = token_to_id,
        document_lengths = np.asarray(document_lengths, dtype = np.uint32),
        posting_offsets = np.asarray(posting_offsets, dtype = np.uint64),
        posting_doc_ids = np.asarray(posting_doc_ids, dtype = np.uint32),
        posting_term_frequencies = np.asarray(posting_term_frequencies, dtype = np.uint32),
        average_document_length = float(np.asarray(document_lengths, dtype = np.float64).mean()),
        k1 = float(config.k1),
        b = float(config.b),
    )
