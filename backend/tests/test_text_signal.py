# backend/tests/test_text_signal.py
import json
import os
import re
import unicodedata
from dataclasses import asdict

import numpy as np
import pytest

from app import ocr_search, preprocess, text_lookup, text_signal
from app.ocr_search import _strip_marks
from app.text_signal import TextMatchMode, annotate_videos


@pytest.fixture(autouse=True)
def reset_module_state(monkeypatch) :
    """Every backing module keeps module-level cache state -- give each test
    a clean slate, same pattern as test_asr_text.py / test_text_lookup.py."""
    monkeypatch.setattr(preprocess, "_video_frames", {})
    monkeypatch.setattr(ocr_search, "_loaded", True)
    monkeypatch.setattr(ocr_search, "_display", {})
    monkeypatch.setattr(ocr_search, "_haystack", {"with_marks" : {}, "no_marks" : {}})
    monkeypatch.setattr(text_signal, "_bm25_loaded", False)
    monkeypatch.setattr(text_signal, "_bm25_unavailable_reason", None)
    monkeypatch.setattr(text_signal, "_bm25_token_to_id", {})
    monkeypatch.setattr(text_signal, "_bm25_posting_offsets", None)
    monkeypatch.setattr(text_signal, "_bm25_posting_doc_ids", None)
    monkeypatch.setattr(text_signal, "_bm25_posting_term_freqs", None)
    monkeypatch.setattr(text_signal, "_bm25_document_lengths", None)
    monkeypatch.setattr(text_signal, "_bm25_avgdl", 0.0)
    monkeypatch.setattr(text_signal, "_bm25_doc_video_ids", [])
    monkeypatch.setattr(text_signal, "_bm25_doc_texts", [])
    monkeypatch.setattr(text_signal, "_bm25_doc_start_s", None)
    monkeypatch.setattr(text_signal, "_bm25_doc_end_s", None)
    monkeypatch.setattr(text_lookup, "_windows_cache", None)


def _meta(name : str, video : str, frame_idx : int, fps : float = 25.0) -> dict :
    return {"name" : name, "video" : video, "frame_idx" : frame_idx, "fps" : fps}


def _set_corpus(monkeypatch, videos : dict[str, list[dict]]) -> None :
    monkeypatch.setattr(preprocess, "_video_frames", videos)


def _set_ocr_text(name : str, with_marks : str, no_marks : str | None = None) -> None :
    """Populate ocr_search's real backing dicts -- exercised through the real
    ocr_search.search()/get_text(), not mocked away."""
    ocr_search._display[name] = with_marks
    ocr_search._haystack["with_marks"][name] = with_marks
    ocr_search._haystack["no_marks"][name] = (no_marks or with_marks)


def _mock_asr_text(monkeypatch, texts : dict[str, str]) -> None :
    monkeypatch.setattr(text_signal.asr_text, "get_text", lambda name : texts.get(name, ""))


# ── substring mode: OCR side (via text_lookup) ──────────────────────────────

def test_substring_ocr_exact_match_here(monkeypatch) :
    _set_corpus(monkeypatch, {"V1" : [_meta("V1-0000-100.jpg", "V1", 100)]})
    _mock_asr_text(monkeypatch, {})
    _set_ocr_text("V1-0000-100.jpg", "co tu khoa can tim")

    result = annotate_videos(["V1"], "tu khoa", TextMatchMode.substring,
                              {"V1" : ["V1-0000-100.jpg"]})
    assert result["V1"].matched is True
    assert result["V1"].ocr.match_frame == "V1-0000-100.jpg"
    assert result["V1"].ocr.match_type == "exact"
    assert result["V1"].ocr.location == "here"


def test_substring_ocr_no_match(monkeypatch) :
    _set_corpus(monkeypatch, {"V1" : [_meta("V1-0000-100.jpg", "V1", 100)]})
    _mock_asr_text(monkeypatch, {})
    _set_ocr_text("V1-0000-100.jpg", "khong lien quan")

    result = annotate_videos(["V1"], "tu khoa", TextMatchMode.substring,
                              {"V1" : ["V1-0000-100.jpg"]})
    assert result["V1"].matched is False
    assert result["V1"].ocr.location == "none"
    assert result["V1"].ocr.match_frame is None


def test_substring_empty_query(monkeypatch) :
    _set_corpus(monkeypatch, {"V1" : [_meta("V1-0000-100.jpg", "V1", 100)]})
    result = annotate_videos(["V1"], "   ", TextMatchMode.substring, {})
    assert result["V1"].matched is False
    assert result["V1"].asr.location == "none"
    assert result["V1"].ocr.location == "none"


# ── substring mode: ASR side (own per-frame check, not via lookup_text) ────

def test_substring_asr_match(monkeypatch) :
    _set_corpus(monkeypatch, {"V1" : [_meta("V1-0000-100.jpg", "V1", 100)]})
    _mock_asr_text(monkeypatch, {"V1-0000-100.jpg" : "mot con cho dang chay ngoai san"})

    result = annotate_videos(["V1"], "cho", TextMatchMode.substring, {"V1" : ["V1-0000-100.jpg"]})
    assert result["V1"].matched is True
    assert result["V1"].asr.match_frame == "V1-0000-100.jpg"
    assert result["V1"].asr.match_type == "exact"


def test_substring_asr_diacritic_folding_is_normalized(monkeypatch) :
    # query has no diacritics, source text does -- must still match, tagged
    # "normalized" since it only matched after folding. (No "ngon" in the
    # text -- that word contains the literal, unfolded substring "ngo" and
    # would wrongly tag this "exact".)
    _set_corpus(monkeypatch, {"V1" : [_meta("V1-0000-100.jpg", "V1", 100)]})
    _mock_asr_text(monkeypatch, {"V1-0000-100.jpg" : "rau ngò rất tươi"})

    result = annotate_videos(["V1"], "ngo", TextMatchMode.substring, {"V1" : ["V1-0000-100.jpg"]})
    assert result["V1"].matched is True
    assert result["V1"].asr.match_type == "normalized"


# ── substring prefilter: identical to the old per-frame fold ────────────────
#
# _substring_hits() used to fold every frame's text; it now compiles the folded
# term to a regex over the raw text. _reference_substring_hits below is the OLD
# implementation, copied verbatim, and serves as the oracle: same hits, same
# exact/normalized tags, same ranks, for every text/term pair.

def _reference_substring_hits(video_id : str, term : str, get_text) :
    term_lower = term.lower()
    term_folded = _strip_marks(term).lower()
    exact, normalized = [], []
    for name in preprocess.frames_for_video(video_id) :
        text = get_text(name)
        if not text :
            continue
        if term_lower in text.lower() :
            exact.append(name)
        elif term_folded in _strip_marks(text).lower() :
            normalized.append(name)

    total = len(exact) + len(normalized)
    hits = [text_lookup.TextHit(video_id, name, "exact", rank, total)
            for rank, name in enumerate(exact, 1)]
    hits += [text_lookup.TextHit(video_id, name, "normalized", rank, total)
             for rank, name in enumerate(normalized, len(exact) + 1)]
    return hits


_VI = "Người ta nấu thịt bò với nước sôi, rau ngò và ngon lắm. Đường đi Đà Nẵng."
REFERENCE_TEXTS = [
    _VI,
    unicodedata.normalize("NFD", _VI),  # decomposed Vietnamese
    "THỂ THAO VÀ ĐƯỜNG ĐI NGƯỜI",
    "thể thao và đường đi",
    "ngo ngon ngò ngõ",
    "chợ cho chờ chó",
    "2018 THPT 2018 THPTQG 2018",
    "วิธบลอกจุรี ดูที่นี้ (ไม่) EMERGENCY 1669",  # Thai: combining marks the old fold also deleted
    "a\u0e31b ab a\u0301b a\u0300\u0301b",  # marks between the letters
    "giá (1.5L) [x] a+b a*b what? c:\\dir 1/2 muỗng \\ ( [ + * ?",  # regex specials
    "a  b   c a b",  # runs of spaces
    "a\u00a0b\ta\tb",  # no-break space and tabs
    "Йога и й, Ελληνικά ΣΑΣ σας ά α",  # other scripts: some fold, some do not
    "İstanbul ıstanbul \u212a \u212b \u026b \u2c62 ; \u037e a=b \u2260",  # Kelvin/Angstrom, leak targets
    "ガカ 한국 🙂 nước 🙂",
    "a\U000e0100b ab x\U0001e8d0y xy",  # Mn above the BMP: the frame takes the per-frame fold
    "",  # no ASR text for this frame
    "   ",
]

REFERENCE_TERMS = [
    "cho", "chợ", "ngo", "ngò", "nuoc", "nước", "nuoc soi", "nước sôi", "thit bo", "thịt bò",
    "nguoi", "người", "NGƯỜI", "the thao", "THỂ THAO", "thể thao", "duong", "đường", "Duong di",
    "đ", "Đ", "d", "2018", "THPT 2018", "a b", "a  b", "a   b", " a", "a ", "a.b", "1.5L",
    "(1.5l)", "[x]", "a+b", "a*b", "what?", "c:\\dir", "\\", "(", "[", "+", "*", "?", "1/2",
    "muỗng", "ab", "a\u0e31b", "วิธ", "ที่", "Йога", "й", "и", "Ελληνικά", "ά", "α", "σας", "ς",
    "istanbul", "İstanbul", "k", "K", "å", "a", "ɫ", "=", "a=b", ";", "≠", "ガ", "カ", "한", "🙂",
    "", " ", "   ", "\t",
]


