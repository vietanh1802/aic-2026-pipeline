# backend/tests/test_text_lookup.py
import json

import numpy as np
import pytest

from app import ocr_search, preprocess, text_lookup, text_signal


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
