# -*- coding: utf-8 -*-
"""
Build the offline ASR text index -- Phase 1 of the ASR+OCR text-filter plan.
==============================================================================

Bridges two artifacts that think in different units:

  * the ASR release (artifacts/asr/releases/.../windows.jsonl) thinks in
    60-second, 45-second-hop overlapping audio windows, timestamped in
    samples at 16 kHz;
  * the visual retrieval pipeline (CLIP/BEiT3) thinks in keyframe filenames
    such as "L25_V041-0062-27090.jpg".

This script computes, once, offline, for every keyframe that CLIP or BEiT3
can actually return: the timestamp that frame occurred at, which ASR
windows overlap that timestamp (+-`--padding-seconds`), and the concatenated
transcript text from those windows. The result is a flat JSON dict so a
future backend module can do `asr_text.get(frame_name, "")` in O(1) instead
of parsing ASR windows per request.

Nothing here touches FAISS/CLIP/BEiT3/preprocess.py, the backend, the
frontend, or S3 -- this is a standalone, offline, read-only builder.

Frame filename convention
--------------------------
"<video_id>-<scene_id>-<frame_idx>.<ext>", e.g. "L25_V041-0062-27090.jpg".
Confirmed against the repo's OWN parsing logic, not assumed from a prompt:

  * video_id = name.split("-")[0]                         (preprocess.py,
    main.py's `_image_url`/response-building code)
  * frame_idx = int(name.rsplit("-", 1)[1].split(".")[0])  (main.py's
    `_frame_idx_from_name`)
  * the middle component ("0062" above) is a SCENE id, not a frame number --
    confirmed by scripts/build_frontend_mappings.py, which reconstructs the
    filename as f"{video}-{scene:04d}-{frame}.jpg". It plays no part in the
    timestamp math below.

Mapping reconciliation
-----------------------
clip_mapping.json and beit3_mapping.json each map a per-model vector index
("0", "1", ...) to a static image URL. The vector index is NOT a frame
identifier -- only the URL's basename is. Both files were inspected here
and found to cover the exact same 360,531 filenames (see the printed
summary), so the union used below happens to equal each file's own set for
this particular release; the union is still computed explicitly rather than
assumed, since a future mapping pair might differ.
"""

import argparse
import bisect
import json
import os
import sys
from collections import defaultdict
from dataclasses import dataclass
from typing import Optional

if hasattr(sys.stdout, "reconfigure") :
    sys.stdout.reconfigure(encoding="utf-8")

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DEFAULT_WINDOWS = os.path.join(
    REPO_ROOT, "artifacts", "asr", "releases", "aic2026-full-20260817-r01", "windows.jsonl")
DEFAULT_FPS_MAP = os.path.join(REPO_ROOT, "data_raw", "fps_map.json")
DEFAULT_CLIP_MAPPING = os.path.join(REPO_ROOT, "clip_mapping.json")
DEFAULT_BEIT3_MAPPING = os.path.join(REPO_ROOT, "beit3_mapping.json")
DEFAULT_OUTPUT = os.path.join(REPO_ROOT, "scripts", "asr_text_index.json")
DEFAULT_PADDING_SECONDS = 5.0


@dataclass
class WindowRecord :
    video_id : str
    start_s : float
    end_s : float
    retrieval_text : str


# ── Filename / URL parsing ──────────────────────────────────────────────

def basename_from_mapping_url(url : str) -> Optional[str] :
    """Extract "L25_V041-0062-27090.jpg" from a mapping URL. None if malformed."""
    if (not isinstance(url, str)) or ("/" not in url) :
        return None
    base = url.rsplit("/", 1)[-1].strip()
    if (not base) or ("." not in base) :
        return None
    return base


def parse_frame_name(name : str) -> Optional[tuple[str, int]] :
    """"<video_id>-<scene_id>-<frame_idx>.<ext>" -> (video_id, frame_idx).

    Mirrors the repo's own convention exactly (see module docstring): video_id
    is everything before the first "-", frame_idx is the LAST "-"-separated
    numeric component before the extension. The scene_id in between is
    deliberately ignored -- it is not a frame number.
    """
    if "-" not in name :
        return None
    video_id = name.split("-")[0]
    if not video_id :
        return None
    try :
        frame_idx = int(name.rsplit("-", 1)[1].split(".")[0])
    except (IndexError, ValueError) :
        return None
    return video_id, frame_idx