@pytest.mark.parametrize("term", REFERENCE_TERMS)
def test_substring_prefilter_matches_reference_fold(monkeypatch, term) :
    names = [f"V1-0000-{index}.jpg" for index in range(len(REFERENCE_TEXTS))]
    _set_corpus(monkeypatch, {"V1" : [_meta(name, "V1", index) for index, name in enumerate(names)]})
    texts = dict(zip(names, REFERENCE_TEXTS))

    def get_text(name : str) -> str :
        return texts.get(name, "")

    assert text_signal._substring_hits("V1", term, get_text) == _reference_substring_hits("V1", term, get_text)


def test_substring_prefilter_skips_marks_between_letters(monkeypatch) :
    """Guards the oracle itself: both implementations could be wrong the same
    way, so pin one behavior explicitly. The old fold deleted every Mn
    character, so "ab" must hit "a" + <Thai tone mark> + "b"."""
    _set_corpus(monkeypatch, {"V1" : [_meta("V1-0000-1.jpg", "V1", 1)]})
    hits = text_signal._substring_hits("V1", "ab", lambda name : "x a\u0e31b y")
    assert [(hit.frame_name, hit.match_type) for hit in hits] == [("V1-0000-1.jpg", "normalized")]


def test_substring_prefilter_still_skips_marks_above_the_bmp(monkeypatch) :
    """The regex class only holds BMP marks; a frame with a character above
    U+FFFF must fall back to the exact fold, so "ab" still hits "a"+U+E0100+"b"
    (a variation selector, category Mn)."""
    _set_corpus(monkeypatch, {"V1" : [_meta("V1-0000-1.jpg", "V1", 1)]})
    hits = text_signal._substring_hits("V1", "ab", lambda name : "x a\U000e0100b y")
    assert [(hit.frame_name, hit.match_type) for hit in hits] == [("V1-0000-1.jpg", "normalized")]


def test_mark_class_covers_exactly_the_bmp_nonspacing_marks() :
    mark = re.compile(text_signal._MARK_CLASS)
    for code in range(0x10000) :
        assert bool(mark.fullmatch(chr(code))) == (unicodedata.category(chr(code)) == "Mn"), hex(code)


def test_substring_prefilter_exact_beats_normalized_and_keeps_ranks(monkeypatch) :
    _set_corpus(monkeypatch, {"V1" : [_meta(f"V1-0000-{i}.jpg", "V1", i) for i in range(3)]})
    texts = {"V1-0000-0.jpg" : "rau ngo", "V1-0000-1.jpg" : "rau ngò", "V1-0000-2.jpg" : "khong co"}
    hits = text_signal._substring_hits("V1", "ngo", lambda name : texts[name])
    assert [(h.frame_name, h.match_type, h.rank, h.total_matched) for h in hits] == [
        ("V1-0000-0.jpg", "exact", 1, 2), ("V1-0000-1.jpg", "normalized", 2, 2)]


def test_terms_outside_the_audited_scope_use_the_fallback_path() :
    for term in ["nguoi", "thịt bò", "2018", "a+b", "", " "] :
        assert text_signal._folded_pattern(_strip_marks(term).lower()) is not None
    for term in ["и", "ά", "ガ", "한", ";", "≠", "ɫ", "🙂"] :
        assert text_signal._folded_pattern(_strip_marks(term).lower()) is None


def test_fold_scope_is_complete() :
    """The prefilter is exact only if the facts in the block comment above
    _FOLD_SCOPE hold. Re-derive them over every code point that can carry a
    decomposition or case mapping (nothing above U+30000 does), so a Python /
    Unicode upgrade that changes them fails here instead of silently changing
    which frames match."""
    def in_scope(code : int) -> bool :
        return any(low <= code <= high for low, high in text_signal._FOLD_SCOPE)

    scope_chars = {chr(code) for low, high in text_signal._FOLD_SCOPE for code in range(low, high + 1)}
    leak_targets = set()
    for code in range(0x30000) :
        if 0xD800 <= code <= 0xDFFF :
            continue
        char = chr(code)
        folded = _strip_marks(char).lower()
        assert _strip_marks(char.lower()) == folded, hex(code)  # exact never hits what folded misses
        if unicodedata.category(char) == "Mn" :
            assert folded == "", hex(code)
        elif in_scope(code) :
            assert len(folded) == 1, hex(code)
        elif any(other in scope_chars for other in folded) :
            assert len(folded) == 1, hex(code)  # a multi-character fold into scope would break the regex
            leak_targets.add(folded)
    assert leak_targets == set(text_signal._FOLD_LEAK_TARGETS)


def test_text_filter_length_cap_is_enforced_on_the_request() :
    from pydantic import ValidationError

    from app.main import EnsembleSearchRequest

    cap = text_signal.TEXT_FILTER_MAX_CHARS
    assert EnsembleSearchRequest(query = "q", text_filter = "x" * cap).text_filter == "x" * cap
    with pytest.raises(ValidationError) :
        EnsembleSearchRequest(query = "q", text_filter = "x" * (cap + 1))


# ── match detail: snippet, highlight, time, rank (popover data) ─────────────

def _hit_texts(segments : list[list]) -> list[str] :
    return [text for text, is_hit in segments if is_hit]


def _plain(segments : list[list]) -> str :
    return "".join(text for text, _is_hit in segments)


def test_snippet_marks_hits_and_needs_no_ellipsis_for_short_text() :
    text = "mot hai ba bon nam"
    assert text_signal._snippet_segments(text, [(8, 10)]) == [["mot hai ", False], ["ba", True], [" bon nam", False]]


def test_snippet_ellipsis_at_both_ends_at_one_end_and_at_neither() :
    filler = "loi noi dai " * 12
    text = filler + "cho meo " + filler
    start = text.index("meo")
    both = text_signal._snippet_segments(text, [(start, start + 3)])
    assert both[0][0].startswith("…") and both[-1][0].endswith("…") and _hit_texts(both) == ["meo"]
    assert len(_plain(both)) <= text_signal.SNIPPET_MAX_CHARS + 2 * text_signal._SNIPPET_EDGE_SLACK + 2

    only_end = text_signal._snippet_segments(text, [(0, 3)])
    assert not only_end[0][0].startswith("…") and only_end[-1][0].endswith("…")
    only_start = text_signal._snippet_segments(text, [(len(text) - 6, len(text) - 2)])
    assert only_start[0][0].startswith("…") and not only_start[-1][0].endswith("…")
    neither = text_signal._snippet_segments("ngan gon", [(0, 4)])
    assert "…" not in _plain(neither)


def test_snippet_hit_at_the_very_start_and_the_very_end() :
    assert text_signal._snippet_segments("meo dep", [(0, 3)]) == [["meo", True], [" dep", False]]
    assert text_signal._snippet_segments("dep meo", [(4, 7)]) == [["dep ", False], ["meo", True]]


def test_snippet_ellipsis_gets_its_own_segment_when_the_window_starts_or_ends_on_a_hit() :
    text = "a" * 100 + "b" * 150 + "c" * 100  # a hit longer than the window
    segments = text_signal._snippet_segments(text, [(100, 250)])
    assert segments[0] == ["…", False] and segments[1][1] is True and segments[-1] == ["…", False]


def test_snippet_prefers_the_densest_cluster_of_distinct_words() :
    early = "thi " + "x " * 80        # one hit, far from the cluster
    late = "thi hien tai " + "y " * 10
    text = early + late
    spans = [m.span() for m in text_signal._BM25_TOKEN_SPAN_RE.finditer(text) if m.group() in ("thi", "hien", "tai")]
    assert _hit_texts(text_signal._snippet_segments(text, spans)) == ["thi", "hien", "tai"]


def test_snippet_ties_go_to_more_spans_then_the_earliest() :
    text = "meo " + "x " * 60 + "meo x meo " + "x " * 60 + "meo x meo"
    spans = [m.span() for m in re.finditer("meo", text)]
    segments = text_signal._snippet_segments(text, spans)
    assert _hit_texts(segments) == ["meo", "meo"]  # the first pair of 2, not the lone "meo" at the start
    assert segments[0][0].startswith("…")


def test_snippet_repeated_occurrences_are_all_marked() :
    text = "meo an ca, meo ngu, meo choi"
    spans = [m.span() for m in re.finditer("meo", text)]
    assert _hit_texts(text_signal._snippet_segments(text, spans)) == ["meo", "meo", "meo"]


def test_snippet_empty_text_no_spans_and_hostile_spans_never_raise() :
    assert text_signal._snippet_segments("", [(0, 1)]) == []
    assert text_signal._snippet_segments("   \n ", [(0, 2)]) == []
    assert text_signal._snippet_segments("abc def", []) == [["abc def", False]]
    long_plain = text_signal._snippet_segments("word " * 60, [])  # no spans: the first characters, one plain segment
    assert len(long_plain) == 1 and long_plain[0][1] is False and long_plain[0][0].endswith("…")
    assert long_plain[0][0][:-1] == ("word " * 60)[: text_signal.SNIPPET_MAX_CHARS].rstrip()
    hostile = [(-5, 2), (3, 3), (5, 1), (100, 200), (0, 100), (2, 4), (2, 4)]
    segments = text_signal._snippet_segments("abcdef ghij", hostile)
    assert _plain(segments).replace(" ", "") == "abcdefghij"


def test_snippet_collapses_whitespace_after_slicing_so_hits_keep_their_boundaries() :
    text = "dong mot\n\n  thit\nbo   ngon\n  qua"
    start = text.index("thit")
    segments = text_signal._snippet_segments(text, [(start, text.index("bo") + 2)])
    assert segments == [["dong mot ", False], ["thit bo", True], [" ngon qua", False]]  # a hit split across a newline


