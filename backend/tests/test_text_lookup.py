# backend/tests/test_text_lookup.py
import json
import re
from dataclasses import asdict

import numpy as np
import pytest

from app import ocr_search, preprocess, text_lookup, text_signal
from app.text_signal import TextMatchMode, annotate_videos


@pytest.fixture(autouse=True)
def reset_module_state(monkeypatch) :
    """Every backing module keeps module-level cache state -- give each test a
    clean slate, same pattern as test_text_signal.py/test_asr_text.py."""
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
    """videos: video_id -> list of frame metadata dicts (from _meta())."""
    monkeypatch.setattr(preprocess, "_video_frames", videos)


# ── preprocess.frames_for_video / fps_for_video ─────────────────────────────

def test_frames_for_video_returns_names_in_order(monkeypatch) :
    _set_corpus(monkeypatch, {"V1" : [_meta("V1-0000-100.jpg", "V1", 100),
                                       _meta("V1-0000-200.jpg", "V1", 200)]})
    assert preprocess.frames_for_video("V1") == ["V1-0000-100.jpg", "V1-0000-200.jpg"]


def test_frames_for_video_unknown_video_returns_empty(monkeypatch) :
    _set_corpus(monkeypatch, {})
    assert preprocess.frames_for_video("GHOST") == []


def test_fps_for_video_reads_from_first_frame(monkeypatch) :
    _set_corpus(monkeypatch, {"V1" : [_meta("V1-0000-100.jpg", "V1", 100, fps=30.0)]})
    assert preprocess.fps_for_video("V1") == 30.0


def test_fps_for_video_unknown_video_falls_back_to_25(monkeypatch) :
    _set_corpus(monkeypatch, {})
    assert preprocess.fps_for_video("GHOST") == 25.0


# ── OCR: exact vs. normalized tagging ────────────────────────────────────────

def test_ocr_exact_tag_when_query_matches_with_marks(monkeypatch) :
    _set_corpus(monkeypatch, {"V1" : [_meta("V1-0000-100.jpg", "V1", 100)]})
    ocr_search._display["V1-0000-100.jpg"] = "co tu khoa can tim"
    ocr_search._haystack["with_marks"]["V1-0000-100.jpg"] = "co tu khoa can tim"
    ocr_search._haystack["no_marks"]["V1-0000-100.jpg"] = "co tu khoa can tim"

    hits = text_lookup.lookup_text("tu khoa", source="ocr", scope="video", video_id="V1")
    assert len(hits) == 1
    assert hits[0].match_type == "exact"
    assert hits[0].video_id == "V1"
    assert hits[0].frame_name == "V1-0000-100.jpg"


def test_ocr_normalized_tag_when_query_only_matches_after_folding(monkeypatch) :
    _set_corpus(monkeypatch, {"V2" : [_meta("V2-0000-100.jpg", "V2", 100)]})
    # with_marks keeps real diacritics -- "tu khoa" (typed with no accents) will
    # not substring-match "từ khóa" there; no_marks is the pre-folded form.
    ocr_search._display["V2-0000-100.jpg"] = "co từ khóa can tim"
    ocr_search._haystack["with_marks"]["V2-0000-100.jpg"] = "co từ khóa can tim"
    ocr_search._haystack["no_marks"]["V2-0000-100.jpg"] = "co tu khoa can tim"

    hits = text_lookup.lookup_text("tu khoa", source="ocr", scope="video", video_id="V2")
    assert len(hits) == 1
    assert hits[0].match_type == "normalized"


def test_ocr_exact_wins_when_hit_found_both_ways(monkeypatch) :
    _set_corpus(monkeypatch, {"V1" : [_meta("V1-0000-100.jpg", "V1", 100)]})
    ocr_search._display["V1-0000-100.jpg"] = "tu khoa"
    ocr_search._haystack["with_marks"]["V1-0000-100.jpg"] = "tu khoa"
    ocr_search._haystack["no_marks"]["V1-0000-100.jpg"] = "tu khoa"

    hits = text_lookup.lookup_text("tu khoa", source="ocr", scope="video", video_id="V1")
    assert len(hits) == 1  # not reported twice
    assert hits[0].match_type == "exact"


# ── OCR: video-scope vs. corpus-scope ────────────────────────────────────────

def test_ocr_video_scope_excludes_other_videos(monkeypatch) :
    _set_corpus(monkeypatch, {
        "V1" : [_meta("V1-0000-100.jpg", "V1", 100)],
        "V2" : [_meta("V2-0000-100.jpg", "V2", 100)],
    })
    for name in ("V1-0000-100.jpg", "V2-0000-100.jpg") :
        ocr_search._display[name] = "tu khoa"
        ocr_search._haystack["with_marks"][name] = "tu khoa"
        ocr_search._haystack["no_marks"][name] = "tu khoa"

    hits = text_lookup.lookup_text("tu khoa", source="ocr", scope="video", video_id="V1")
    assert {h.video_id for h in hits} == {"V1"}


def test_ocr_corpus_scope_returns_every_indexed_video(monkeypatch) :
    _set_corpus(monkeypatch, {
        "V1" : [_meta("V1-0000-100.jpg", "V1", 100)],
        "V2" : [_meta("V2-0000-100.jpg", "V2", 100)],
    })
    for name in ("V1-0000-100.jpg", "V2-0000-100.jpg") :
        ocr_search._display[name] = "tu khoa"
        ocr_search._haystack["with_marks"][name] = "tu khoa"
        ocr_search._haystack["no_marks"][name] = "tu khoa"

    hits = text_lookup.lookup_text("tu khoa", source="ocr", scope="corpus")
    assert {h.video_id for h in hits} == {"V1", "V2"}


# ── OCR: the 873-video exclusion ─────────────────────────────────────────────

