# scripts/check_text_artifacts.py
"""Is the OCR and ASR text really there, and does the annotation code find it? Loads NO encoder model.

The first real ablation run recorded ASR as "flagged nothing" for all 86 round 1 to 3 queries although every
reference video is an L video with full ASR. This script separates the three possible causes:

  1. the files are missing or at another path in this container       -> section 1 shows path, exists, size
  2. the files are there but this process never read them             -> section 2 (asr_text.get_text() does not
     load by itself, only asr_text.preload() does; the suite script never called it)
  3. the data really holds no match for the term                       -> section 4 looks the term up in the reference
     video with the same function the annotation uses and prints the matched snippet

Section 3 counts keyframes that carry OCR text and ASR text per video prefix with the SAME get_text functions
annotation uses, so a number here is the number text_coverage records.

It also lists which deployed module reads which ASR file: the dense E5 files (e5_embeddings.npy and the id maps)
are on disk but no module of this checkout reads them.

Run inside the API container (it needs the same AIC_INDEX_DIR and the metadata, about 4 GB of RAM, no GPU):

    docker exec -e AIC_INDEX_DIR=/opt/aic/indexes $CID python /tmp/ablation/scripts/check_text_artifacts.py

Exit code 1 when the ASR index is empty or an L video has no ASR text.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
# Before any `import app`: the checkout this script lives in must win over an `app` package already in the image.
sys.path.insert(0, str(REPO_ROOT / "backend"))

if hasattr(sys.stdout, "reconfigure") :
    sys.stdout.reconfigure(encoding = "utf-8")

from app import asr_text, ocr_search, preprocess, text_signal  # noqa: E402
from app.evaluation import cues, text_length, text_measures  # noqa: E402
from app.evaluation.seed import SEEDS_DIR  # noqa: E402

PREFIXES       = ("L", "M", "N", "S")
LOOKUP_DATASET = "round2-v2"
LOOKUP_CUES    = 5
E5_FILES       = ("e5_embeddings.npy", "eligible_to_physical.npy", "eligible_window_ids.json", "manifest.json")


def size_of(path : str) -> str :
    return f"{os.path.getsize(path):,} bytes" if os.path.isfile(path) else ("directory" if os.path.isdir(path) else "MISSING")


def describe(label : str, path : str, reader : str) -> None :
    print(f"  {'yes' if os.path.exists(path) else 'NO ':3} {size_of(path):>20}  {path}   [{label}; read by {reader}]")


def section_files() -> None :
    print("== 1. artifact files (path, exists, size)")
    print(f"  AIC_INDEX_DIR={os.environ.get('AIC_INDEX_DIR')}  AIC_OCR_DIR={os.environ.get('AIC_OCR_DIR')}  AIC_ASR_RELEASE_DIR={os.environ.get('AIC_ASR_RELEASE_DIR')}")
    release = text_signal.ASR_RELEASE_DIR
    describe("keyframe metadata", preprocess.META_PATH, "preprocess._load_meta")
    describe("OCR with diacritics", ocr_search.WITH_MARKS_PATH, "ocr_search._load (annotation, /ocr-search)")
    describe("OCR without diacritics", ocr_search.NO_MARKS_PATH, "ocr_search._load")
    describe("frame -> ASR text", asr_text.ASR_TEXT_PATH, "asr_text._load (annotation: ASR substring and regex)")
    describe("ASR windows", os.path.join(release, "windows.jsonl"), "text_signal._load_bm25, text_lookup._windows_by_video (ASR bm25)")
    for name in ("vocabulary.json", "posting_offsets.npy", "posting_doc_ids.npy", "posting_term_frequencies.npy", "document_lengths.npy") :
        describe("BM25", os.path.join(release, "bm25", name), "text_signal._load_bm25")
    for name in E5_FILES :
        describe("dense E5 release", os.path.join(release, name), "NOTHING in this checkout (grep finds no reader)")


def section_loading() -> dict :
    print("== 2. loading in this process")
    report = text_measures.load_text_artifacts()
    for source, info in report.items() :
        print(f"  {source}: ready {info['ready']}, entries with text {info['entries']:,}, error {info['error']}, path {info['path']}")
    text_signal._load_bm25()
    print(f"  bm25: {text_signal.status()}")
    return report


def section_coverage() -> dict[str, dict[str, int]] :
    print("== 3. keyframes with text, per video prefix (same get_text functions as annotation)")
    preprocess._load_meta()
    counts = {p : {"videos" : 0, "keyframes" : 0, "ocr" : 0, "asr" : 0, "videos_with_asr" : 0} for p in PREFIXES}
    for video, frames in preprocess._video_frames.items() :
        row = counts.get(video[ : 1])
        if (row is None) :
            continue
        names = [f["name"] for f in frames]
        asr_frames = sum(1 for n in names if asr_text.get_text(n))
        row["videos"] += 1
        row["keyframes"] += len(names)
        row["ocr"] += sum(1 for n in names if ocr_search.get_text(n))
        row["asr"] += asr_frames
        row["videos_with_asr"] += 1 if asr_frames else 0
    print(f"  {'prefix':6} {'videos':>7} {'keyframes':>10} {'with OCR':>10} {'with ASR':>10} {'videos with ASR':>16}")
    for prefix, row in counts.items() :
        print(f"  {prefix:6} {row['videos']:>7,} {row['keyframes']:>10,} {row['ocr']:>10,} {row['asr']:>10,} {row['videos_with_asr']:>16,}")
    return counts


def section_lookup() -> None :
    print(f"== 4. ASR substring lookup of {LOOKUP_CUES} legacy_leaky cues of {LOOKUP_DATASET} in their reference video")
    seed = json.loads((SEEDS_DIR / f"{LOOKUP_DATASET}.json").read_text(encoding = "utf-8"))
    reference = {q["id"] : q["reference"]["video_id"] for q in seed["queries"]}
    picked = [r for r in cues.read_rows(LOOKUP_DATASET) if r["source"] == "asr" and r["status"] == "legacy_leaky"][ : LOOKUP_CUES]
    for row in picked :
        video, term = reference[row["query_key"]], row["term"]
        hits = text_signal._substring_hits(video, term, asr_text.get_text)
        n_text = sum(1 for n in preprocess.frames_for_video(video) if asr_text.get_text(n))
        print(f"  {row['query_key']} {video} term {term!r}: {len(hits)} matching frames of {n_text} frames with ASR text")
        if (hits) :
            text = asr_text.get_text(hits[0].frame_name)
            spans = text_signal._substring_spans(text, term, hits[0].match_type, False)
            start = max(0, (spans[0][0] if spans else 0) - 40)
            print(f"      first {hits[0].frame_name} ({hits[0].match_type}): ...{text[start : start + 140]}...")


def section_tokenizers() -> None :
    print("== 5. tokenizers for the text-length diagnostic (no model weights are loaded)")
    sample = "A man in a red shirt walks into the kitchen and opens the fridge " * 8
    for model in text_length.MODELS :
        count, limit, method = text_length.counter(model)
        print(f"  {model:8} limit {limit}, {count(sample)} tokens for a {len(sample.split())}-word sample, tokens by {method}")


def main() -> int :
    section_files()
    report = section_loading()
    counts = section_coverage()
    section_lookup()
    section_tokenizers()
    problems = []
    if (not report["asr"]["ready"] or not report["asr"]["entries"]) :
        problems.append("the ASR text index is not loaded or empty")
    if (counts["L"]["asr"] == 0) :
        problems.append("no L keyframe has ASR text")
    print("== verdict: " + ("; ".join(problems) if problems else "OCR and ASR text are loaded and L videos have text"))
    return 1 if problems else 0


if (__name__ == "__main__") :
    raise SystemExit(main())