def test_token_spans_match_bm25_tokenize() :
    for text in ["Người ta nấu thịt bò, nước sôi (2018)!", "THỂ THAO 1.5L a+b", "", "  ...  ", "đường-đi/đà nẵng"] :
        assert [text[start : end].lower() for start, end in text_signal._token_spans(text)] == text_signal._bm25_tokenize(text)


def test_moment_in_window_is_linear_and_clamped() :
    assert text_signal._moment_in_window(100.0, 160.0, 200, 100) == 130.0
    assert text_signal._moment_in_window(100.0, 160.0, 200, -50) == 100.0
    assert text_signal._moment_in_window(100.0, 160.0, 200, 999) == 160.0
    assert text_signal._moment_in_window(100.0, 160.0, 0, 5) == 130.0  # empty text: the middle


@pytest.mark.parametrize("text, term, match_type, hit", [
    ("nước sôi", "nuoc", "normalized", "nước"),
    ("Nước sôi", "nước", "exact", "Nước"),
    ("cả THỂ THAO hôm nay", "the thao", "normalized", "THỂ THAO"),
    ("Đường đi", "duong", "normalized", "Đường"),
    (unicodedata.normalize("NFD", "nước sôi"), "nuoc", "normalized", unicodedata.normalize("NFD", "nước")),
    ("x aัb y", "ab", "normalized", "aัb"),
])
def test_highlight_is_computed_on_the_original_text(text, term, match_type, hit) :
    segments = text_signal._snippet_segments(text, text_signal._substring_spans(text, term, match_type, False))
    assert _hit_texts(segments) == [hit]
    assert json.loads(json.dumps(segments, ensure_ascii=True)) == json.loads(json.dumps(segments, ensure_ascii=False)) == segments


def test_highlight_survives_astral_characters_and_json_round_trips() :
    text = "🙂 mon nước sôi 🙂"
    exact = text_signal._snippet_segments(text, text_signal._substring_spans(text, "nước", "exact", False))
    assert _hit_texts(exact) == ["nước"] and _plain(exact) == text
    for ensure_ascii in (True, False) :
        assert json.loads(json.dumps(exact, ensure_ascii=ensure_ascii)) == exact
    # accent-insensitive on a text with a character above U+FFFF: no highlight, but a snippet
    folded = text_signal._snippet_segments(text, text_signal._substring_spans(text, "nuoc", "normalized", False))
    assert _hit_texts(folded) == [] and _plain(folded) == text


def _detail_video(monkeypatch, asr : str = "", ocr : str = "", frame_idx : int = 100, fps : float = 25.0) :
    name = f"V1-0000-{frame_idx}.jpg"
    _set_corpus(monkeypatch, {"V1" : [_meta(name, "V1", frame_idx, fps=fps)]})
    _mock_asr_text(monkeypatch, {name : asr} if asr else {})
    if ocr :
        _set_ocr_text(name, ocr)
    return name, {"V1" : [name]}


def test_asr_substring_detail_uses_the_frame_time_and_ranks_nothing(monkeypatch) :
    name, frames = _detail_video(monkeypatch, asr="rau ngò rất tươi", frame_idx=100, fps=25.0)
    detail = annotate_videos(["V1"], "ngo", TextMatchMode.substring, frames)["V1"].asr.detail
    assert _hit_texts(detail.snippet) == ["ngò"] and _plain(detail.snippet) == "rau ngò rất tươi"
    assert (detail.at_s, detail.start_s, detail.end_s, detail.time_approx) == (4.0, None, None, False)
    assert (detail.rank, detail.total_matched, detail.exact_phrase) == (None, None, None)
    assert (detail.matched_terms, detail.terms_total) == ([], 0)


def test_regex_detail_highlights_the_pattern_matches(monkeypatch) :
    name, frames = _detail_video(monkeypatch, asr="gia 12 va 345 dong", frame_idx=50, fps=25.0)
    detail = annotate_videos(["V1"], r"\d+", TextMatchMode.regex, frames)["V1"].asr.detail
    assert _hit_texts(detail.snippet) == ["12", "345"]
    assert (detail.at_s, detail.start_s, detail.end_s, detail.time_approx) == (2.0, None, None, False)
    assert (detail.rank, detail.total_matched) == (None, None)


def test_ocr_substring_detail_word_scatter_multiline_phrase_flag_and_rank(monkeypatch) :
    name, frames = _detail_video(monkeypatch, ocr="quan an\ncho o lon\nra", frame_idx=125, fps=25.0)
    result = annotate_videos(["V1"], "an lon", TextMatchMode.substring, frames)["V1"]
    detail = result.ocr.detail
    assert _hit_texts(detail.snippet) == ["an", "an", "lon"]     # phrase absent: each WORD is marked, as a substring
    assert _plain(detail.snippet) == "quan an cho o lon ra"      # newlines collapsed
    assert (detail.at_s, detail.time_approx, detail.exact_phrase) == (5.0, False, False)
    assert (detail.rank, detail.total_matched) == (1, 1)
    assert result.asr.detail is None                              # no ASR match, no detail



def test_ocr_whole_phrase_sets_exact_phrase_true_and_marks_the_phrase(monkeypatch) :
    name, frames = _detail_video(monkeypatch, ocr="Quán ăn Chợ Lớn", frame_idx=25)
    ocr_search._haystack["with_marks"][name] = "quán ăn chợ lớn"  # the real haystack is lowercased
    ocr_search._haystack["no_marks"][name] = "quan an cho lon"
    detail = annotate_videos(["V1"], "chợ lớn", TextMatchMode.substring, frames)["V1"].ocr.detail
    assert _hit_texts(detail.snippet) == ["Chợ Lớn"] and detail.exact_phrase is True


def test_ocr_normalized_match_is_highlighted_on_the_accented_text(monkeypatch) :
    name, frames = _detail_video(monkeypatch, ocr="HỂ THAO va TIN TUC", frame_idx=25)
    _set_ocr_text(name, "HỂ THAO va TIN TUC", no_marks="he thao va tin tuc")
    detail = annotate_videos(["V1"], "he thao", TextMatchMode.substring, frames)["V1"].ocr.detail
    assert _hit_texts(detail.snippet) == ["HỂ THAO"]


def test_source_match_asdict_keeps_the_original_keys_and_adds_detail() :
    plain = text_signal.SourceMatch("V1-0000-1.jpg", "exact", "here")
    assert asdict(plain) == {"match_frame" : "V1-0000-1.jpg", "match_type" : "exact", "location" : "here", "detail" : None}
    assert text_signal._NO_MATCH.detail is None and asdict(text_signal._NO_MATCH)["location"] == "none"


def test_annotation_with_detail_is_json_serializable(monkeypatch) :
    name, frames = _detail_video(monkeypatch, asr="rau ngò 🙂 rất tươi", ocr="ngò gai")
    result = annotate_videos(["V1"], "ngo", TextMatchMode.substring, frames)["V1"]
    payload = json.loads(json.dumps(asdict(result), ensure_ascii=False))
    assert set(payload) == {"matched", "score", "mode", "asr", "ocr"}
    assert set(payload["asr"]) == {"match_frame", "match_type", "location", "detail"}
    assert set(payload["asr"]["detail"]) == {"snippet", "matched_terms", "terms_total", "at_s", "start_s", "end_s",
                                             "time_approx", "rank", "total_matched", "exact_phrase"}


def test_a_failing_detail_leaves_the_annotation_intact_and_other_videos_unaffected(monkeypatch, caplog) :
    _set_corpus(monkeypatch, {"V1" : [_meta("V1-0000-100.jpg", "V1", 100)], "V2" : [_meta("V2-0000-100.jpg", "V2", 100)],
                              "V3" : [_meta("V3-0000-100.jpg", "V3", 100)]})
    _mock_asr_text(monkeypatch, {f"V{i}-0000-100.jpg" : "rau ngò rất tươi" for i in (1, 2, 3)})
    real = text_signal.describe_match

    def flaky(hit, source, mode, term, pattern=None) :
        if hit.video_id in ("V1", "V2") :
            raise RuntimeError("boom")
        return real(hit, source, mode, term, pattern)

    monkeypatch.setattr(text_signal, "describe_match", flaky)
    frames = {f"V{i}" : [f"V{i}-0000-100.jpg"] for i in (1, 2, 3)}
    with caplog.at_level("ERROR", logger=text_signal.logger.name) :
        result = annotate_videos(["V1", "V2", "V3"], "ngo", TextMatchMode.substring, frames)
    for video in ("V1", "V2") :
        assert result[video].matched is True and result[video].asr.match_frame == f"{video}-0000-100.jpg"
        assert result[video].asr.location == "here" and result[video].asr.detail is None
    assert result["V3"].asr.detail is not None
    assert sum("match detail failed" in record.getMessage() for record in caplog.records) == 1  # once per call


def test_non_matching_videos_get_no_detail_and_do_no_detail_work(monkeypatch) :
    _set_corpus(monkeypatch, {"V1" : [_meta("V1-0000-100.jpg", "V1", 100)]})
    _mock_asr_text(monkeypatch, {"V1-0000-100.jpg" : "khong lien quan"})
    calls = []
    monkeypatch.setattr(text_signal, "describe_match", lambda *args, **kwargs : calls.append(args))
    result = annotate_videos(["V1"], "ngo", TextMatchMode.substring, {"V1" : ["V1-0000-100.jpg"]})["V1"]
    assert result.matched is False and result.asr.detail is None and calls == []