def test_ocr_corpus_scope_excludes_video_outside_visual_corpus(monkeypatch) :
    """K01_V001 stands in for the confirmed K01-K20 gap: real ASR/OCR text
    exists for it, but it was never keyframe-extracted, so it has no entry in
    preprocess._video_frames -- frames_for_video() returns [] for it."""
    _set_corpus(monkeypatch, {"L21_V001" : [_meta("L21_V001-0000-100.jpg", "L21_V001", 100)]})
    for name in ("L21_V001-0000-100.jpg", "K01_V001-0000-50.jpg") :
        ocr_search._display[name] = "tu khoa"
        ocr_search._haystack["with_marks"][name] = "tu khoa"
        ocr_search._haystack["no_marks"][name] = "tu khoa"

    hits = text_lookup.lookup_text("tu khoa", source="ocr", scope="corpus")
    assert "K01_V001" not in {h.video_id for h in hits}
    assert {h.video_id for h in hits} == {"L21_V001"}


# ── ASR: window-to-frame mapping ─────────────────────────────────────────────

def _write_bm25_and_windows(tmp_path) :
    """Synthetic BM25 index (schema matches test_text_signal.py's own helper)
    plus a windows.jsonl carrying real sample_start/sample_end/sample_rate, so
    _windows_by_video() has a genuine time range to convert to a frame."""
    release_dir = tmp_path / "asr_release"
    bm25_dir = release_dir / "bm25"
    bm25_dir.mkdir(parents=True)

    rows = [
        {"video_id" : "V_A", "eligible" : True, "retrieval_text" : "con meo ngoi tren tham",
         "sample_start" : 4000, "sample_end" : 8000, "sample_rate" : 1000},
        {"video_id" : "V_A", "eligible" : True, "retrieval_text" : "con cho chay ngoai san",
         "sample_start" : 16000, "sample_end" : 20000, "sample_rate" : 1000},
    ]
    with open(release_dir / "windows.jsonl", "w", encoding="utf-8") as f :
        for row in rows :
            f.write(json.dumps(row) + "\n")

    tokens = ["cho", "meo"]
    with open(bm25_dir / "vocabulary.json", "w", encoding="utf-8") as f :
        json.dump({"format_version" : "1.0", "tokens" : tokens}, f)

    posting_doc_ids = np.array([1, 0], dtype=np.uint32)          # "cho"->doc1, "meo"->doc0
    posting_term_frequencies = np.array([1, 1], dtype=np.uint32)
    posting_offsets = np.array([0, 1, 2], dtype=np.uint64)
    document_lengths = np.array([5, 5], dtype=np.uint32)

    np.save(bm25_dir / "posting_doc_ids.npy", posting_doc_ids)
    np.save(bm25_dir / "posting_term_frequencies.npy", posting_term_frequencies)
    np.save(bm25_dir / "posting_offsets.npy", posting_offsets)
    np.save(bm25_dir / "document_lengths.npy", document_lengths)

    return str(release_dir)


def test_asr_maps_matching_window_to_nearest_keyframe(monkeypatch, tmp_path) :
    release_dir = _write_bm25_and_windows(tmp_path)
    monkeypatch.setattr(text_signal, "ASR_RELEASE_DIR", release_dir)
    # doc0 ("meo") starts at 4000/1000 = 4.0s; at 25fps that is frame_idx 100 --
    # an exact hit on one of V_A's own real keyframes.
    _set_corpus(monkeypatch, {"V_A" : [_meta("V_A-0000-100.jpg", "V_A", 100),
                                        _meta("V_A-0000-400.jpg", "V_A", 400)]})

    hits = text_lookup.lookup_text("meo", source="asr", scope="video", video_id="V_A")
    assert len(hits) == 1
    assert hits[0].frame_name == "V_A-0000-100.jpg"
    assert hits[0].match_type == "exact"
    assert hits[0].video_id == "V_A"


def test_asr_picks_second_window_when_only_it_matches(monkeypatch, tmp_path) :
    release_dir = _write_bm25_and_windows(tmp_path)
    monkeypatch.setattr(text_signal, "ASR_RELEASE_DIR", release_dir)
    # doc1 ("cho") starts at 16000/1000 = 16.0s; at 25fps that is frame_idx 400.
    _set_corpus(monkeypatch, {"V_A" : [_meta("V_A-0000-100.jpg", "V_A", 100),
                                        _meta("V_A-0000-400.jpg", "V_A", 400)]})

    hits = text_lookup.lookup_text("cho", source="asr", scope="video", video_id="V_A")
    assert len(hits) == 1
    assert hits[0].frame_name == "V_A-0000-400.jpg"


def test_asr_no_hit_when_video_has_no_keyframes(monkeypatch, tmp_path) :
    release_dir = _write_bm25_and_windows(tmp_path)
    monkeypatch.setattr(text_signal, "ASR_RELEASE_DIR", release_dir)
    _set_corpus(monkeypatch, {})  # V_A matches on BM25 but was never keyframe-extracted

    hits = text_lookup.lookup_text("meo", source="asr", scope="video", video_id="V_A")
    assert hits == []


def test_asr_corpus_scope_excludes_video_outside_visual_corpus(monkeypatch, tmp_path) :
    release_dir = _write_bm25_and_windows(tmp_path)
    monkeypatch.setattr(text_signal, "ASR_RELEASE_DIR", release_dir)
    _set_corpus(monkeypatch, {})  # V_A has ASR data but no keyframes at all

    hits = text_lookup.lookup_text("meo", source="asr", scope="corpus")
    assert hits == []