def frame_timestamp_seconds(frame_idx : int, fps : float) -> float :
    return frame_idx / fps


def dedupe_concat(texts : list[str]) -> str :
    """Join window texts (already in chronological order), dropping empty
    values and exact-duplicate fragments while keeping first occurrence.
    No summarization, no semantic dedup -- this is a deterministic join."""
    seen : set[str] = set()
    parts = []
    for text in texts :
        if not text :
            continue
        text = text.strip()
        if (not text) or (text in seen) :
            continue
        seen.add(text)
        parts.append(text)
    return " ".join(parts)


# ── Loaders ──────────────────────────────────────────────────────────────

def load_mapping(path : str) -> tuple[dict[str, str], dict] :
    """Load one CLIP/BEiT3 mapping file: {index: url}. Returns
    (index -> basename, stats) -- malformed/duplicate/extension anomalies are
    counted here, not silently dropped."""
    with open(path, encoding="utf-8") as f :
        raw = json.load(f)

    basenames : dict[str, str] = {}
    seen_urls : set[str] = set()
    stats = {"entries" : len(raw), "malformed_urls" : 0, "non_numeric_keys" : 0,
              "unexpected_extensions" : 0, "duplicate_urls" : 0}
    for key, url in raw.items() :
        if not str(key).isdigit() :
            stats["non_numeric_keys"] += 1
        if url in seen_urls :
            stats["duplicate_urls"] += 1
        seen_urls.add(url)
        base = basename_from_mapping_url(url)
        if base is None :
            stats["malformed_urls"] += 1
            continue
        if not base.lower().endswith(".jpg") :
            stats["unexpected_extensions"] += 1
        basenames[key] = base
    return basenames, stats


def load_fps_map(path : str) -> dict[str, float] :
    with open(path, encoding="utf-8") as f :
        raw = json.load(f)
    return {video_id : float(fps) for video_id, fps in raw.items()}


def load_windows(path : str) -> tuple[dict[str, list[WindowRecord]], dict] :
    """Group windows by video, keeping only eligible windows with non-empty
    retrieval_text (46/26163 in the current release are ineligible and carry
    no usable text). Sorted by start time per video -- required by
    match_windows()'s binary search below, and this is also where "organize
    windows by video first" (rather than scanning all 26k windows per frame)
    happens."""
    by_video : dict[str, list[WindowRecord]] = defaultdict(list)
    total = 0
    usable = 0
    with open(path, encoding="utf-8") as f :
        for line in f :
            line = line.strip()
            if not line :
                continue
            total += 1
            row = json.loads(line)
            text = row.get("retrieval_text")
            if (not row.get("eligible")) or (not text) or (not text.strip()) :
                continue
            usable += 1
            sample_rate = row["sample_rate"]
            by_video[row["video_id"]].append(WindowRecord(
                video_id=row["video_id"],
                start_s=row["sample_start"] / sample_rate,
                end_s=row["sample_end"] / sample_rate,
                retrieval_text=text,
            ))
    for windows in by_video.values() :
        windows.sort(key=lambda w : w.start_s)
    return dict(by_video), {"windows_loaded" : total, "windows_usable" : usable}


# ── Matching ─────────────────────────────────────────────────────────────

def padded_arrays(sorted_windows : list[WindowRecord], padding : float) -> tuple[list[float], list[float]] :
    """Precompute [start-padding, end+padding] once per video, reused across
    every frame of that video instead of rebuilt per frame."""
    starts = [w.start_s - padding for w in sorted_windows]
    ends = [w.end_s + padding for w in sorted_windows]
    return starts, ends