# ── regex mode ───────────────────────────────────────────────────────────

def test_regex_valid_match(monkeypatch) :
    _set_corpus(monkeypatch, {"V1" : [_meta("V1-0000-100.jpg", "V1", 100)]})
    _mock_asr_text(monkeypatch, {"V1-0000-100.jpg" : "gia ve la hai trieu dong"})
    monkeypatch.setattr(ocr_search, "get_text", lambda name : "")

    result = annotate_videos(["V1"], r"hai\s+trieu", TextMatchMode.regex, {"V1" : ["V1-0000-100.jpg"]})
    assert result["V1"].matched is True
    assert result["V1"].asr.match_type == "exact"  # regex has no folded tier


def test_regex_valid_no_match(monkeypatch) :
    _set_corpus(monkeypatch, {"V1" : [_meta("V1-0000-100.jpg", "V1", 100)]})
    _mock_asr_text(monkeypatch, {"V1-0000-100.jpg" : "gia ve la hai trieu dong"})
    monkeypatch.setattr(ocr_search, "get_text", lambda name : "")

    result = annotate_videos(["V1"], r"\d{4}", TextMatchMode.regex, {"V1" : ["V1-0000-100.jpg"]})
    assert result["V1"].matched is False


def test_regex_invalid_pattern_returns_gracefully(monkeypatch) :
    _set_corpus(monkeypatch, {"V1" : [_meta("V1-0000-100.jpg", "V1", 100)],
                              "V2" : [_meta("V2-0000-100.jpg", "V2", 100)]})
    result = annotate_videos(["V1", "V2"], "(unclosed", TextMatchMode.regex, {})
    assert result["V1"].matched is False
    assert result["V1"].asr.location == "none"
    # same (non-)result for every requested video, not just the first
    assert result["V2"].matched is False


def test_regex_not_diacritic_folded(monkeypatch) :
    """Old substring-mode guarantee, still true for regex: querying without
    diacritics must NOT match text that only has the accented form."""
    _set_corpus(monkeypatch, {"V1" : [_meta("V1-0000-100.jpg", "V1", 100)]})
    _mock_asr_text(monkeypatch, {"V1-0000-100.jpg" : "rau ngò rất tươi"})
    monkeypatch.setattr(ocr_search, "get_text", lambda name : "")

    result = annotate_videos(["V1"], "ngo", TextMatchMode.regex, {"V1" : ["V1-0000-100.jpg"]})
    assert result["V1"].matched is False


# ── never raises ─────────────────────────────────────────────────────────

def test_no_exception_propagates_when_get_text_raises(monkeypatch) :
    _set_corpus(monkeypatch, {"V1" : [_meta("V1-0000-100.jpg", "V1", 100)]})
    def boom(name) :
        raise RuntimeError("simulated failure")
    monkeypatch.setattr(text_signal.asr_text, "get_text", boom)
    monkeypatch.setattr(ocr_search, "search", boom)

    result = annotate_videos(["V1"], "anything", TextMatchMode.substring, {})
    assert result["V1"].matched is False
    assert result["V1"].asr.location == "none"


def test_no_exception_propagates_for_unknown_video(monkeypatch) :
    _set_corpus(monkeypatch, {})
    result = annotate_videos(["GHOST_VIDEO"], "anything", TextMatchMode.substring, {})
    assert result["GHOST_VIDEO"].matched is False


# ── here vs. elsewhere ───────────────────────────────────────────────────

def test_location_here_when_match_frame_is_in_result_set(monkeypatch) :
    _set_corpus(monkeypatch, {"V1" : [_meta("V1-0000-100.jpg", "V1", 100)]})
    _mock_asr_text(monkeypatch, {})
    _set_ocr_text("V1-0000-100.jpg", "tu khoa")

    result = annotate_videos(["V1"], "tu khoa", TextMatchMode.substring,
                              {"V1" : ["V1-0000-100.jpg"]})
    assert result["V1"].ocr.location == "here"


def test_location_elsewhere_when_match_frame_is_not_in_result_set(monkeypatch) :
    # The matching frame (100) exists in the video's real frame list but was
    # not one of the frames the visual search actually retrieved (200 was).
    _set_corpus(monkeypatch, {"V1" : [_meta("V1-0000-100.jpg", "V1", 100),
                                       _meta("V1-0000-200.jpg", "V1", 200)]})
    _mock_asr_text(monkeypatch, {})
    _set_ocr_text("V1-0000-100.jpg", "tu khoa")
    _set_ocr_text("V1-0000-200.jpg", "khong lien quan")

    result = annotate_videos(["V1"], "tu khoa", TextMatchMode.substring,
                              {"V1" : ["V1-0000-200.jpg"]})
    assert result["V1"].matched is True
    assert result["V1"].ocr.match_frame == "V1-0000-100.jpg"
    assert result["V1"].ocr.location == "elsewhere"


# ── exact vs. normalized preference ─────────────────────────────────────

def test_exact_preferred_over_normalized_even_when_normalized_is_here(monkeypatch) :
    """frame A: "here", matches only after diacritic folding ("normalized").
    frame B: "elsewhere", matches with real diacritics intact ("exact").
    match_type takes priority over location -- B wins."""
    _set_corpus(monkeypatch, {"V1" : [_meta("V1-0000-100.jpg", "V1", 100),
                                       _meta("V1-0000-200.jpg", "V1", 200)]})
    _mock_asr_text(monkeypatch, {})
    _set_ocr_text("V1-0000-100.jpg", with_marks="khong co dau day du", no_marks="tu khoa day day")
    _set_ocr_text("V1-0000-200.jpg", with_marks="tu khoa", no_marks="tu khoa")

    result = annotate_videos(["V1"], "tu khoa", TextMatchMode.substring,
                              {"V1" : ["V1-0000-100.jpg"]})  # only A is "here"
    assert result["V1"].ocr.match_frame == "V1-0000-200.jpg"
    assert result["V1"].ocr.match_type == "exact"
    assert result["V1"].ocr.location == "elsewhere"


def test_here_preferred_over_elsewhere_when_match_type_ties(monkeypatch) :
    _set_corpus(monkeypatch, {"V1" : [_meta("V1-0000-100.jpg", "V1", 100),
                                       _meta("V1-0000-200.jpg", "V1", 200)]})
    _mock_asr_text(monkeypatch, {})
    _set_ocr_text("V1-0000-100.jpg", "tu khoa")   # here, exact
    _set_ocr_text("V1-0000-200.jpg", "tu khoa")   # elsewhere, also exact

    result = annotate_videos(["V1"], "tu khoa", TextMatchMode.substring,
                              {"V1" : ["V1-0000-100.jpg"]})
    assert result["V1"].ocr.match_frame == "V1-0000-100.jpg"
    assert result["V1"].ocr.location == "here"


# ── regression: the two confirmed bugs this rewrite fixes ─────────────────

def test_regression_match_not_misattributed_to_a_different_frame(monkeypatch) :
    """The "2018" bug: a genuine match on one frame must never be reported
    against a different, unrelated frame of the same video. Frame 100 (the
    one actually retrieved by visual search) does NOT contain "2018"; frame
    200 (not retrieved) does. The old blob-concatenation code could not tell
    them apart; this must report frame 200 by name, as "elsewhere"."""
    _set_corpus(monkeypatch, {"V1" : [_meta("V1-0000-100.jpg", "V1", 100),
                                       _meta("V1-0000-200.jpg", "V1", 200)]})
    _mock_asr_text(monkeypatch, {})
    _set_ocr_text("V1-0000-100.jpg", "de thi nam hoc truoc")   # no "2018" here
    _set_ocr_text("V1-0000-200.jpg", "de thi THPTQG 2018")     # "2018" is here

    result = annotate_videos(["V1"], "2018", TextMatchMode.substring,
                              {"V1" : ["V1-0000-100.jpg"]})  # only frame 100 was retrieved
    assert result["V1"].matched is True
    assert result["V1"].ocr.match_frame == "V1-0000-200.jpg"  # not the retrieved frame
    assert result["V1"].ocr.location == "elsewhere"


def test_regression_match_outside_result_set_is_not_invisible(monkeypatch) :
    """The "nghêu" bug: a real match must be found even when none of the
    frames the visual search happened to retrieve for this video contain it
    -- as long as SOME frame of the video's real, full frame list does."""
    video_frames = [_meta(f"V2-0000-{i}.jpg", "V2", i) for i in range(1, 17)]
    _set_corpus(monkeypatch, {"V2" : video_frames})
    _mock_asr_text(monkeypatch, {})
    for frame in video_frames :
        _set_ocr_text(frame["name"], "khong lien quan")
    _set_ocr_text("V2-0000-5.jpg", "mon nghêu hap sa")  # the one real hit, frame 5

    # Visual search only retrieved frame 1 -- frame 5 was never in the top-100.
    result = annotate_videos(["V2"], "nghêu", TextMatchMode.substring,
                              {"V2" : ["V2-0000-1.jpg"]})
    assert result["V2"].matched is True
    assert result["V2"].ocr.match_frame == "V2-0000-5.jpg"
    assert result["V2"].ocr.location == "elsewhere"


# ── bm25 mode ────────────────────────────────────────────────────────────