def test_asr_rank_and_total_matched_are_per_video(monkeypatch, tmp_path) :
    """"meo" only ever appears in V_A's doc0 -- one matching video, rank 1."""
    release_dir = _write_bm25_and_windows(tmp_path)
    monkeypatch.setattr(text_signal, "ASR_RELEASE_DIR", release_dir)
    _set_corpus(monkeypatch, {"V_A" : [_meta("V_A-0000-100.jpg", "V_A", 100)]})

    hits = text_lookup.lookup_text("meo", source="asr", scope="corpus")
    assert len(hits) == 1
    assert hits[0].rank == 1
    assert hits[0].total_matched == 1


# ── lookup_text() argument validation and safety ─────────────────────────────

def test_scope_video_without_video_id_raises() :
    with pytest.raises(ValueError) :
        text_lookup.lookup_text("anything", source="ocr", scope="video")


def test_never_raises_on_internal_error(monkeypatch) :
    def boom(*args, **kwargs) :
        raise RuntimeError("simulated failure")
    monkeypatch.setattr(ocr_search, "search", boom)
    assert text_lookup.lookup_text("anything", source="ocr", scope="corpus") == []


# ── preload() ──────────────────────────────────────────────────────────────

def test_preload_warms_the_windows_cache_without_a_lookup_call(monkeypatch, tmp_path) :
    """The whole point: _windows_cache must be populated by preload() alone,
    before any lookup_text() call ever touches it -- same contract as
    asr_text.preload()/ocr_search.preload()/text_signal.preload()."""
    release_dir = _write_bm25_and_windows(tmp_path)
    monkeypatch.setattr(text_signal, "ASR_RELEASE_DIR", release_dir)

    assert text_lookup._windows_cache is None
    text_lookup.preload()
    assert text_lookup._windows_cache is not None
    assert "V_A" in text_lookup._windows_cache


def test_preload_is_idempotent(monkeypatch, tmp_path) :
    release_dir = _write_bm25_and_windows(tmp_path)
    monkeypatch.setattr(text_signal, "ASR_RELEASE_DIR", release_dir)

    text_lookup.preload()
    first = text_lookup._windows_cache
    text_lookup.preload()
    assert text_lookup._windows_cache is first  # not rebuilt


def test_preload_does_not_raise_when_windows_jsonl_is_missing(monkeypatch, tmp_path) :
    monkeypatch.setattr(text_signal, "ASR_RELEASE_DIR", str(tmp_path / "does_not_exist"))
    text_lookup.preload()  # must not raise
    assert text_lookup._windows_cache == {}


def test_preload_does_not_raise_on_a_corrupt_windows_jsonl(monkeypatch, tmp_path) :
    release_dir = tmp_path / "asr_release"
    release_dir.mkdir()
    (release_dir / "windows.jsonl").write_text("{not valid json", encoding="utf-8")
    monkeypatch.setattr(text_signal, "ASR_RELEASE_DIR", str(release_dir))

    text_lookup.preload()  # must not raise
    # _windows_by_video() sets the cache to {} before it starts reading lines,
    # so a mid-parse failure leaves it cached empty rather than unset -- same
    # "fail once, don't retry every call" shape as text_signal's own
    # _bm25_unavailable_reason latch.
    assert text_lookup._windows_cache == {}


# ── ASR: the window that decided the rank, lazy resolution, new TextHit fields ──

def _build_release(tmp_path, windows : list[tuple[str, float, float, str]]) -> str :
    """Synthetic BM25 release from (video_id, start_s, end_s, text) tuples, in
    windows.jsonl file order (== doc id order). Same on-disk schema as
    _write_bm25_and_windows(), but with arbitrary documents."""
    release_dir = tmp_path / "release_b"
    bm25_dir = release_dir / "bm25"
    bm25_dir.mkdir(parents=True)

    rows = [{"video_id" : video, "eligible" : True, "retrieval_text" : text,
             "sample_start" : int(start * 1000), "sample_end" : int(end * 1000), "sample_rate" : 1000}
            for video, start, end, text in windows]
    with open(release_dir / "windows.jsonl", "w", encoding="utf-8") as f :
        for row in rows :
            f.write(json.dumps(row) + "\n")

    postings : dict[str, dict[int, int]] = {}
    lengths = []
    for doc_id, (_video, _start, _end, text) in enumerate(windows) :
        tokens = text_signal._bm25_tokenize(text)
        lengths.append(len(tokens))
        for token in tokens :
            postings.setdefault(token, {})[doc_id] = postings.get(token, {}).get(doc_id, 0) + 1
    vocabulary = sorted(postings)
    doc_ids, term_freqs, offsets = [], [], [0]
    for token in vocabulary :
        for doc_id, tf in sorted(postings[token].items()) :
            doc_ids.append(doc_id)
            term_freqs.append(tf)
        offsets.append(len(doc_ids))

    with open(bm25_dir / "vocabulary.json", "w", encoding="utf-8") as f :
        json.dump({"format_version" : "1.0", "tokens" : vocabulary}, f)
    np.save(bm25_dir / "posting_doc_ids.npy", np.array(doc_ids, dtype=np.uint32))
    np.save(bm25_dir / "posting_term_frequencies.npy", np.array(term_freqs, dtype=np.uint32))
    np.save(bm25_dir / "posting_offsets.npy", np.array(offsets, dtype=np.uint64))
    np.save(bm25_dir / "document_lengths.npy", np.array(lengths, dtype=np.uint32))
    return str(release_dir)


_FILLER = [("V_F", 0.0, 60.0, "mot hai ba bon nam"), ("V_F", 45.0, 105.0, "sau bay tam chin muoi"),
           ("V_G", 0.0, 60.0, "xanh do tim vang den")]


def _frames(video : str, indexes : list[int]) -> list[dict] :
    return [_meta(f"{video}-0000-{i}.jpg", video, i) for i in indexes]