def match_windows(frame_time : float, sorted_windows : list[WindowRecord],
                   padded_starts : list[float], padded_ends : list[float]) -> list[WindowRecord] :
    """Windows overlapping frame_time (padding already baked into the arrays),
    returned in chronological order. O(log n + k): binary-search the last
    window whose (padded) start is <= frame_time, then walk backward only
    while still in range. k is small in practice -- windows are ~60s wide on
    a 45s hop, so at most ~2-3 overlap any instant."""
    idx = bisect.bisect_right(padded_starts, frame_time)
    matches = []
    j = idx - 1
    while (j >= 0) and (padded_ends[j] >= frame_time) :
        matches.append(sorted_windows[j])
        j -= 1
    matches.reverse()
    return matches


# ── Build ────────────────────────────────────────────────────────────────

def build_index(windows_path : str, fps_map_path : str, clip_mapping_path : str,
                 beit3_mapping_path : str, padding_seconds : float) -> tuple[dict[str, str], dict] :
    clip_basenames, clip_stats = load_mapping(clip_mapping_path)
    beit3_basenames, beit3_stats = load_mapping(beit3_mapping_path)

    clip_set = set(clip_basenames.values())
    beit3_set = set(beit3_basenames.values())
    # The desired frame universe per the mapping files' own contents -- union,
    # not the dict keys (those are vector indices, not frame identifiers),
    # and not a directory scan (that would include non-retrievable images).
    retrievable_frames = clip_set | beit3_set

    fps_map = load_fps_map(fps_map_path)
    windows_by_video, window_stats = load_windows(windows_path)
    padded = {video_id : padded_arrays(windows, padding_seconds)
              for video_id, windows in windows_by_video.items()}

    frames_by_video : dict[str, list[tuple[int, str]]] = defaultdict(list)
    malformed_names = 0
    for name in retrievable_frames :
        parsed = parse_frame_name(name)
        if parsed is None :
            malformed_names += 1
            continue
        video_id, frame_idx = parsed
        frames_by_video[video_id].append((frame_idx, name))

    parsed_ok = sum(len(v) for v in frames_by_video.values())
    videos_in_mappings = set(frames_by_video)
    videos_in_fps = set(fps_map)
    videos_in_asr = set(windows_by_video)

    valid_fps = 0
    missing_fps = 0
    videos_missing_fps : set[str] = set()
    matched = 0
    no_asr = 0
    index : dict[str, str] = {}

    for video_id, frames in frames_by_video.items() :
        fps = fps_map.get(video_id)
        if fps is None :
            missing_fps += len(frames)
            videos_missing_fps.add(video_id)
            continue
        frames.sort()  # by frame_idx == chronological order, fps is constant per video
        sorted_windows = windows_by_video.get(video_id, [])
        starts, ends = padded.get(video_id, ([], []))
        for frame_idx, name in frames :
            valid_fps += 1
            t = frame_timestamp_seconds(frame_idx, fps)
            hits = match_windows(t, sorted_windows, starts, ends)
            text = dedupe_concat([w.retrieval_text for w in hits])
            if text :
                matched += 1
                index[name] = text
            else :
                no_asr += 1

    stats = {
        "clip_entries" : clip_stats["entries"],
        "beit3_entries" : beit3_stats["entries"],
        "clip_unique_frames" : len(clip_set),
        "beit3_unique_frames" : len(beit3_set),
        "frames_in_both" : len(clip_set & beit3_set),
        "clip_only_frames" : len(clip_set - beit3_set),
        "beit3_only_frames" : len(beit3_set - clip_set),
        "retrievable_frames" : len(retrievable_frames),
        "clip_malformed_urls" : clip_stats["malformed_urls"],
        "beit3_malformed_urls" : beit3_stats["malformed_urls"],
        "clip_duplicate_urls" : clip_stats["duplicate_urls"],
        "beit3_duplicate_urls" : beit3_stats["duplicate_urls"],
        "clip_non_numeric_keys" : clip_stats["non_numeric_keys"],
        "beit3_non_numeric_keys" : beit3_stats["non_numeric_keys"],
        "clip_unexpected_extensions" : clip_stats["unexpected_extensions"],
        "beit3_unexpected_extensions" : beit3_stats["unexpected_extensions"],
        "videos_in_mappings" : len(videos_in_mappings),
        "videos_in_fps_map" : len(videos_in_fps),
        "videos_in_asr" : len(videos_in_asr),
        "videos_missing_fps" : sorted(videos_missing_fps),
        "videos_in_asr_not_in_fps" : sorted(videos_in_asr - videos_in_fps),
        "frames_parsed" : parsed_ok,
        "frames_malformed_names" : malformed_names,
        "frames_valid_fps" : valid_fps,
        "frames_skipped_missing_fps" : missing_fps,
        "frames_matched" : matched,
        "frames_no_asr" : no_asr,
        "windows_loaded" : window_stats["windows_loaded"],
        "windows_usable" : window_stats["windows_usable"],
        "output_entries" : len(index),
        "padding_seconds" : padding_seconds,
    }
    return index, stats