def _write_bm25_index(tmp_path) :
    """Synthetic BM25 index + windows.jsonl carrying real sample_start/
    sample_rate, so lookup_text()'s window-to-frame mapping has a genuine
    time range to convert (same schema as test_text_lookup.py's helper).

    doc0 (V_A, "meo"): starts at 4000/1000 = 4.0s -> frame_idx 100 @ 25fps
    doc1 (V_A, "cho"): starts at 16000/1000 = 16.0s -> frame_idx 400 @ 25fps
    doc2 (V_B, "meo" x2): starts at 0s -> frame_idx 0
    """
    release_dir = tmp_path / "asr_release"
    bm25_dir = release_dir / "bm25"
    bm25_dir.mkdir(parents=True)

    rows = [
        {"video_id" : "V_A", "eligible" : True, "retrieval_text" : "con meo ngoi tren tham",
         "sample_start" : 4000, "sample_end" : 8000, "sample_rate" : 1000},
        {"video_id" : "V_A", "eligible" : True, "retrieval_text" : "con cho chay ngoai san",
         "sample_start" : 16000, "sample_end" : 20000, "sample_rate" : 1000},
        {"video_id" : "V_B", "eligible" : True, "retrieval_text" : "con meo con meo rat dep",
         "sample_start" : 0, "sample_end" : 4000, "sample_rate" : 1000},
    ]
    with open(release_dir / "windows.jsonl", "w", encoding="utf-8") as f :
        for row in rows :
            f.write(json.dumps(row) + "\n")

    tokens = ["cho", "meo"]
    with open(bm25_dir / "vocabulary.json", "w", encoding="utf-8") as f :
        json.dump({"format_version" : "1.0", "tokens" : tokens}, f)

    # "cho" -> doc1(tf1); "meo" -> doc0(tf1), doc2(tf2)
    posting_doc_ids = np.array([1, 0, 2], dtype=np.uint32)
    posting_term_frequencies = np.array([1, 1, 2], dtype=np.uint32)
    posting_offsets = np.array([0, 1, 3], dtype=np.uint64)
    document_lengths = np.array([5, 5, 6], dtype=np.uint32)

    np.save(bm25_dir / "posting_doc_ids.npy", posting_doc_ids)
    np.save(bm25_dir / "posting_term_frequencies.npy", posting_term_frequencies)
    np.save(bm25_dir / "posting_offsets.npy", posting_offsets)
    np.save(bm25_dir / "document_lengths.npy", document_lengths)

    return str(release_dir)


def test_bm25_scores_and_attributes_to_the_matching_window_frame(monkeypatch, tmp_path) :
    """VideoAnnotation.score is binary (1.0 matched / 0.0 not) in every mode
    since Stage C, bm25 included -- continuous BM25 relevance (V_B's doc has
    "meo" twice, a genuinely higher raw score than V_A's once, confirmed via
    text_lookup's own rank/total_matched) is available at that finer layer,
    not surfaced on VideoAnnotation itself. See Stage C's report."""
    release_dir = _write_bm25_index(tmp_path)
    monkeypatch.setattr(text_signal, "ASR_RELEASE_DIR", release_dir)
    _set_corpus(monkeypatch, {
        "V_A" : [_meta("V_A-0000-100.jpg", "V_A", 100), _meta("V_A-0000-400.jpg", "V_A", 400)],
        "V_B" : [_meta("V_B-0000-0.jpg", "V_B", 0)],
    })

    result = annotate_videos(["V_A", "V_B"], "meo", TextMatchMode.bm25, {})
    assert result["V_B"].matched is True
    assert result["V_B"].score == 1.0
    assert result["V_B"].asr.match_frame == "V_B-0000-0.jpg"
    assert result["V_A"].matched is True
    assert result["V_A"].asr.match_frame == "V_A-0000-100.jpg"
    assert result["V_A"].ocr.location == "none"  # bm25 mode never checks ocr


def test_bm25_query_matching_only_one_video_leaves_other_unmatched(monkeypatch, tmp_path) :
    release_dir = _write_bm25_index(tmp_path)
    monkeypatch.setattr(text_signal, "ASR_RELEASE_DIR", release_dir)
    _set_corpus(monkeypatch, {
        "V_A" : [_meta("V_A-0000-100.jpg", "V_A", 100), _meta("V_A-0000-400.jpg", "V_A", 400)],
        "V_B" : [_meta("V_B-0000-0.jpg", "V_B", 0)],
    })

    result = annotate_videos(["V_A", "V_B"], "cho", TextMatchMode.bm25, {})
    assert result["V_A"].matched is True
    assert result["V_A"].asr.match_frame == "V_A-0000-400.jpg"
    assert result["V_B"].matched is False


def test_bm25_missing_index_reports_no_match(monkeypatch, tmp_path) :
    """Stage C dropped the old "fall back to substring" behavior for bm25
    mode (text_lookup.lookup_text() has no such fallback) -- an unavailable
    BM25 index now simply means no ASR hits, not a silent mode switch."""
    monkeypatch.setattr(text_signal, "ASR_RELEASE_DIR", str(tmp_path / "does_not_exist"))
    _set_corpus(monkeypatch, {"V1" : [_meta("V1-0000-100.jpg", "V1", 100)]})
    _mock_asr_text(monkeypatch, {"V1-0000-100.jpg" : "con meo dang ngu"})

    result = annotate_videos(["V1"], "meo", TextMatchMode.bm25, {})
    assert result["V1"].matched is False
    assert result["V1"].asr.location == "none"


# ── status() reports BM25 unavailability with a real reason ──────────────

def test_status_reports_bm25_unavailable_reason(tmp_path, monkeypatch) :
    """Regression for the production sighting: bm25_ready=false but
    bm25_unavailable_reason=null. That combination meant _load_bm25() had
    never been ATTEMPTED (lazy load, nobody had run a bm25-mode query yet)
    -- not that the reason was being lost on a real failure. Once a load is
    attempted, a real failure must always leave a reason string behind."""
    monkeypatch.setattr(text_signal, "ASR_RELEASE_DIR", str(tmp_path / "does_not_exist"))

    before = text_signal.status()
    assert before["bm25_ready"] is False
    assert before["bm25_unavailable_reason"] is None  # not attempted yet

    annotate_videos(["V1"], "meo", TextMatchMode.bm25, {})  # triggers _load_bm25()

    after = text_signal.status()
    assert after["bm25_ready"] is False
    assert after["bm25_unavailable_reason"] is not None
    assert "FileNotFoundError" in after["bm25_unavailable_reason"]
    assert after["bm25_documents"] == 0


def test_preload_loads_bm25_eagerly(monkeypatch, tmp_path) :
    """preload() (called from main.py's warm-up, same as
    ocr_route.preload()/_asr_text.preload()) must populate status() WITHOUT
    a bm25-mode request ever having been made -- that is the whole point of
    moving BM25 off its old lazy-load path."""
    release_dir = _write_bm25_index(tmp_path)
    monkeypatch.setattr(text_signal, "ASR_RELEASE_DIR", release_dir)

    assert text_signal.status()["bm25_ready"] is False  # nothing has loaded yet
    text_signal.preload()
    status = text_signal.status()
    assert status["bm25_ready"] is True
    assert status["bm25_documents"] == 3
    assert status["bm25_unavailable_reason"] is None


# ── ASR_RELEASE_DIR resolution against AIC_INDEX_DIR ──────────────────────

def test_asr_release_dir_resolves_under_aic_index_dir(monkeypatch) :
    monkeypatch.setenv("AIC_INDEX_DIR", os.path.join("opt", "aic", "indexes"))
    monkeypatch.delenv("AIC_ASR_RELEASE_DIR", raising=False)
    resolved = text_signal._resolve_asr_release_dir()
    assert resolved == os.path.join("opt", "aic", "indexes", "asr")


def test_asr_release_dir_explicit_override_wins(monkeypatch) :
    monkeypatch.setenv("AIC_INDEX_DIR", os.path.join("opt", "aic", "indexes"))
    monkeypatch.setenv("AIC_ASR_RELEASE_DIR", os.path.join("custom", "path"))
    resolved = text_signal._resolve_asr_release_dir()
    assert resolved == os.path.join("custom", "path")


def test_asr_release_dir_falls_back_to_local_indexes_dir_without_aic_index_dir(monkeypatch) :
    monkeypatch.delenv("AIC_INDEX_DIR", raising=False)
    monkeypatch.delenv("AIC_ASR_RELEASE_DIR", raising=False)
    resolved = text_signal._resolve_asr_release_dir()
    expected = os.path.join(
        os.path.dirname(os.path.abspath(text_signal.__file__)), "indexes", "asr")
    assert resolved == expected


# ── independent ASR / OCR filters (annotate_videos_split, annotate_request) ──
#
# annotate_videos() is now a mapping onto annotate_videos_split(). The function
# below is the previous implementation of annotate_videos(), copied verbatim
# (only the names qualified with their module), and is the oracle for the three
# legacy modes: same annotations, same details, for every video.