def test_asr_reports_the_window_with_more_query_tokens_not_the_first_one(monkeypatch, tmp_path) :
    """The L25_V075 shape: the FIRST window shares one word with the query, a
    later window has all of them. The frame must come from the later one."""
    release_dir = _build_release(tmp_path, [
        ("V_A", 0.0, 60.0, "thi thi thi la mot tu"),        # doc0: 1 of 3 tokens, repeated
        ("V_A", 400.0, 460.0, "thi hien tai dang dien ra"),  # doc1: all 3 tokens
    ] + _FILLER)
    monkeypatch.setattr(text_signal, "ASR_RELEASE_DIR", release_dir)
    _set_corpus(monkeypatch, {"V_A" : _frames("V_A", [0, 5000, 10000, 10500])})

    hits = text_lookup.lookup_text("thi hien tai", source="asr", scope="corpus")
    assert [(h.video_id, h.frame_name, h.doc_id) for h in hits] == [("V_A", "V_A-0000-10000.jpg", 1)]  # 400 s = frame 10000


def test_asr_two_token_shape_also_picks_the_later_window(monkeypatch, tmp_path) :
    release_dir = _build_release(tmp_path, [
        ("V_A", 0.0, 60.0, "thi la mot tu"), ("V_A", 400.0, 460.0, "thi hien dang dien ra")] + _FILLER)
    monkeypatch.setattr(text_signal, "ASR_RELEASE_DIR", release_dir)
    _set_corpus(monkeypatch, {"V_A" : _frames("V_A", [0, 10000])})

    hits = text_lookup.lookup_text("thi hien", source="asr", scope="corpus")
    assert hits[0].frame_name == "V_A-0000-10000.jpg"


def test_asr_equal_scores_resolve_to_the_earliest_window_whatever_the_doc_order(monkeypatch, tmp_path) :
    """Two identical windows score identically. The LATER doc id starts EARLIER
    (documents out of time order): the earliest start must win, not the doc the
    scoring loop met first."""
    release_dir = _build_release(tmp_path, [
        ("V_A", 400.0, 460.0, "meo ngoi tren tham"),   # doc0, later in time
        ("V_A", 40.0, 100.0, "meo ngoi tren tham"),    # doc1, earlier in time
    ] + _FILLER)
    monkeypatch.setattr(text_signal, "ASR_RELEASE_DIR", release_dir)
    _set_corpus(monkeypatch, {"V_A" : _frames("V_A", [1000, 10000])})

    for _ in range(3) :  # deterministic, not an iteration-order accident
        best = text_signal._best_windows_bm25(["V_A"], "meo")
        assert best["V_A"][1] == 1
    hits = text_lookup.lookup_text("meo", source="asr", scope="corpus")
    assert hits[0].frame_name == "V_A-0000-1000.jpg" and hits[0].doc_id == 1  # 40 s = frame 1000


def test_asr_equal_score_and_equal_start_resolve_to_the_lowest_doc_id(monkeypatch, tmp_path) :
    release_dir = _build_release(tmp_path, [
        ("V_A", 40.0, 100.0, "meo ngoi tren tham"), ("V_A", 40.0, 100.0, "meo ngoi tren tham")] + _FILLER)
    monkeypatch.setattr(text_signal, "ASR_RELEASE_DIR", release_dir)
    assert text_signal._best_windows_bm25(["V_A"], "meo")["V_A"][1] == 0


def _multi_video_release(tmp_path, monkeypatch) :
    """V_K has the best score but no keyframes (a K01-K20 stand-in), V_X is
    second, V_Y third, V_Z fourth. All four match "meo"."""
    release_dir = _build_release(tmp_path, [
        ("V_K", 10.0, 70.0, "meo meo meo meo"), ("V_X", 20.0, 80.0, "meo meo meo ngoi"),
        ("V_Y", 30.0, 90.0, "meo meo ngoi tren"), ("V_Z", 40.0, 100.0, "meo ngoi tren tham xanh")] + _FILLER)
    monkeypatch.setattr(text_signal, "ASR_RELEASE_DIR", release_dir)
    _set_corpus(monkeypatch, {"V_X" : _frames("V_X", [500, 600]), "V_Y" : _frames("V_Y", [750]),
                              "V_Z" : _frames("V_Z", [1000])})


def _key(hit) :
    return (hit.video_id, hit.frame_name, hit.match_type, hit.rank, hit.total_matched, hit.doc_id)


def test_asr_only_videos_gives_the_same_hits_as_full_resolution(monkeypatch, tmp_path) :
    _multi_video_release(tmp_path, monkeypatch)
    full = text_lookup._lookup_asr("meo", "corpus", None)
    assert [h.video_id for h in full] == ["V_X", "V_Y", "V_Z"]  # V_K has no keyframes: dropped, rank 1 left as a gap
    assert [h.rank for h in full] == [2, 3, 4] and {h.total_matched for h in full} == {4}

    # V_Y and V_Z are requested; V_X (outranks both) and V_K (outranks all) are not.
    lazy = text_lookup._lookup_asr("meo", "corpus", None, only_videos={"V_Y", "V_Z"})
    assert [_key(h) for h in lazy] == [_key(h) for h in full if h.video_id in {"V_Y", "V_Z"}]
    assert "V_X" not in {h.video_id for h in lazy}


def test_lookup_text_batch_asr_matches_a_full_lookup_for_the_requested_videos(monkeypatch, tmp_path) :
    _multi_video_release(tmp_path, monkeypatch)
    full = text_lookup._lookup_asr("meo", "corpus", None)
    batch = text_lookup.lookup_text_batch("meo", "asr", ["V_Z", "V_K", "V_GHOST"])
    assert [_key(h) for h in batch["V_Z"]] == [_key(h) for h in full if h.video_id == "V_Z"]
    assert batch["V_K"] == [] and batch["V_GHOST"] == []  # K-video and unknown video stay excluded