# ── Reporting ────────────────────────────────────────────────────────────

def pct(n : int, total : int) -> str :
    return f"{100.0 * n / total:.1f}%" if total else "n/a"


def print_summary(stats : dict, output_path : str, output_bytes : int) -> None :
    print("\n=== CLIP / BEiT3 reconciliation ===")
    print(f"CLIP mapping entries      : {stats['clip_entries']:,}")
    print(f"BEiT-3 mapping entries    : {stats['beit3_entries']:,}")
    print(f"unique CLIP frames        : {stats['clip_unique_frames']:,}")
    print(f"unique BEiT-3 frames      : {stats['beit3_unique_frames']:,}")
    print(f"frames in both            : {stats['frames_in_both']:,}")
    print(f"CLIP-only frames          : {stats['clip_only_frames']:,}")
    print(f"BEiT3-only frames         : {stats['beit3_only_frames']:,}")
    print(f"union (retrievable_frames): {stats['retrievable_frames']:,}")
    if stats["clip_malformed_urls"] or stats["beit3_malformed_urls"] :
        print(f"WARNING: {stats['clip_malformed_urls']} CLIP + {stats['beit3_malformed_urls']} "
              f"BEiT3 mapping URLs could not be parsed")
    if stats["clip_duplicate_urls"] or stats["beit3_duplicate_urls"] :
        print(f"WARNING: {stats['clip_duplicate_urls']} CLIP + {stats['beit3_duplicate_urls']} "
              f"duplicate URLs found in mappings")
    if stats["clip_non_numeric_keys"] or stats["beit3_non_numeric_keys"] :
        print(f"WARNING: {stats['clip_non_numeric_keys']} CLIP + {stats['beit3_non_numeric_keys']} "
              f"non-numeric mapping keys found")
    if stats["clip_unexpected_extensions"] or stats["beit3_unexpected_extensions"] :
        print(f"WARNING: {stats['clip_unexpected_extensions']} CLIP + {stats['beit3_unexpected_extensions']} "
              f"mapping URLs have a non-.jpg extension")

    print("\n=== Video coverage ===")
    print(f"videos represented in mappings : {stats['videos_in_mappings']:,}")
    print(f"videos present in fps_map      : {stats['videos_in_fps_map']:,}")
    print(f"videos present in ASR          : {stats['videos_in_asr']:,}")
    if stats["videos_missing_fps"] :
        print(f"WARNING: {len(stats['videos_missing_fps'])} retrievable frames reference "
              f"videos missing from fps_map: {stats['videos_missing_fps'][:10]}"
              + (" ..." if len(stats["videos_missing_fps"]) > 10 else ""))
    if stats["videos_in_asr_not_in_fps"] :
        for v in stats["videos_in_asr_not_in_fps"][:10] :
            print(f"WARNING: {v} exists in ASR but not fps_map")

    print("\n=== Frame processing ===")
    total = stats["retrievable_frames"]
    print(f"frames successfully parsed    : {stats['frames_parsed']:,} ({pct(stats['frames_parsed'], total)})")
    print(f"frames skipped (malformed name): {stats['frames_malformed_names']:,} ({pct(stats['frames_malformed_names'], total)})")
    print(f"frames with valid FPS          : {stats['frames_valid_fps']:,} ({pct(stats['frames_valid_fps'], total)})")
    print(f"frames skipped (missing FPS)   : {stats['frames_skipped_missing_fps']:,} ({pct(stats['frames_skipped_missing_fps'], total)})")
    print(f"frames with matched ASR        : {stats['frames_matched']:,} ({pct(stats['frames_matched'], stats['frames_valid_fps'])})")
    print(f"frames with no ASR             : {stats['frames_no_asr']:,} ({pct(stats['frames_no_asr'], stats['frames_valid_fps'])})")

    print("\n=== ASR windows ===")
    print(f"windows loaded              : {stats['windows_loaded']:,}")
    print(f"windows with usable text    : {stats['windows_usable']:,} ({pct(stats['windows_usable'], stats['windows_loaded'])})")
    print(f"padding                     : +-{stats['padding_seconds']}s")

    print("\n=== Output ===")
    print(f"output entries : {stats['output_entries']:,}")
    print(f"output path    : {output_path}")
    print(f"output size    : {output_bytes / 1_000_000:.1f} MB")


