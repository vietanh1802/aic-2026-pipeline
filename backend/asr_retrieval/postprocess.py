from __future__ import annotations

from dataclasses import replace
from typing import Iterable, Sequence
import re
import unicodedata

from .schemas import (
    BoilerplateMatch,
    PostprocessOutput,
    ProcessedTranscriptWindow,
    TranscriptSegment,
    TranscriptionResult,
)


POSTPROCESS_VERSION = "1.1"
BOILERPLATE_DOMINANCE_THRESHOLD = 0.80

KNOWN_BOILERPLATE = [
    "hãy subscribe cho kênh ghiền mì gõ để không bỏ lỡ những video hấp dẫn",
    "các bạn hãy đăng ký kênh để ủng hộ kênh của chúng mình nhé",
    "đừng quên đăng ký kênh để không bỏ lỡ những video hấp dẫn",
    "hãy đăng ký kênh để không bỏ lỡ những video hấp dẫn",
]

KNOWN_BOILERPLATE_SIGNATURES = [
    "hãy subscribe cho kênh ghiền mì gõ",
    "các bạn hãy đăng ký kênh để ủng hộ kênh của chúng mình",
    "đừng quên đăng ký kênh để không bỏ lỡ những video hấp dẫn",
    "hãy đăng ký kênh để không bỏ lỡ những video hấp dẫn",
]

UNIT_PATTERNS = [
    (r"\bki\s*l[oô]\s*gam\b", "kg"),
    (r"\bkilogram\b", "kg"),
    (r"\bkilograms\b", "kg"),
    (r"\bki\s*l[oô]\b", "kg"),
    (r"(?<=\d)\s*k[ýy]\b", " kg"),
]


def normalize_whitespace(text : str) -> str :
    return re.sub(r"\s+", " ", str(text or "")).strip()


def normalize_unicode(text : str) -> str :
    return unicodedata.normalize("NFC", normalize_whitespace(text))


def normalize_for_matching(text : str) -> str :
    text = normalize_unicode(text).lower()
    text = re.sub(r"[^0-9a-zA-ZÀ-ỹđĐ\s]", " ", text)
    return normalize_whitespace(text)


def accent_fold(text : str) -> str :
    text = normalize_for_matching(text).replace("đ", "d").replace("Đ", "D")
    decomposed = unicodedata.normalize("NFD", text)
    return normalize_whitespace(
        "".join(
            character
            for character in decomposed
            if unicodedata.category(character) != "Mn"
        )
    )


def apply_unit_aliases(text : str) -> str :
    aliased = normalize_for_matching(text)

    for pattern, replacement in UNIT_PATTERNS :
        aliased = re.sub(
            pattern,
            replacement,
            aliased,
            flags = re.IGNORECASE,
        )

    return normalize_whitespace(aliased)


def suppress_consecutive_duplicate_segments(
    segments : Sequence[TranscriptSegment],
) -> tuple[str, tuple[str, ...]] :
    kept = []
    warnings = []
    last_match = None

    for segment in segments :
        text = normalize_unicode(segment.text)
        match_text = accent_fold(text)

        if (match_text and match_text == last_match) :
            warnings.append("consecutive_duplicate_segment")
            continue

        if (text) :
            kept.append(text)
            last_match = match_text

    return (
        normalize_whitespace(" ".join(kept)),
        tuple(sorted(set(warnings))),
    )


def _merge_spans(spans : Iterable[tuple[int, int]]) -> tuple[tuple[int, int], ...] :
    merged : list[list[int]] = []

    for start, end in sorted(spans) :
        if (not merged or start > merged[-1][1]) :
            merged.append([start, end])
        else :
            merged[-1][1] = max(merged[-1][1], end)

    return tuple((start, end) for start, end in merged)


def find_boilerplate_matches(
    text : str,
) -> tuple[str, tuple[BoilerplateMatch, ...], tuple[tuple[int, int], ...], float] :
    normalized = accent_fold(text)
    matches = []
    phrases = list(dict.fromkeys(KNOWN_BOILERPLATE + KNOWN_BOILERPLATE_SIGNATURES))

    for phrase in phrases :
        candidate = accent_fold(phrase)

        if (not candidate) :
            continue

        for match in re.finditer(re.escape(candidate), normalized) :
            matches.append(
                BoilerplateMatch(
                    phrase = phrase,
                    start = match.start(),
                    end = match.end(),
                )
            )

    merged_spans = _merge_spans(
        (item.start, item.end)
        for item in matches
    )
    denominator = sum(not character.isspace() for character in normalized)
    matched_characters = sum(
        sum(
            not character.isspace()
            for character in normalized[start : end]
        )
        for start, end in merged_spans
    )
    coverage = matched_characters / denominator if denominator else 0.0

    return normalized, tuple(matches), merged_spans, float(coverage)


def remove_matching_spans(
    text : str,
    spans : Sequence[tuple[int, int]],
) -> str :
    characters = list(text)

    for start, end in spans :
        for index in range(max(0, start), min(len(characters), end)) :
            characters[index] = " "

    return normalize_whitespace("".join(characters))