def test_asr_video_without_keyframes_is_excluded_with_and_without_only_videos(monkeypatch, tmp_path) :
    _multi_video_release(tmp_path, monkeypatch)
    assert "V_K" not in {h.video_id for h in text_lookup._lookup_asr("meo", "corpus", None)}
    assert text_lookup._lookup_asr("meo", "corpus", None, only_videos={"V_K"}) == []
    # scope="video" is unchanged too: no keyframes means no hit.
    assert text_lookup._lookup_asr("meo", "video", "V_K") == []


def test_asr_hits_carry_doc_id_and_no_exact_phrase(monkeypatch, tmp_path) :
    _multi_video_release(tmp_path, monkeypatch)
    hits = text_lookup.lookup_text("meo", source="asr", scope="corpus")
    assert all(isinstance(h.doc_id, int) and h.exact_phrase is None for h in hits)


def test_ocr_hits_carry_exact_phrase_and_no_doc_id(monkeypatch) :
    _set_corpus(monkeypatch, {"V1" : _frames("V1", [100, 200])})
    for name, text in (("V1-0000-100.jpg", "quan an cho lon"), ("V1-0000-200.jpg", "cho o lon quan an")) :
        ocr_search._display[name] = text
        ocr_search._haystack["with_marks"][name] = text
        ocr_search._haystack["no_marks"][name] = text

    hits = {h.frame_name : h for h in text_lookup.lookup_text("quan an cho lon", source="ocr", scope="corpus")}
    assert hits["V1-0000-100.jpg"].exact_phrase is True    # the whole phrase
    assert hits["V1-0000-200.jpg"].exact_phrase is False   # the same words, scattered
    assert all(h.doc_id is None for h in hits.values())


def test_text_hit_still_accepts_the_original_five_positional_fields() :
    hit = text_lookup.TextHit("V1", "V1-0000-1.jpg", "exact", 3, 9)
    assert (hit.rank, hit.total_matched, hit.exact_phrase, hit.doc_id) == (3, 9, None, None)


def test_annotate_bm25_keeps_its_return_type_and_values(monkeypatch, tmp_path) :
    _multi_video_release(tmp_path, monkeypatch)
    scores = text_signal._annotate_bm25(["V_X", "V_Y", "V_NONE"], "meo")
    assert list(scores) == ["V_X", "V_Y", "V_NONE"] and all(isinstance(v, float) for v in scores.values())
    assert scores["V_NONE"] == 0.0 and 0 < scores["V_Y"] < scores["V_X"] == 1.0  # normalized over the requested videos
    best = text_signal._best_windows_bm25(["V_X", "V_Y", "V_NONE"], "meo")
    assert scores == text_signal._normalize_bm25(best, ["V_X", "V_Y", "V_NONE"])


# ── match detail for bm25 (ASR) and the corpus-only rank fields ─────────────

def _detail_of(video : str, term : str, frames : dict[str, list[str]]) :
    return annotate_videos([video], term, TextMatchMode.bm25, frames)[video].asr


def _l25_shape(tmp_path, monkeypatch) :
    """The L25_V075 shape: the first window shares one word with the query, the
    best window (400-460 s) holds all three."""
    release_dir = _build_release(tmp_path, [
        ("V_A", 0.0, 60.0, "xin chao cac ban thi la mot tu rat hay"),
        ("V_A", 400.0, 460.0, "hom nay hoc thi hien tai don va thi hien tai tiep dien cac ban nhe"),
    ] + _FILLER)
    monkeypatch.setattr(text_signal, "ASR_RELEASE_DIR", release_dir)
    _set_corpus(monkeypatch, {"V_A" : _frames("V_A", [0, 5000, 10000, 10500])})
    return {"V_A" : ["V_A-0000-0.jpg"]}


def test_bm25_detail_full_match_lists_every_query_token_and_marks_them(monkeypatch, tmp_path) :
    frames = _l25_shape(tmp_path, monkeypatch)
    asr = _detail_of("V_A", "thi hien tai", frames)
    detail = asr.detail
    assert asr.match_frame == "V_A-0000-10000.jpg"                 # the best window, not the first one
    assert (detail.matched_terms, detail.terms_total) == (["thi", "hien", "tai"], 3)
    assert {text for text, is_hit in detail.snippet if is_hit} == {"thi", "hien", "tai"}
    assert (detail.start_s, detail.end_s, detail.time_approx) == (400.0, 460.0, True)
    assert detail.start_s <= detail.at_s <= detail.end_s
    assert detail.at_s > 400.0 and detail.exact_phrase is None


def test_bm25_detail_partial_single_and_repeated_query_tokens(monkeypatch, tmp_path) :
    frames = _l25_shape(tmp_path, monkeypatch)
    partial = _detail_of("V_A", "thi hien khongco", frames).detail
    assert (partial.matched_terms, partial.terms_total) == (["thi", "hien"], 3)
    single = _detail_of("V_A", "hien", frames).detail
    assert (single.matched_terms, single.terms_total) == (["hien"], 1)
    repeated = _detail_of("V_A", "hien hien thi", frames).detail
    assert (repeated.matched_terms, repeated.terms_total) == (["hien", "thi"], 2)  # distinct, in query order


def test_bm25_detail_moment_follows_the_densest_cluster_inside_the_window(monkeypatch, tmp_path) :
    early = " ".join(["day", "la", "cau", "dai"] * 20)
    release_dir = _build_release(tmp_path, [
        ("V_A", 100.0, 160.0, early + " meo ngu " + early)] + _FILLER)
    monkeypatch.setattr(text_signal, "ASR_RELEASE_DIR", release_dir)
    _set_corpus(monkeypatch, {"V_A" : _frames("V_A", [2500, 3500, 4000])})
    detail = _detail_of("V_A", "meo", {"V_A" : ["V_A-0000-2500.jpg"]}).detail
    assert 100.0 <= detail.at_s <= 160.0
    assert abs(detail.at_s - 130.0) < 5.0  # the match sits in the middle of the window's text