def _reference_annotate_videos(video_ids, filter_query, mode, frame_names) :
    query = (filter_query or "").strip()
    if not query :
        return {video_id : text_signal.VideoAnnotation(False, 0.0, mode.value, text_signal._NO_MATCH, text_signal._NO_MATCH)
                for video_id in video_ids}

    regex_pattern = None
    if mode == TextMatchMode.regex :
        try :
            regex_pattern = re.compile(query, re.IGNORECASE)
        except re.error :
            return {video_id : text_signal.VideoAnnotation(False, 0.0, mode.value, text_signal._NO_MATCH, text_signal._NO_MATCH)
                    for video_id in video_ids}

    ocr_hits_by_video : dict[str, list] = {}
    asr_hits_by_video : dict[str, list] = {}
    if mode == TextMatchMode.bm25 :
        asr_hits_by_video = text_lookup.lookup_text_batch(query, source="asr", video_ids=video_ids)
    elif mode == TextMatchMode.substring :
        ocr_hits_by_video = text_lookup.lookup_text_batch(query, source="ocr", video_ids=video_ids)

    out : dict[str, text_signal.VideoAnnotation] = {}
    detail_failure_logged = False
    for video_id in video_ids :
        here = frame_names.get(video_id, [])
        try :
            ocr_hits : list = []
            if mode == TextMatchMode.bm25 :
                asr_hits = asr_hits_by_video.get(video_id, [])
                ocr_match = text_signal._NO_MATCH
            elif mode == TextMatchMode.substring :
                asr_hits = text_signal._substring_hits(video_id, query, text_signal.asr_text.get_text)
                ocr_hits = ocr_hits_by_video.get(video_id, [])
                ocr_match = text_signal._best_match(ocr_hits, here)
            elif mode == TextMatchMode.regex :
                asr_hits = text_signal._regex_hits(video_id, regex_pattern, text_signal.asr_text.get_text)
                ocr_hits = text_signal._regex_hits(video_id, regex_pattern, text_signal.ocr_search.get_text)
                ocr_match = text_signal._best_match(ocr_hits, here)
            else :
                raise ValueError(f"unknown TextMatchMode: {mode}")

            asr_match = text_signal._best_match(asr_hits, here)
            for source, match, hits in (("asr", asr_match, asr_hits), ("ocr", ocr_match, ocr_hits)) :
                if match.location == "none" :
                    continue
                try :
                    match.detail = text_signal.describe_match(text_signal._choose_hit(hits, here), source, mode, query, regex_pattern)
                except Exception :
                    if not detail_failure_logged :
                        text_signal.logger.exception("[text_signal] match detail failed (annotation kept without it)")
                        detail_failure_logged = True

            matched = (asr_match.location != "none") or (ocr_match.location != "none")
            out[video_id] = text_signal.VideoAnnotation(matched, 1.0 if matched else 0.0, mode.value, asr_match, ocr_match)
        except Exception :
            out[video_id] = text_signal.VideoAnnotation(False, 0.0, mode.value, text_signal._NO_MATCH, text_signal._NO_MATCH)
    return out


def _as_dicts(annotations) :
    return {video : asdict(annotation) for video, annotation in annotations.items()}


def _mixed_corpus(monkeypatch) :
    """Videos covering every case the legacy function distinguishes:
    E1 exact hits (ASR on the visible frame, OCR on another frame), N1
    accent-insensitive hits on both sources, X1 nothing, O1 hits only on a frame
    that is not in the result set, NF a video without keyframes."""
    _set_corpus(monkeypatch, {
        "E1" : [_meta("E1-0000-100.jpg", "E1", 100), _meta("E1-0000-200.jpg", "E1", 200)],
        "N1" : [_meta("N1-0000-100.jpg", "N1", 100)],
        "X1" : [_meta("X1-0000-100.jpg", "X1", 100)],
        "O1" : [_meta("O1-0000-100.jpg", "O1", 100), _meta("O1-0000-200.jpg", "O1", 200)],
    })
    _mock_asr_text(monkeypatch, {
        "E1-0000-100.jpg" : "rau ngo hap 2018 va nghêu nuong",
        "N1-0000-100.jpg" : "rau ngò rất tươi, nghêu",
        "X1-0000-100.jpg" : "khong lien quan",
        "O1-0000-200.jpg" : "cuoi video co ngo va 2018\nnghêu",
    })
    _set_ocr_text("E1-0000-200.jpg", "mon ngo hap 2018 nghêu")
    _set_ocr_text("N1-0000-100.jpg", "rau ngò tươi", no_marks="rau ngo tuoi")
    _set_ocr_text("O1-0000-200.jpg", "ngo 2018 nghêu")
    return {"E1" : ["E1-0000-100.jpg"], "N1" : ["N1-0000-100.jpg"], "X1" : ["X1-0000-100.jpg"],
            "O1" : ["O1-0000-100.jpg"]}


_MIXED_VIDEOS = ["E1", "N1", "X1", "O1", "NF", "GHOST"]


@pytest.mark.parametrize("mode, query", [
    (TextMatchMode.substring, "ngo"), (TextMatchMode.substring, "2018"), (TextMatchMode.substring, "nghêu"),
    (TextMatchMode.substring, "ngo hap"), (TextMatchMode.substring, "  "),
    (TextMatchMode.regex, r"ngo\s+hap"), (TextMatchMode.regex, r"\d{4}"), (TextMatchMode.regex, r"ngh[eê]u"),
    (TextMatchMode.regex, "(unclosed"), (TextMatchMode.regex, "   "),
])
def test_legacy_annotate_videos_is_identical_to_the_previous_implementation(monkeypatch, mode, query) :
    frames = _mixed_corpus(monkeypatch)
    new = annotate_videos(_MIXED_VIDEOS, query, mode, frames)
    reference = _reference_annotate_videos(_MIXED_VIDEOS, query, mode, frames)
    assert _as_dicts(new) == _as_dicts(reference) and list(new) == list(reference)


def test_the_oracle_really_exercises_matches_and_details(monkeypatch) :
    frames = _mixed_corpus(monkeypatch)
    result = annotate_videos(_MIXED_VIDEOS, "ngo", TextMatchMode.substring, frames)
    assert result["E1"].asr.detail is not None and result["E1"].ocr.detail is not None
    assert result["N1"].asr.match_type == "normalized" and result["N1"].ocr.match_type == "normalized"
    assert result["O1"].asr.location == "elsewhere" and result["X1"].matched is False
    assert result["NF"].matched is False and result["GHOST"].matched is False


@pytest.mark.parametrize("query", ["meo", "cho", "meo cho", "", "  "])
def test_legacy_bm25_annotate_videos_is_identical_to_the_previous_implementation(monkeypatch, tmp_path, query) :
    monkeypatch.setattr(text_signal, "ASR_RELEASE_DIR", _write_bm25_index(tmp_path))
    _set_corpus(monkeypatch, {"V_A" : [_meta("V_A-0000-100.jpg", "V_A", 100), _meta("V_A-0000-400.jpg", "V_A", 400)],
                              "V_B" : [_meta("V_B-0000-0.jpg", "V_B", 0)]})
    videos = ["V_A", "V_B", "V_NONE"]
    frames = {"V_A" : ["V_A-0000-400.jpg"]}
    assert _as_dicts(annotate_videos(videos, query, TextMatchMode.bm25, frames)) == \
        _as_dicts(_reference_annotate_videos(videos, query, TextMatchMode.bm25, frames))


def _split_corpus(monkeypatch) :
    """S1 has ASR "nước sôi" and OCR "NGHÊU NƯỚNG" (display text, as ocr_search
    keeps it) on frame 100; S2 only OCR text "canh nuoc soi"."""
    _set_corpus(monkeypatch, {"S1" : [_meta("S1-0000-100.jpg", "S1", 100)], "S2" : [_meta("S2-0000-100.jpg", "S2", 100)]})
    _mock_asr_text(monkeypatch, {"S1-0000-100.jpg" : "vao bep nước sôi va nghêu hap"})
    _set_ocr_text("S1-0000-100.jpg", "NGHÊU NƯỚNG")
    ocr_search._haystack["with_marks"]["S1-0000-100.jpg"] = "nghêu nướng"
    ocr_search._haystack["no_marks"]["S1-0000-100.jpg"] = "nghieu nuong"
    _set_ocr_text("S2-0000-100.jpg", "canh nuoc soi")
    return {"S1" : ["S1-0000-100.jpg"], "S2" : ["S2-0000-100.jpg"]}


def test_split_asr_only_leaves_ocr_inactive(monkeypatch) :
    frames = _split_corpus(monkeypatch)
    result = text_signal.annotate_videos_split(["S1", "S2"], frames, "nuoc", TextMatchMode.substring, "", None)
    assert result["S1"].asr.match_type == "normalized" and _hit_texts(result["S1"].asr.detail.snippet) == ["nước"]
    assert result["S1"].ocr.location == "none" and result["S1"].ocr.detail is None
    assert result["S2"].matched is False  # S2 has only OCR text, and OCR is inactive
    assert result["S1"].mode == "substring"


def test_split_ocr_only_leaves_asr_inactive(monkeypatch) :
    frames = _split_corpus(monkeypatch)
    result = text_signal.annotate_videos_split(["S1", "S2"], frames, "", None, "nuoc", text_signal.OcrFilterMode.substring)
    assert result["S2"].ocr.match_type == "exact" and result["S2"].asr.location == "none"
    assert result["S1"].asr.location == "none"  # the ASR text contains "nước", but ASR is inactive
    assert result["S1"].mode == "substring"


def test_split_each_source_describes_its_match_with_its_own_term_and_mode(monkeypatch) :
    frames = _split_corpus(monkeypatch)
    result = text_signal.annotate_videos_split(
        ["S1"], frames, "nuoc", TextMatchMode.substring, "ngh[eê]u", text_signal.OcrFilterMode.regex)["S1"]
    assert result.matched is True and result.mode == "mixed"
    assert _hit_texts(result.asr.detail.snippet) == ["nước"]      # ASR substring, accent-insensitive
    assert _hit_texts(result.ocr.detail.snippet) == ["NGHÊU"]     # OCR regex, its own pattern
    assert _plain(result.asr.detail.snippet) != _plain(result.ocr.detail.snippet)


def test_split_with_both_filters_empty_matches_nothing(monkeypatch) :
    frames = _split_corpus(monkeypatch)
    result = text_signal.annotate_videos_split(["S1", "S2"], frames, "  ", TextMatchMode.substring, "", text_signal.OcrFilterMode.regex)
    assert [result[v].matched for v in ("S1", "S2")] == [False, False]
    assert all(r.asr.location == "none" and r.ocr.location == "none" for r in result.values())