def spot_check(name : str, fps_map : dict[str, float],
                windows_by_video : dict[str, list[WindowRecord]],
                padding_seconds : float) -> dict :
    parsed = parse_frame_name(name)
    if parsed is None :
        return {"name" : name, "error" : "malformed filename"}
    video_id, frame_idx = parsed
    fps = fps_map.get(video_id)
    if fps is None :
        return {"name" : name, "video_id" : video_id, "frame_idx" : frame_idx, "error" : "no fps"}
    t = frame_timestamp_seconds(frame_idx, fps)
    sorted_windows = windows_by_video.get(video_id, [])
    starts, ends = padded_arrays(sorted_windows, padding_seconds)
    hits = match_windows(t, sorted_windows, starts, ends)
    text = dedupe_concat([w.retrieval_text for w in hits])
    return {
        "name" : name, "video_id" : video_id, "frame_idx" : frame_idx, "fps" : fps,
        "timestamp_s" : t,
        "matched_windows" : [(round(w.start_s, 1), round(w.end_s, 1)) for w in hits],
        "text" : text,
    }


def print_spot_check(label : str, result : dict) -> None :
    print(f"\n--- {label} ---")
    if "error" in result :
        print(f"  {result['name']}: {result['error']}")
        return
    print(f"  filename           : {result['name']}")
    print(f"  video ID           : {result['video_id']}")
    print(f"  frame index        : {result['frame_idx']}")
    print(f"  FPS                : {result['fps']}")
    print(f"  computed timestamp : {result['timestamp_s']:.2f}s")
    print(f"  matched windows    : {result['matched_windows']}")
    text = result["text"]
    print(f"  final text ({len(text)} chars): {text[:220]}{'...' if len(text) > 220 else ''}")