def test_corpus_rank_ignores_videos_without_keyframes_that_hold_raw_ranks(monkeypatch, tmp_path) :
    _multi_video_release(tmp_path, monkeypatch)  # V_K: raw rank 1, no keyframes
    frames = {"V_X" : ["V_X-0000-500.jpg"], "V_Y" : ["V_Y-0000-750.jpg"], "V_Z" : ["V_Z-0000-1000.jpg"]}
    result = annotate_videos(["V_X", "V_Y", "V_Z"], "meo", TextMatchMode.bm25, frames)
    assert [(v, result[v].asr.detail.rank, result[v].asr.detail.total_matched) for v in ("V_X", "V_Y", "V_Z")] == [
        ("V_X", 1, 3), ("V_Y", 2, 3), ("V_Z", 3, 3)]
    raw = {h.video_id : (h.rank, h.total_matched) for h in text_lookup._lookup_asr("meo", "corpus", None)}
    assert raw == {"V_X" : (2, 4), "V_Y" : (3, 4), "V_Z" : (4, 4)}  # TextHit.rank / total_matched keep their raw meaning


def test_lazy_resolution_still_gives_the_same_corpus_rank(monkeypatch, tmp_path) :
    _multi_video_release(tmp_path, monkeypatch)
    full = {h.video_id : (h.corpus_video_rank, h.corpus_videos_matched) for h in text_lookup._lookup_asr("meo", "corpus", None)}
    lazy = {h.video_id : (h.corpus_video_rank, h.corpus_videos_matched)
            for h in text_lookup._lookup_asr("meo", "corpus", None, only_videos={"V_Z"})}
    assert lazy == {"V_Z" : full["V_Z"]} and full["V_Z"] == (3, 3)


def test_asr_video_scope_leaves_the_corpus_rank_empty(monkeypatch, tmp_path) :
    _multi_video_release(tmp_path, monkeypatch)
    hits = text_lookup._lookup_asr("meo", "video", "V_X")
    assert [(h.corpus_video_rank, h.corpus_videos_matched) for h in hits] == [(None, None)]


def test_ocr_hits_get_dense_video_ranks_by_first_appearance(monkeypatch) :
    _set_corpus(monkeypatch, {"V1" : _frames("V1", [100, 200, 300]), "V2" : _frames("V2", [100])})
    for name, text in (("V1-0000-100.jpg", "quan an cho lon"), ("V1-0000-200.jpg", "cho lon"), ("V2-0000-100.jpg", "lon")) :
        ocr_search._display[name] = text
        ocr_search._haystack["with_marks"][name] = text
        ocr_search._haystack["no_marks"][name] = text
    by_video = text_lookup.lookup_text_batch("lon", "ocr", ["V1", "V2"])
    ranks = {(h.video_id, h.frame_name) : (h.corpus_video_rank, h.corpus_videos_matched) for hits in by_video.values() for h in hits}
    assert {value for value in ranks.values()} == {(1, 2), (2, 2)}          # two videos, whatever the frame count
    assert len({v for (video, _), v in ranks.items() if video == "V1"}) == 1  # both V1 frames share V1's rank


def test_detail_survives_json_and_keeps_the_original_source_keys(monkeypatch, tmp_path) :
    frames = _l25_shape(tmp_path, monkeypatch)
    annotation = annotate_videos(["V_A"], "thi hien tai", TextMatchMode.bm25, frames)["V_A"]
    payload = json.loads(json.dumps(asdict(annotation), ensure_ascii=False))
    assert {"match_frame", "match_type", "location"} <= set(payload["asr"]) and "detail" in payload["asr"]
    assert payload["ocr"]["detail"] is None and payload["ocr"]["location"] == "none"


# ── multi-term OCR lookup: lookup_text_batch_multi() ────────────────────────

_MULTI_TEXTS = {
    "V1-0000-1.jpg" : "Quán ăn Chợ Lớn",
    "V1-0000-2.jpg" : "chợ nổi",
    "V1-0000-3.jpg" : "thịt bò nướng",
    "V2-0000-1.jpg" : "Nước sôi, thịt bò",
    "V2-0000-2.jpg" : "nuoc soi",
    "V2-0000-3.jpg" : "Nước soi va lửa",
    "V3-0000-1.jpg" : "nghêu hấp",
    "V3-0000-2.jpg" : "xxx",
    "V4-0000-1.jpg" : "Chợ Lớn thịt bò",
    "K1-0000-1.jpg" : "chợ lớn thịt bò",  # video outside the visual corpus (no keyframes)
}
_MULTI_VIDEOS = ["V1", "V2", "V3", "V4", "K1", "GHOST"]


def _multi_corpus(monkeypatch) -> None :
    """Real backing dicts of ocr_search, filled the way _load() fills them; K1 has
    OCR text but no entry in the visual corpus."""
    videos : dict[str, list[dict]] = {}
    for name in _MULTI_TEXTS :
        video, _block, tail = name.split("-")
        if video != "K1" :
            videos.setdefault(video, []).append(_meta(name, video, int(tail.split(".")[0])))
    _set_corpus(monkeypatch, videos)
    for name, text in _MULTI_TEXTS.items() :
        ocr_search._display[name] = text
        ocr_search._haystack["with_marks"][name] = text.lower()
        ocr_search._haystack["no_marks"][name] = ocr_search._strip_marks(text).lower()