def test_split_asr_bm25_with_ocr_regex(monkeypatch, tmp_path) :
    monkeypatch.setattr(text_signal, "ASR_RELEASE_DIR", _write_bm25_index(tmp_path))
    _set_corpus(monkeypatch, {"V_A" : [_meta("V_A-0000-100.jpg", "V_A", 100), _meta("V_A-0000-400.jpg", "V_A", 400)],
                              "V_B" : [_meta("V_B-0000-0.jpg", "V_B", 0)]})
    _set_ocr_text("V_A-0000-100.jpg", "quan an cho lon")
    result = text_signal.annotate_videos_split(
        ["V_A", "V_B"], {}, "meo", TextMatchMode.bm25, r"cho\s+lon", text_signal.OcrFilterMode.regex)
    assert result["V_A"].asr.detail.matched_terms == ["meo"] and result["V_A"].asr.detail.time_approx is True
    assert _hit_texts(result["V_A"].ocr.detail.snippet) == ["cho lon"] and result["V_A"].ocr.detail.time_approx is False
    assert result["V_B"].asr.location != "none" and result["V_B"].ocr.location == "none"


def test_split_an_invalid_asr_regex_turns_off_only_the_asr_source(monkeypatch) :
    frames = _split_corpus(monkeypatch)
    result = text_signal.annotate_videos_split(
        ["S1", "S2"], frames, "(unclosed", TextMatchMode.regex, "nuoc", text_signal.OcrFilterMode.substring)
    assert result["S1"].asr.location == "none"
    assert result["S2"].ocr.location != "none"    # the OCR filter still ran
    assert result["S2"].mode == "mixed"           # and the response still says both filters were requested


def test_split_an_invalid_ocr_regex_turns_off_only_the_ocr_source(monkeypatch) :
    frames = _split_corpus(monkeypatch)
    result = text_signal.annotate_videos_split(
        ["S1", "S2"], frames, "nuoc", TextMatchMode.substring, "(unclosed", text_signal.OcrFilterMode.regex)
    assert result["S1"].asr.location != "none" and result["S1"].ocr.location == "none"


def test_split_ocr_cannot_be_bm25(monkeypatch) :
    """OcrFilterMode has no bm25 and the request model rejects it; if a caller
    passes bm25 anyway the OCR source is simply inactive, never a wrong search."""
    frames = _split_corpus(monkeypatch)
    result = text_signal.annotate_videos_split(["S2"], frames, "", None, "nuoc", TextMatchMode.bm25)
    assert result["S2"].matched is False


def _rows(*names) :
    return [{"video" : name.split("-")[0], "name" : name} for name in names]


def test_request_routing_split_fields_win_over_legacy_fields(monkeypatch) :
    _split_corpus(monkeypatch)
    outcome = text_signal.annotate_request(
        "nuoc", TextMatchMode.substring, "", text_signal.OcrFilterMode.substring,
        "zzz-no-match", TextMatchMode.regex, _rows("S1-0000-100.jpg"))
    assert outcome.asr_filter_active is True and outcome.ocr_filter_active is False and outcome.text_filter_active is True
    assert (outcome.asr_filter_mode, outcome.ocr_filter_mode, outcome.text_filter_mode) == ("substring", None, "substring")
    annotation = outcome.video_annotations["S1"]
    assert annotation["matched"] is True and annotation["mode"] == "substring"  # the legacy regex "zzz-no-match" was ignored


def test_request_routing_legacy_path_runs_when_the_split_fields_are_empty_or_blank(monkeypatch) :
    _split_corpus(monkeypatch)
    for asr_blank, ocr_blank in [("", ""), ("   ", "\t \n")] :
        outcome = text_signal.annotate_request(
            asr_blank, TextMatchMode.bm25, ocr_blank, text_signal.OcrFilterMode.regex,
            "nuoc", TextMatchMode.substring, _rows("S1-0000-100.jpg"))
        assert (outcome.text_filter_active, outcome.asr_filter_active, outcome.ocr_filter_active) == (True, False, False)
        assert (outcome.text_filter_mode, outcome.asr_filter_mode, outcome.ocr_filter_mode) == ("substring", None, None)
        legacy = _as_dicts(annotate_videos(["S1"], "nuoc", TextMatchMode.substring, {"S1" : ["S1-0000-100.jpg"]}))
        assert outcome.video_annotations == legacy


def test_request_routing_nothing_active_returns_no_annotations(monkeypatch) :
    _split_corpus(monkeypatch)
    outcome = text_signal.annotate_request("", TextMatchMode.substring, " ", text_signal.OcrFilterMode.substring,
                                           "  ", TextMatchMode.substring, _rows("S1-0000-100.jpg"))
    assert outcome == text_signal.RequestAnnotation(None, False, None, False, False, None, None)


@pytest.mark.parametrize("asr, ocr, label", [
    (("nuoc", TextMatchMode.bm25), ("", text_signal.OcrFilterMode.substring), "bm25"),
    (("", TextMatchMode.substring), ("ngh[eê]u", text_signal.OcrFilterMode.regex), "regex"),
    (("nuoc", TextMatchMode.bm25), ("ngh[eê]u", text_signal.OcrFilterMode.regex), "mixed"),
    (("nuoc", TextMatchMode.substring), ("nuoc", text_signal.OcrFilterMode.substring), "mixed"),
])
def test_split_mode_labels(monkeypatch, asr, ocr, label) :
    _split_corpus(monkeypatch)
    outcome = text_signal.annotate_request(asr[0], asr[1], ocr[0], ocr[1], "", TextMatchMode.substring, _rows("S1-0000-100.jpg"))
    assert outcome.text_filter_mode == label
    assert outcome.asr_filter_mode == (asr[1].value if asr[0] else None)
    assert outcome.ocr_filter_mode == (ocr[1].value if ocr[0] else None)
    assert {annotation["mode"] for annotation in outcome.video_annotations.values()} == {label}
    assert text_signal._mode_label(None, None) == ""


def test_split_annotations_are_json_serializable_with_and_without_detail(monkeypatch) :
    _split_corpus(monkeypatch)
    rows = _rows("S1-0000-100.jpg")
    with_detail = text_signal.annotate_request("nuoc", TextMatchMode.substring, "ngh[eê]u", text_signal.OcrFilterMode.regex,
                                               "", TextMatchMode.substring, rows)
    payload = json.loads(json.dumps(with_detail.video_annotations, ensure_ascii=False))
    assert payload["S1"]["asr"]["detail"]["snippet"] and payload["S1"]["ocr"]["detail"]["snippet"]

    def boom(*args, **kwargs) :
        raise RuntimeError("boom")

    monkeypatch.setattr(text_signal, "describe_match", boom)
    without_detail = text_signal.annotate_request("nuoc", TextMatchMode.substring, "ngh[eê]u", text_signal.OcrFilterMode.regex,
                                                  "", TextMatchMode.substring, rows)
    payload = json.loads(json.dumps(without_detail.video_annotations, ensure_ascii=False))
    assert payload["S1"]["asr"]["detail"] is None and payload["S1"]["ocr"]["detail"] is None


def test_split_detail_failure_keeps_every_annotation_and_logs_once_per_call(monkeypatch, caplog) :
    frames = _split_corpus(monkeypatch)
    _set_ocr_text("S2-0000-100.jpg", "canh nuoc soi")
    _mock_asr_text(monkeypatch, {"S1-0000-100.jpg" : "nuoc soi", "S2-0000-100.jpg" : "nuoc lanh"})

    def boom(*args, **kwargs) :
        raise RuntimeError("boom")

    baseline = _as_dicts(text_signal.annotate_videos_split(
        ["S1", "S2"], frames, "nuoc", TextMatchMode.substring, "nuoc", text_signal.OcrFilterMode.substring))
    monkeypatch.setattr(text_signal, "describe_match", boom)
    with caplog.at_level("ERROR", logger=text_signal.logger.name) :
        result = _as_dicts(text_signal.annotate_videos_split(
            ["S1", "S2"], frames, "nuoc", TextMatchMode.substring, "nuoc", text_signal.OcrFilterMode.substring))
    for video in ("S1", "S2") :
        for source in ("asr", "ocr") :
            assert result[video][source]["detail"] is None
            assert {k : v for k, v in result[video][source].items() if k != "detail"} == \
                {k : v for k, v in baseline[video][source].items() if k != "detail"}
        assert result[video]["matched"] == baseline[video]["matched"]
    assert sum("match detail failed" in record.getMessage() for record in caplog.records) == 1


def test_request_model_accepts_the_split_fields_and_enforces_the_caps() :
    from pydantic import ValidationError

    from app.main import EnsembleSearchRequest, SingleSearchRequest

    cap = text_signal.TEXT_FILTER_MAX_CHARS
    request = EnsembleSearchRequest(query = "q", asr_filter = "x" * cap, ocr_filter = "y" * cap,
                                    asr_filter_mode = "bm25", ocr_filter_mode = "regex")
    assert (request.asr_filter_mode, request.ocr_filter_mode) == (TextMatchMode.bm25, text_signal.OcrFilterMode.regex)
    for field in ("asr_filter", "ocr_filter") :
        with pytest.raises(ValidationError) :
            EnsembleSearchRequest(query = "q", **{field : "x" * (cap + 1)})
    for mode in ("substring", "regex", "bm25") :
        assert EnsembleSearchRequest(query = "q", asr_filter_mode = mode).asr_filter_mode.value == mode
    with pytest.raises(ValidationError) :
        EnsembleSearchRequest(query = "q", ocr_filter = "x", ocr_filter_mode = "bm25")  # OCR has no BM25

    legacy = EnsembleSearchRequest(query = "q", text_filter = "x" * cap, text_filter_mode = "bm25")
    assert legacy.text_filter_mode == TextMatchMode.bm25 and legacy.asr_filter == "" and legacy.ocr_filter == ""
    with pytest.raises(ValidationError) :
        EnsembleSearchRequest(query = "q", text_filter = "x" * (cap + 1))
    assert SingleSearchRequest(query = "q", ocr_filter = "z").ocr_filter == "z"  # inherited, and ignored by that endpoint