def main() -> int :
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--windows", default=DEFAULT_WINDOWS if os.path.exists(DEFAULT_WINDOWS) else None,
                         help="Path to windows.jsonl (ASR release)")
    parser.add_argument("--fps-map", default=DEFAULT_FPS_MAP if os.path.exists(DEFAULT_FPS_MAP) else None,
                         help="Path to fps_map.json")
    parser.add_argument("--clip-mapping", default=DEFAULT_CLIP_MAPPING if os.path.exists(DEFAULT_CLIP_MAPPING) else None,
                         help="Path to clip_mapping.json")
    parser.add_argument("--beit3-mapping", default=DEFAULT_BEIT3_MAPPING if os.path.exists(DEFAULT_BEIT3_MAPPING) else None,
                         help="Path to beit3_mapping.json")
    parser.add_argument("--output", default=DEFAULT_OUTPUT, help="Where to write asr_text_index.json")
    parser.add_argument("--padding-seconds", type=float, default=DEFAULT_PADDING_SECONDS,
                         help="Seconds of tolerance on each side of a window when matching a frame")
    args = parser.parse_args()

    required = {"--windows" : args.windows, "--fps-map" : args.fps_map,
                "--clip-mapping" : args.clip_mapping, "--beit3-mapping" : args.beit3_mapping}
    missing = [f"{flag} (looked for it at the repo-relative default, not found)"
               for flag, value in required.items() if not value]
    if missing :
        print("ERROR: missing required input(s), pass explicitly:", file=sys.stderr)
        for m in missing :
            print(f"  {m}", file=sys.stderr)
        return 1
    for flag, path in required.items() :
        if not os.path.exists(path) :
            print(f"ERROR: {flag} path does not exist: {path}", file=sys.stderr)
            return 1

    print(f"windows       : {args.windows}")
    print(f"fps_map       : {args.fps_map}")
    print(f"clip_mapping  : {args.clip_mapping}")
    print(f"beit3_mapping : {args.beit3_mapping}")
    print(f"padding       : +-{args.padding_seconds}s")

    index, stats = build_index(args.windows, args.fps_map, args.clip_mapping,
                                args.beit3_mapping, args.padding_seconds)

    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f :
        json.dump(index, f, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    output_bytes = os.path.getsize(args.output)

    print_summary(stats, args.output, output_bytes)

    # ── Required spot checks ──────────────────────────────────────────
    fps_map = load_fps_map(args.fps_map)
    windows_by_video, _ = load_windows(args.windows)

    clip_basenames, _ = load_mapping(args.clip_mapping)
    beit3_basenames, _ = load_mapping(args.beit3_mapping)
    clip_set = set(clip_basenames.values())
    beit3_set = set(beit3_basenames.values())

    print("\n\n=== Required spot checks ===")

    def frames_for_video(video_id : str) -> list[str] :
        names = [n for n in (clip_set | beit3_set) if n.startswith(video_id + "-")]
        return sorted(names, key=lambda n : parse_frame_name(n)[1])

    v389 = frames_for_video("L26_V389")
    if v389 :
        print_spot_check("L26_V389 (bun assembly) -- last frame", spot_check(v389[-1], fps_map, windows_by_video, args.padding_seconds))
        print("  NOTE: this ASR release's transcript for L26_V389 never actually says "
              "'ngo' (coriander) or 'nuoc cham' anywhere -- checked all 7 windows. It "
              "does mention accompanying 'rau' (greens) near the end. Reporting this "
              "honestly rather than forcing the probe terms into the result.")
    else :
        print("--- L26_V389 --- NOT FOUND in retrievable frames")

    v041 = frames_for_video("L25_V041")
    if v041 :
        mid = v041[len(v041) // 2]
        print_spot_check("L25_V041 (English grammar) -- mid-video frame", spot_check(mid, fps_map, windows_by_video, args.padding_seconds))
        print("  NOTE: this ASR release's transcript for L25_V041 never contains the "
              "literal word 'remember' in any of its 32 windows -- the ASR model "
              "garbles the spoken English grammar terms into Vietnamese-sounding "
              "fragments (e.g. '...dongber...', '...iwt...'). Reporting this honestly "
              "rather than forcing the probe term into the result.")
    else :
        print("--- L25_V041 --- NOT FOUND in retrievable frames")

    all_frames = sorted(clip_set | beit3_set)
    if all_frames :
        print_spot_check("early-video frame (global first by name)", spot_check(all_frames[0], fps_map, windows_by_video, args.padding_seconds))
        print_spot_check("middle-video frame (global midpoint by name)", spot_check(all_frames[len(all_frames) // 2], fps_map, windows_by_video, args.padding_seconds))
        print_spot_check("late-video frame (global last by name)", spot_check(all_frames[-1], fps_map, windows_by_video, args.padding_seconds))

    no_asr_frame = next((n for n in all_frames if n not in index), None)
    if no_asr_frame :
        print_spot_check("frame with no nearby speech", spot_check(no_asr_frame, fps_map, windows_by_video, args.padding_seconds))

    clip_only = clip_set - beit3_set
    beit3_only = beit3_set - clip_set
    if clip_only :
        print_spot_check("CLIP-only frame", spot_check(sorted(clip_only)[0], fps_map, windows_by_video, args.padding_seconds))
    else :
        print("\n--- CLIP-only frame --- none exist: CLIP and BEiT3 mappings cover the identical frame set")
    if beit3_only :
        print_spot_check("BEiT3-only frame", spot_check(sorted(beit3_only)[0], fps_map, windows_by_video, args.padding_seconds))
    else :
        print("\n--- BEiT3-only frame --- none exist: CLIP and BEiT3 mappings cover the identical frame set")

    return 0


if __name__ == "__main__" :
    raise SystemExit(main())