def _reference_multi_ocr(terms : list[str], video_ids : list[str]) -> dict[str, list] :
    """The multi-term OCR rules restated with plain loops and no shared code:
    per pass and per term "every word of the term is in the text, whole phrase or
    not"; a term is exact when the exact pass matched it; frames order by most
    terms, exact tier first, more whole-phrase terms, shorter text, name; rank and
    total are the frame's position and the size of its own pass; the video rank is
    the order of first appearance of the video in the frame ranking."""
    def words(needle : str) -> set[str] :
        return {word for word in re.split(r"[^0-9a-zA-ZÀ-ỹ]+", needle) if word}

    per_pass : dict[str, dict[str, list]] = {"exact" : {}, "normalized" : {}}
    for tier, folded in (("exact", False), ("normalized", True)) :
        for name, text in _MULTI_TEXTS.items() :
            haystack = (ocr_search._strip_marks(text) if folded else text).lower()
            found = []
            for index, term in enumerate(terms) :
                needle = (ocr_search._strip_marks(term) if folded else term).lower().strip()
                if needle and all(word in haystack for word in words(needle)) :
                    found.append((index, needle in haystack))
            if found :
                per_pass[tier][name] = found

    pass_rank = {}
    for tier, frames in per_pass.items() :
        ordered = sorted(frames, key = lambda name : (-len(frames[name]), -sum(1 for _i, phrase in frames[name] if phrase),
                                                       len(_MULTI_TEXTS[name]), name))
        pass_rank[tier] = {name : rank for rank, name in enumerate(ordered, 1)}

    merged : dict[str, list] = {}
    for name in _MULTI_TEXTS :
        if name.startswith("K1-") :
            continue  # outside the visual corpus
        by_term = {}
        for tier in ("normalized", "exact") :  # the exact pass overrides
            for index, phrase in per_pass[tier].get(name, []) :
                by_term[index] = (tier, phrase)
        if by_term :
            merged[name] = [(index, *by_term[index]) for index in sorted(by_term)]

    def key(name : str) -> tuple :
        hits = merged[name]
        return (-len(hits), int(any(tier == "normalized" for _i, tier, _p in hits)),
                -sum(1 for _i, _t, phrase in hits if phrase), len(_MULTI_TEXTS[name]), name)

    ranking = sorted(merged, key = key)
    video_order : list[str] = []
    for name in ranking :
        if name.split("-")[0] not in video_order :
            video_order.append(name.split("-")[0])

    out : dict[str, list] = {}
    for video in video_ids :
        out[video] = []
        for name in ranking :
            if name.split("-")[0] != video :
                continue
            hits = merged[name]
            tier = "normalized" if any(t == "normalized" for _i, t, _p in hits) else "exact"
            out[video].append(text_lookup.TextHit(
                video, name, tier, pass_rank[tier][name], len(per_pass[tier]), exact_phrase = all(p for _i, _t, p in hits),
                corpus_video_rank = video_order.index(video) + 1, corpus_videos_matched = len(video_order),
                term_hits = tuple(hits) if len(terms) > 1 else None))
    return out


@pytest.mark.parametrize("term", ["chợ lớn", "lớn chợ", "chợ", "cho lon", "nước", "nuoc", "sôi", "thịt bò", "thit bo",
                                  "quán ăn", "xxx", "zzz", "(", "-", "🙂", "", "   "])
def test_multi_lookup_with_one_term_equals_lookup_text_batch(monkeypatch, term) :
    """Proof (a): a list of ONE term gives exactly the hits of lookup_text_batch()
    once its row cap is out of the way (token-less terms included: search()'s
    quirk of matching every frame carries over). term_hits stays None."""
    _multi_corpus(monkeypatch)
    monkeypatch.setattr(text_lookup, "OCR_LIMIT", 10 ** 6)
    assert text_lookup.lookup_text_batch_multi([term], "ocr", _MULTI_VIDEOS) == text_lookup.lookup_text_batch(term, "ocr", _MULTI_VIDEOS)


def test_the_one_term_proof_really_compares_hits(monkeypatch) :
    _multi_corpus(monkeypatch)
    monkeypatch.setattr(text_lookup, "OCR_LIMIT", 10 ** 6)
    hits = text_lookup.lookup_text_batch_multi(["chợ lớn"], "ocr", _MULTI_VIDEOS)
    assert [hit.frame_name for hit in hits["V1"]] == ["V1-0000-1.jpg"] and hits["V1"][0].exact_phrase is True
    assert hits["K1"] == [] and hits["GHOST"] == [] and hits["V1"][0].term_hits is None
    assert len(text_lookup.lookup_text_batch("(", "ocr", _MULTI_VIDEOS)["V3"]) == 2  # the quirk: every frame


@pytest.mark.parametrize("terms", [
    ["chợ lớn", "thịt bò"], ["nước", "sôi"], ["nuoc", "thịt bò", "lửa"], ["quán ăn", "lớn chợ"], ["nghêu", "xxx", "zzz"],
    ["cho", "lon"], ["chợ", "chợ lớn"], ["zzz", "qqq"], ["Nước", "NƯỚC", "nuoc"], ["", "thịt bò"], ["xxx", "chợ lớn", "nổi"],
])
def test_multi_lookup_equals_a_brute_force_reference(monkeypatch, terms) :
    """Proof (b): the same hits, ranks, totals, tiers, phrase flags and term_hits
    as a plain restatement of the rules on a small synthetic corpus."""
    _multi_corpus(monkeypatch)
    assert text_lookup.lookup_text_batch_multi(terms, "ocr", _MULTI_VIDEOS) == _reference_multi_ocr(terms, _MULTI_VIDEOS)


def test_a_two_term_frame_outranks_a_one_term_frame(monkeypatch) :
    """Proof (c)."""
    _multi_corpus(monkeypatch)
    hits = text_lookup.lookup_text_batch_multi(["chợ lớn", "thịt bò"], "ocr", _MULTI_VIDEOS)
    assert hits["V4"][0].term_hits == ((0, "exact", True), (1, "exact", True))
    assert hits["V4"][0].corpus_video_rank == 1
    assert all(len(hit.term_hits) == 1 for video in ("V1", "V2") for hit in hits[video])
    assert min(hit.corpus_video_rank for video in ("V1", "V2") for hit in hits[video]) > 1
    assert hits["V1"][0].frame_name == "V1-0000-3.jpg"  # equal terms and tier: the shorter text wins