def postprocess_transcription(
    result : TranscriptionResult,
) -> PostprocessOutput :
    raw_text = str(result.raw_text or "")
    warning_reasons = list(result.warning_reasons)
    rejection_reasons : list[str] = []

    deduplicated_text, segment_warnings = suppress_consecutive_duplicate_segments(
        result.native_segments
    )
    source_text = deduplicated_text or normalize_unicode(raw_text)

    normalized_text = normalize_for_matching(source_text)
    accent_folded_text = accent_fold(source_text)
    retrieval_text = apply_unit_aliases(source_text)

    warning_reasons.extend(segment_warnings)

    _, boilerplate_matches, merged_spans, coverage = find_boilerplate_matches(
        source_text
    )

    if (
        boilerplate_matches
        and coverage >= BOILERPLATE_DOMINANCE_THRESHOLD
    ) :
        warning_reasons.append("known_boilerplate")
        rejection_reasons.append("dominant_known_boilerplate")
        retrieval_text = ""
    elif (boilerplate_matches) :
        warning_reasons.append("partial_known_boilerplate")
        remaining_text = remove_matching_spans(
            normalized_text,
            merged_spans,
        )
        retrieval_text = apply_unit_aliases(remaining_text)

        if (not retrieval_text) :
            rejection_reasons.append("known_boilerplate_only_after_removal")

    if (not normalize_whitespace(raw_text)) :
        warning_reasons.append("empty_output")

    return PostprocessOutput(
        normalized_text = normalized_text,
        accent_folded_text = accent_folded_text,
        retrieval_text = retrieval_text,
        warning_reasons = tuple(sorted(set(warning_reasons))),
        rejection_reasons = tuple(sorted(set(rejection_reasons))),
        boilerplate_coverage = coverage,
        boilerplate_matches = boilerplate_matches,
        postprocess_version = POSTPROCESS_VERSION,
    )


def is_retrieval_eligible(
    status : str,
    retrieval_text : str,
    rejection_reasons : Sequence[str],
) -> bool :
    return (
        str(status).lower() == "ok"
        and bool(str(retrieval_text or "").strip())
        and not rejection_reasons
    )


def process_transcription(
    result : TranscriptionResult,
) -> ProcessedTranscriptWindow :
    processed = postprocess_transcription(result)
    eligible = is_retrieval_eligible(
        result.status,
        processed.retrieval_text,
        processed.rejection_reasons,
    )

    return ProcessedTranscriptWindow(
        window = result.window,
        status = result.status,
        raw_text = result.raw_text,
        native_segments = result.native_segments,
        normalized_text = processed.normalized_text,
        accent_folded_text = processed.accent_folded_text,
        retrieval_text = processed.retrieval_text,
        warning_reasons = processed.warning_reasons,
        rejection_reasons = processed.rejection_reasons,
        boilerplate_coverage = processed.boilerplate_coverage,
        boilerplate_matches = processed.boilerplate_matches,
        postprocess_version = processed.postprocess_version,
        eligible = eligible,
        window_pcm_sha256 = result.window_pcm_sha256,
        canonical_wav_sha256 = result.canonical_wav_sha256,
        model_name = result.model_name,
        model_revision = result.model_revision,
        runtime_s = result.runtime_s,
        peak_gpu_memory_bytes = result.peak_gpu_memory_bytes,
        peak_reserved_memory_bytes = result.peak_reserved_memory_bytes,
        resolved_arguments = result.resolved_arguments,
        error = result.error,
    )


def mark_consecutive_duplicate_windows(
    windows : Sequence[ProcessedTranscriptWindow],
) -> tuple[ProcessedTranscriptWindow, ...] :
    ordered = sorted(
        windows,
        key = lambda item : (
            item.window.sample_start,
            item.window.window_id,
        ),
    )
    output = []
    last_text = None

    for window in ordered :
        current = accent_fold(window.retrieval_text)
        updated = window

        if (current and len(current) >= 30 and current == last_text) :
            warnings = tuple(
                sorted(
                    set(window.warning_reasons)
                    | {"consecutive_duplicate_window"}
                )
            )
            rejections = tuple(
                sorted(
                    set(window.rejection_reasons)
                    | {"consecutive_duplicate_window"}
                )
            )
            updated = replace(
                window,
                retrieval_text = "",
                warning_reasons = warnings,
                rejection_reasons = rejections,
                eligible = False,
            )

        output.append(updated)

        if (current) :
            last_text = current

    return tuple(output)


def rebuild_processed_windows(
    results : Sequence[TranscriptionResult],
) -> tuple[ProcessedTranscriptWindow, ...] :
    processed = [
        process_transcription(result)
        for result in sorted(
            results,
            key = lambda item : (
                item.window.sample_start,
                item.window.window_id,
            ),
        )
    ]
    return mark_consecutive_duplicate_windows(processed)
