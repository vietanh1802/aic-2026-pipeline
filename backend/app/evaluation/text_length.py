# backend/app/evaluation/text_length.py
"""How long the text a query is searched with is, in each encoder's own tokens, against its context limit.

Why: the first real run searched plain Google Translate output. Many of those texts are long (median 52
words, 65 of 145 over 55 words), and an encoder reads only its first N tokens. This records, per query, how
many tokens the searched text has under each encoder's tokenizer so the analysis can say how many queries were
cut and whether the cut ones were missed more often. Only TOKENIZERS are loaded here, never a model weight.

What each encoder does with a long text, read from preprocess.py (not assumed):

  clip     open_clip.get_tokenizer("ViT-bigG-14"), context 77 including start and end tokens. The tokenizer
           truncates (preprocess.encode_text_clip: tokens = _clip_tokenizer([text])).
  beit3    preprocess._Beit3Tokenizer: sentencepiece, [bos] + pieces + [eos], NO truncation and no padding
           (encode_text_beit3). The official BEiT-3 retrieval fine-tuning used 64 tokens; this backend feeds
           longer text through unchanged, so "over the limit" is outside the training length, not a cut.
  siglip2  the Hugging Face processor of google/siglip2-giant-opt-patch16-384 with truncation=True and
           padding="max_length", so the processor's default max_length (64, Siglip2ProcessorKwargs in
           transformers) is both the cut and the pad length. The tokenizer's own model_max_length is an
           unset sentinel (1e30) for this checkpoint, so it is not used. The tokenizer appends an end token.

`over_limit` is tokens > limit for any of them; `truncated` is over_limit AND the code really cuts (clip, siglip2).

A tokenizer that cannot be loaded here (no open_clip, no beit3.spm in the index directory, no SigLIP2 tokenizer
files on disk) falls back to a word-count estimate, recorded in `method` with the reason, never silently. The
estimate is words x 1.4 + 2, the ratio of the figures the team quoted (55 words for CLIP's 77, 45 for 64).
"""
from __future__ import annotations

import math
import os
from typing import Any, Callable

MODELS    = ("beit3", "clip", "siglip2")
LIMITS    = {"beit3" : 64, "clip" : 77, "siglip2" : 64}           # used when the tokenizer cannot tell
TRUNCATES = {"beit3" : False, "clip" : True, "siglip2" : True}     # does the production code cut a longer text
TOKENS_PER_WORD = 1.4

# model -> (count function, limit), or the reason it could not be loaded. Filled lazily, once per process.
_LOADED : dict[str, tuple[Callable[[str], int], int] | str] = {}


def _load_clip() -> tuple[Callable[[str], int], int] :
    import open_clip

    from app import preprocess

    tokenizer = open_clip.get_tokenizer(preprocess.CLIP_MODEL_NAME)
    # encode() is the BPE without the start and end tokens the tokenizer adds on top.
    return (lambda text : len(tokenizer.encode(text)) + 2), int(getattr(tokenizer, "context_length", LIMITS["clip"]))


def _load_beit3() -> tuple[Callable[[str], int], int] :
    from app import preprocess

    path = os.path.join(preprocess.INDEX_DIR, "beit3.spm")
    if (not os.path.exists(path)) :
        raise FileNotFoundError(f"{path} (the BEiT-3 sentencepiece model) is not on this host")
    tokenizer = preprocess._Beit3Tokenizer(path)
    return (lambda text : len(tokenizer(text, return_tensors = None)["input_ids"][0])), LIMITS["beit3"]


def _local_siglip2_dir() -> str :
    """The directory preprocess._ensure_siglip2_model would return, WITHOUT its download step: a host that does
    not have the files gets an estimate instead of a 3.5 GB download."""
    from app import preprocess

    if (preprocess._is_siglip2_dir(preprocess.INDEX_DIR)) :
        return preprocess.INDEX_DIR
    for candidate in (preprocess.SIGLIP2_LOCAL_DIR, os.path.join(preprocess.INDEX_DIR, preprocess.SIGLIP2_MODEL_ID.split("/")[-1])) :
        if (os.path.exists(os.path.join(candidate, "config.json"))) :
            return candidate
    root = os.path.join(preprocess.INDEX_DIR, "models--" + preprocess.SIGLIP2_MODEL_ID.replace("/", "--"), "snapshots")
    for name in (sorted(os.listdir(root)) if os.path.isdir(root) else []) :
        if (os.path.exists(os.path.join(root, name, "config.json"))) :
            return os.path.join(root, name)
    raise FileNotFoundError("no SigLIP2 directory with tokenizer files under the index directory")


def _load_siglip2() -> tuple[Callable[[str], int], int] :
    from transformers import AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(_local_siglip2_dir(), local_files_only = True)
    return (lambda text : len(tokenizer(text, add_special_tokens = True, truncation = False, verbose = False)["input_ids"])), LIMITS["siglip2"]


_LOADERS = {"clip" : _load_clip, "beit3" : _load_beit3, "siglip2" : _load_siglip2}


def counter(model : str) -> tuple[Callable[[str], int], int, str] :
    """(count function, limit, method) for one encoder. method is "tokenizer", or "estimate: <why>"."""
    if (model not in _LOADED) :
        try :
            _LOADED[model] = _LOADERS[model]()
        except Exception as exc :
            # No tokenizer on this host: record the reason with every number that falls back to the estimate.
            reason = f"{type(exc).__name__}: {str(exc)[ : 120]}"
            print(f"[text_length] {model} tokenizer not loadable ({reason}); using a word-count estimate")
            _LOADED[model] = reason
    entry = _LOADED[model]
    if (isinstance(entry, str)) :
        return (lambda text : math.ceil(len(text.split()) * TOKENS_PER_WORD) + 2), LIMITS[model], f"estimate: {entry}"
    return entry[0], entry[1], "tokenizer"


def measure(texts : list[str]) -> dict[str, Any] :
    """Per encoder: tokens (the longest of `texts`; a TRAKE-N query has one text per event), limit, over_limit,
    truncated, method, how many texts were over, and the word count of the longest. Never loads a model."""
    out : dict[str, Any] = {"n_texts" : len(texts), "words" : max((len(t.split()) for t in texts), default = 0)}
    for model in MODELS :
        count, limit, method = counter(model)
        tokens = [count(t) for t in texts]
        over = sum(1 for n in tokens if n > limit)
        out[model] = {
            "tokens"     : max(tokens, default = 0),
            "limit"      : limit,
            "over_limit" : over > 0,
            "truncated"  : over > 0 and TRUNCATES[model],
            "n_over"     : over,
            "method"     : method,
        }
    return out