def test_exact_and_folded_matches_merge_per_frame_with_the_worst_tier(monkeypatch) :
    """Proof (d): a term is exact when the exact pass matched it, else normalized,
    and the frame's tier is the worst of its terms."""
    _multi_corpus(monkeypatch)
    hits = text_lookup.lookup_text_batch_multi(["nước", "sôi"], "ocr", _MULTI_VIDEOS)["V2"]
    assert [hit.frame_name for hit in hits] == ["V2-0000-1.jpg", "V2-0000-2.jpg", "V2-0000-3.jpg"]
    assert [hit.match_type for hit in hits] == ["exact", "normalized", "normalized"]
    assert hits[0].term_hits == ((0, "exact", True), (1, "exact", True))
    assert hits[1].term_hits == ((0, "normalized", True), (1, "normalized", True))
    assert hits[2].term_hits == ((0, "exact", True), (1, "normalized", True))  # mixed: exact nước, folded sôi


def test_exact_phrase_is_true_only_when_every_matched_term_is_a_whole_phrase(monkeypatch) :
    _multi_corpus(monkeypatch)
    hits = text_lookup.lookup_text_batch_multi(["quán ăn", "lớn chợ"], "ocr", ["V1"])["V1"]
    assert hits[0].frame_name == "V1-0000-1.jpg" and hits[0].term_hits == ((0, "exact", True), (1, "exact", False))
    assert hits[0].exact_phrase is False   # "quán ăn" is a phrase there, "lớn chợ" is scattered words
    only_phrase = text_lookup.lookup_text_batch_multi(["quán ăn", "nổi"], "ocr", ["V1"])["V1"]
    assert only_phrase[0].exact_phrase is True


def test_multi_lookup_excludes_videos_outside_the_corpus(monkeypatch) :
    """Proof (e): K1 holds the text but has no keyframes; it is neither returned
    nor counted in corpus_videos_matched."""
    _multi_corpus(monkeypatch)
    hits = text_lookup.lookup_text_batch_multi(["chợ lớn", "thịt bò"], "ocr", ["K1", "V4"])
    assert hits["K1"] == [] and hits["V4"][0].corpus_videos_matched == 3   # V4, V1, V2 (not K1)


def test_multi_lookup_dense_video_ranks(monkeypatch) :
    """Proof (f): a video ranks by its best frame, two frames of one video share the
    rank, and the total counts corpus videos with at least one match."""
    _multi_corpus(monkeypatch)
    hits = text_lookup.lookup_text_batch_multi(["chợ", "thịt bò", "nước"], "ocr", ["V1", "V2", "V3", "V4"])
    ranks = {video : {hit.corpus_video_rank for hit in frames} for video, frames in hits.items()}
    assert all(len(video_ranks) == 1 for video_ranks in ranks.values() if video_ranks)
    assert hits["V3"] == [] and ranks["V3"] == set()
    ordered = sorted((next(iter(video_ranks)), video) for video, video_ranks in ranks.items() if video_ranks)
    assert [rank for rank, _video in ordered] == [1, 2, 3] and {hit.corpus_videos_matched for frames in hits.values() for hit in frames} == {3}


def test_multi_lookup_ignores_the_single_term_row_cap(monkeypatch) :
    """Proof (g): OCR_LIMIT truncates lookup_text_batch(); the multi path keeps
    every matching frame."""
    _multi_corpus(monkeypatch)
    monkeypatch.setattr(text_lookup, "OCR_LIMIT", 1)
    capped = text_lookup.lookup_text_batch("thịt bò", "ocr", _MULTI_VIDEOS)
    assert sum(len(frames) for frames in capped.values()) == 1          # only the single best row of each pass survives (the same frame)
    multi = text_lookup.lookup_text_batch_multi(["thịt bò", "zzz"], "ocr", _MULTI_VIDEOS)
    assert {video : [hit.frame_name for hit in frames] for video, frames in multi.items() if frames} == {
        "V1" : ["V1-0000-3.jpg"], "V2" : ["V2-0000-1.jpg"], "V4" : ["V4-0000-1.jpg"]}


def test_multi_lookup_only_builds_hits_for_the_requested_videos(monkeypatch) :
    _multi_corpus(monkeypatch)
    hits = text_lookup.lookup_text_batch_multi(["chợ lớn", "thịt bò"], "ocr", ["V1"])
    assert list(hits) == ["V1"] and hits["V1"][0].corpus_videos_matched == 3   # ranks still count every corpus video


def test_multi_lookup_never_raises_and_logs_the_failure(monkeypatch, caplog) :
    _multi_corpus(monkeypatch)

    def boom(*args, **kwargs) :
        raise RuntimeError("boom")

    monkeypatch.setattr(ocr_search, "search_terms", boom)
    with caplog.at_level("ERROR", logger = text_lookup.logger.name) :
        hits = text_lookup.lookup_text_batch_multi(["a", "b"], "ocr", ["V1", "V2"])
    assert hits == {"V1" : [], "V2" : []}
    assert sum("multi-term OCR lookup failed" in record.getMessage() for record in caplog.records) == 1


def test_multi_lookup_supports_ocr_only() :
    with pytest.raises(ValueError) :
        text_lookup.lookup_text_batch_multi(["a", "b"], "asr", ["V1"])  # type: ignore[arg-type]


def test_term_hits_field_defaults_to_none_and_keeps_positional_construction() :
    hit = text_lookup.TextHit("V1", "V1-0000-1.jpg", "exact", 3, 9)
    assert hit.term_hits is None and hit == text_lookup.TextHit("V1", "V1-0000-1.jpg", "exact", 3, 9, None, None, None, None)