# ── multi-term filters: split_terms() ───────────────────────────────────────

@pytest.mark.parametrize("text, terms", [
    ("lửa, nước", ["lửa", "nước"]),
    ("lửa,nước", ["lửa", "nước"]),
    ("lửa; nước", ["lửa", "nước"]),
    ("lửa;nước", ["lửa", "nước"]),
    ("lửa，nước", ["lửa", "nước"]),                # full-width comma
    ("lửa；nước", ["lửa", "nước"]),                # full-width semicolon
    ("lửa、nước", ["lửa", "nước"]),                # ideographic comma
    ("lửa, nước", ["lửa", "nước"]),           # a comma followed by a no-break space splits
    (" lửa , nước ", ["lửa", "nước"]),  # NBSP is trimmed
    ("1,5", ["1,5"]),                               # decimal comma: digit on both sides
    ("1,5 kg", ["1,5 kg"]),
    ("1,5,2", ["1,5,2"]),
    ("2018,2019", ["2018,2019"]),
    ("2018, 2019", ["2018", "2019"]),
    ("2018;2019", ["2018", "2019"]),
    ("a,1", ["a", "1"]),
    ("1,a", ["1", "a"]),
    ("1,,5", ["1", "5"]),
    ("giá 1,5 kg, quán trọ", ["giá 1,5 kg", "quán trọ"]),
    ("١,٥", ["١", "٥"]),                            # only ASCII digits make a decimal comma
    (",,", []),
    (" , ; ", []),
    ("", []),
    ("   ", []),
    ("lửa,", ["lửa"]),
    (",lửa", ["lửa"]),
    ("  lửa  ", ["lửa"]),
    ("lửa", ["lửa"]),
    ("lửa nước", ["lửa nước"]),                     # a space is not a separator
    ("lửa\tnước", ["lửa\tnước"]),
    ("lửa, Lửa, LỬA", ["lửa"]),                     # duplicates: case-insensitive, first typed form wins
    ("Lửa, lửa", ["Lửa"]),
    ("nuoc, nước", ["nuoc"]),                       # accent-insensitive too: the FIRST typed form wins
    ("nước, nuoc", ["nước"]),
    ("đường, DUONG", ["đường"]),
    ("a, b, c, d, e, f, g", ["a", "b", "c", "d", "e"]),
    ("a, a, b, c, d, e, f", ["a", "b", "c", "d", "e"]),  # duplicates do not use up the cap
])
def test_split_terms_table(text, terms) :
    assert text_signal.split_terms(text) == terms


def test_substring_hits_classifies_each_distinct_text_once_per_video(monkeypatch) :
    """Adjacent keyframes share one transcript window, so the per-video memo must
    run the per-text rule once per DISTINCT text, with the same hits as before."""
    names = [f"V1-0000-{index}.jpg" for index in range(5)]
    _set_corpus(monkeypatch, {"V1" : [_meta(name, "V1", index) for index, name in enumerate(names)]})
    texts = dict(zip(names, ["rau ngò", "rau ngò", "rau ngò", "khong co", "khong co"]))
    calls = []
    real = text_signal._classify_text
    monkeypatch.setattr(text_signal, "_classify_text", lambda *args : calls.append(args[0]) or real(*args))
    hits = text_signal._substring_hits("V1", "ngo", lambda name : texts[name])
    assert sorted(calls) == ["khong co", "rau ngò"]
    assert hits == _reference_substring_hits("V1", "ngo", lambda name : texts[name])
    assert [hit.frame_name for hit in hits] == names[ : 3]


def test_split_terms_keeps_at_most_max_filter_terms() :
    assert text_signal.MAX_FILTER_TERMS == 5
    assert len(text_signal.split_terms(",".join(str(index) for index in "abcdefghij"))) == 5


def test_split_terms_handles_a_request_sized_input() :
    cap = text_signal.TEXT_FILTER_MAX_CHARS
    assert text_signal.split_terms("x" * cap) == ["x" * cap]
    text = ",".join(["ab"] * (cap // 3))  # 200 characters or fewer, one distinct term
    assert len(text) <= cap and text_signal.split_terms(text) == ["ab"]
    distinct = ",".join(f"t{index}" for index in range(60))[ : cap]
    assert len(text_signal.split_terms(distinct)) == text_signal.MAX_FILTER_TERMS


def test_split_terms_without_a_separator_gives_the_stripped_text() :
    """The wiring relies on this: no separator means today's code gets the same string."""
    for text in ["ngò", "quán trọ", "  ngò  ", "a b c", "(", "1.5", "x" * 50] :
        assert text_signal.split_terms(text) == [text.strip()]


# ── multi-term ASR scanner: _substring_matches_multi() ──────────────────────
#
# Contract: for every term the per-frame kinds equal what a separate
# _substring_hits() (and the old per-frame fold, _reference_substring_hits) says.

def _hits_of_term(video_id : str, matches, index : int) :
    """The hit list _substring_hits() returns for terms[index], rebuilt from the
    per-frame kinds with plain loops, independent of the code under test."""
    exact = [name for name, kinds in matches if kinds[index] == "exact"]
    normalized = [name for name, kinds in matches if kinds[index] == "normalized"]
    total = len(exact) + len(normalized)
    hits = [text_lookup.TextHit(video_id, name, "exact", rank, total) for rank, name in enumerate(exact, 1)]
    hits += [text_lookup.TextHit(video_id, name, "normalized", rank, total) for rank, name in enumerate(normalized, len(exact) + 1)]
    return hits


def _reference_combos() -> list[list[str]] :
    """Pairs and triples drawn from REFERENCE_TERMS (accents, uppercase, đ, regex
    specials, other scripts, astral characters, empty and blank terms), plus
    overlapping and accent-variant terms."""
    count = len(REFERENCE_TERMS)
    combos = []
    for k in range(count) :
        combos.append([REFERENCE_TERMS[k], REFERENCE_TERMS[(k * 7 + 3) % count]])
        combos.append([REFERENCE_TERMS[k], REFERENCE_TERMS[(k + 13) % count], REFERENCE_TERMS[(k * 5 + 2) % count]])
    combos += [["nước", "nước sôi"], ["nuoc", "nước", "NƯỚC"], ["ngo", "ngò", "ngõ"], ["thể thao", "the thao"],
               ["d", "đ", "Đ"], ["a", "a b", "ab"], ["sôi", "nước sôi", "nuoc soi"]]
    return combos


def test_multi_term_scan_equals_separate_substring_hits_for_every_term(monkeypatch) :
    names = [f"V1-0000-{index}.jpg" for index in range(len(REFERENCE_TEXTS))]
    _set_corpus(monkeypatch, {"V1" : [_meta(name, "V1", index) for index, name in enumerate(names)]})
    texts = dict(zip(names, REFERENCE_TEXTS))

    def get_text(name : str) -> str :
        return texts.get(name, "")

    combos = _reference_combos()
    assert len(combos) >= 150
    for terms in combos :
        matches = text_signal._substring_matches_multi("V1", terms, get_text)
        for index, term in enumerate(terms) :
            expected = text_signal._substring_hits("V1", term, get_text)
            assert _hits_of_term("V1", matches, index) == expected, (terms, term)
            assert expected == _reference_substring_hits("V1", term, get_text), (terms, term)


def test_multi_term_scan_lists_frames_in_order_and_skips_empty_and_unmatched_frames(monkeypatch) :
    names = [f"V1-0000-{index}.jpg" for index in range(5)]
    _set_corpus(monkeypatch, {"V1" : [_meta(name, "V1", index) for index, name in enumerate(names)]})
    texts = dict(zip(names, ["rau ngò", "", "nước sôi", "khong co", "rau ngo nuoc"]))
    matches = text_signal._substring_matches_multi("V1", ["ngo", "nuoc"], lambda name : texts[name])
    assert matches == [(names[0], ("normalized", None)), (names[2], (None, "normalized")), (names[4], ("exact", "exact"))]
    assert text_signal._substring_matches_multi("V1", [], lambda name : texts[name]) == []
    assert text_signal._substring_matches_multi("GHOST", ["ngo"], lambda name : texts[name]) == []


def test_multi_term_scan_classifies_each_distinct_text_once_per_term(monkeypatch) :
    names = [f"V1-0000-{index}.jpg" for index in range(6)]
    _set_corpus(monkeypatch, {"V1" : [_meta(name, "V1", index) for index, name in enumerate(names)]})
    texts = dict(zip(names, ["rau ngò", "rau ngò", "rau ngò", "khong co", "khong co", "khong co"]))
    calls = []
    real = text_signal._classify_text
    monkeypatch.setattr(text_signal, "_classify_text", lambda *args : calls.append(args[0]) or real(*args))
    text_signal._substring_matches_multi("V1", ["ngo", "co", "zzz"], lambda name : texts[name])
    assert len(calls) == 2 * 3 and sorted(set(calls)) == ["khong co", "rau ngò"]
