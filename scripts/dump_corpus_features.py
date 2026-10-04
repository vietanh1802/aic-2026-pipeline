# scripts/dump_corpus_features.py
"""Dump per-video and per-shot corpus features from the keyframe metadata, for the ablation analysis.

Standard library only, and it does NOT import app.preprocess, so it loads no models and no FAISS index:
it reads keyframe_metadata.json (a list with one record per keyframe) with the json module. On the EC2
host the full file (991,469 records) parses in a few GB of RAM.

Written to <out>/:
    videos.csv         video, prefix, n_keyframes, n_shots, fps, fps_varies, fps_map, first_frame, last_frame,
                       duration_s, last_timestamp_s
    shots.csv          video, shot, n_keyframes, first_frame, last_frame, span_s, duration_est_s
    frames_ref.csv     video, name, shot, frame_idx   (only the reference videos of the four seeds)
    index_files.csv    name, bytes   (every file in the index folder: vectors per index come from the log)
    corpus_totals.json the totals printed at the end

What is and is not known from the metadata
  shot        record["scene_id"] when present, else the middle part of the file name video-shot-frame. The
              script counts how many records disagree between the two and prints it; do not assume.
  duration_s  last keyframe frame / fps. The metadata has no container duration, so this is a LOWER bound of
              the true length (frames after the last keyframe are not counted). last_timestamp_s is the
              last keyframe's timestamp_ms / 1000, which differs on variable frame rate videos.
  duration_est_s  an estimate of a shot's length: first keyframe of the next shot minus this shot's first
              keyframe, over fps (the last shot of a video uses its own last keyframe, a lower bound). The
              true shot boundaries came from the shot detector and are not stored here.

    python scripts/dump_corpus_features.py --index-dir /opt/aic/indexes --out /opt/aic/data/ablation_out/features
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import statistics
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SEEDS_DIR = REPO_ROOT / "backend" / "app" / "evaluation" / "seeds"
SEED_FILES = ("round1-v3.json", "round2-v2.json", "round3-v2.json", "final-v1.json")

if hasattr(sys.stdout, "reconfigure") :
    sys.stdout.reconfigure(encoding = "utf-8")


def name_parts(name : str) -> tuple[str, int, int] | None :
    """(video, shot, frame_idx) from a keyframe file name, reading from the right: the video id of the
    N and S batches contains a hyphen (N001-V001-0012-345.jpg)."""
    parts = name.rsplit(".", 1)[0].rsplit("-", 2)
    if (len(parts) != 3 or not parts[1].isdigit() or not parts[2].isdigit()) :
        return None
    return parts[0], int(parts[1]), int(parts[2])


def reference_videos(seeds_dir : Path) -> dict[str, str] :
    """{video: first dataset that uses it as a reference} over the four seeds."""
    found : dict[str, str] = {}
    for file in SEED_FILES :
        seed = json.loads((seeds_dir / file).read_text(encoding = "utf-8"))
        for query in seed["queries"] :
            found.setdefault(query["reference"]["video_id"], file.removesuffix(".json"))
    return found


def build(records : list[dict], fps_map : dict[str, float], references : dict[str, str]) -> tuple[list[dict], list[dict], list[dict], dict] :
    """Per-video rows, per-shot rows, reference frame rows and the disagreement counts."""
    by_video : dict[str, list[dict]] = {}
    disagree = {"shot_vs_name" : 0, "frame_vs_name" : 0, "video_vs_name" : 0, "no_scene_id" : 0, "unparsable_name" : 0}
    for record in records :
        video = record["video"]
        parsed = name_parts(record["name"])
        if (parsed is None) :
            disagree["unparsable_name"] += 1
        elif (parsed[0] != video) :
            disagree["video_vs_name"] += 1
        shot = record.get("scene_id")
        if (shot is None) :
            disagree["no_scene_id"] += 1
            shot = parsed[1] if parsed else -1
        elif (parsed is not None and parsed[1] != shot) :
            disagree["shot_vs_name"] += 1
        if (parsed is not None and parsed[2] != record["frame_idx"]) :
            disagree["frame_vs_name"] += 1
        by_video.setdefault(video, []).append({
            "name" : record["name"], "shot" : int(shot), "frame_idx" : int(record["frame_idx"]),
            "fps" : float(record.get("fps") or 0.0), "ts_ms" : record.get("timestamp_ms"),
        })

    videos, shots, refs = [], [], []
    for video in sorted(by_video) :
        frames = sorted(by_video[video], key = lambda f : f["frame_idx"])
        fps_values = {f["fps"] for f in frames}
        fps = frames[0]["fps"] or fps_map.get(video) or 25.0
        last = frames[-1]
        by_shot : dict[int, list[dict]] = {}
        for f in frames :
            by_shot.setdefault(f["shot"], []).append(f)
        order = sorted(by_shot, key = lambda s : by_shot[s][0]["frame_idx"])
        for index, shot in enumerate(order) :
            members = by_shot[shot]
            first_frame, last_frame = members[0]["frame_idx"], members[-1]["frame_idx"]
            end = by_shot[order[index + 1]][0]["frame_idx"] if index + 1 < len(order) else last_frame
            shots.append({
                "video" : video, "shot" : shot, "n_keyframes" : len(members), "first_frame" : first_frame,
                "last_frame" : last_frame, "span_s" : round((last_frame - first_frame) / fps, 3),
                "duration_est_s" : round((end - first_frame) / fps, 3),
            })
        videos.append({
            "video" : video, "prefix" : video[ : 1], "n_keyframes" : len(frames), "n_shots" : len(by_shot),
            "fps" : fps, "fps_varies" : int(len(fps_values) > 1), "fps_map" : fps_map.get(video, ""),
            "first_frame" : frames[0]["frame_idx"], "last_frame" : last["frame_idx"],
            "duration_s" : round(last["frame_idx"] / fps, 2),
            "last_timestamp_s" : round(last["ts_ms"] / 1000.0, 2) if last["ts_ms"] is not None else "",
        })
        if (video in references) :
            refs.extend({"video" : video, "name" : f["name"], "shot" : f["shot"], "frame_idx" : f["frame_idx"]} for f in frames)
    return videos, shots, refs, disagree


def totals(videos : list[dict], shots : list[dict]) -> dict :
    """Corpus totals overall and per prefix (hours from the last keyframe, a lower bound)."""
    def block(vs : list[dict], ss : list[dict]) -> dict :
        per_shot = [s["n_keyframes"] for s in ss]
        return {
            "videos"      : len(vs),
            "hours"       : round(sum(v["duration_s"] for v in vs) / 3600.0, 2),
            "keyframes"   : sum(v["n_keyframes"] for v in vs),
            "shots"       : len(ss),
            "keyframes_per_shot_mean"   : round(statistics.mean(per_shot), 3) if per_shot else None,
            "keyframes_per_shot_median" : statistics.median(per_shot) if per_shot else None,
        }
    result = {"all" : block(videos, shots)}
    for prefix in sorted({v["prefix"] for v in videos}) :
        members = {v["video"] for v in videos if v["prefix"] == prefix}
        result[prefix] = block([v for v in videos if v["prefix"] == prefix], [s for s in shots if s["video"] in members])
    return result


def write_csv(path : Path, rows : list[dict], fields : list[str]) -> None :
    with open(path, "w", encoding = "utf-8", newline = "") as handle :
        writer = csv.DictWriter(handle, fieldnames = fields, lineterminator = "\n")
        writer.writeheader()
        writer.writerows(rows)


def main() -> int :
    parser = argparse.ArgumentParser(description = __doc__.split("\n")[0])
    parser.add_argument("--index-dir", default = os.environ.get("AIC_INDEX_DIR"), help = "folder with keyframe_metadata.json (default: AIC_INDEX_DIR)")
    parser.add_argument("--metadata", default = None, help = "path of keyframe_metadata.json when it is not in --index-dir")
    parser.add_argument("--fps-map", default = None, help = "fps_map.json (default: <index-dir>/fps_map.json when present)")
    parser.add_argument("--seeds-dir", default = str(SEEDS_DIR))
    parser.add_argument("--out", required = True, help = "folder to write")
    args = parser.parse_args()

    metadata_path = Path(args.metadata) if args.metadata else Path(args.index_dir or ".") / "keyframe_metadata.json"
    if (not metadata_path.exists()) :
        print(f"keyframe_metadata.json not found at {metadata_path}; pass --index-dir or --metadata")
        return 2
    fps_path = Path(args.fps_map) if args.fps_map else (Path(args.index_dir) / "fps_map.json" if args.index_dir else None)
    fps_map = json.loads(fps_path.read_text(encoding = "utf-8")) if (fps_path and fps_path.exists()) else {}
    out = Path(args.out)
    out.mkdir(parents = True, exist_ok = True)

    print(f"reading {metadata_path}", flush = True)
    records = json.loads(metadata_path.read_text(encoding = "utf-8"))
    references = reference_videos(Path(args.seeds_dir))
    videos, shots, refs, disagree = build(records, fps_map, references)
    del records

    write_csv(out / "videos.csv", videos, ["video", "prefix", "n_keyframes", "n_shots", "fps", "fps_varies", "fps_map", "first_frame", "last_frame", "duration_s", "last_timestamp_s"])
    write_csv(out / "shots.csv", shots, ["video", "shot", "n_keyframes", "first_frame", "last_frame", "span_s", "duration_est_s"])
    write_csv(out / "frames_ref.csv", refs, ["video", "name", "shot", "frame_idx"])
    index_dir = Path(args.index_dir) if args.index_dir else metadata_path.parent
    files = [{"name" : p.name, "bytes" : p.stat().st_size} for p in sorted(index_dir.iterdir()) if p.is_file()]
    write_csv(out / "index_files.csv", files, ["name", "bytes"])

    summary = {"totals" : totals(videos, shots), "metadata_file" : str(metadata_path), "disagreements" : disagree,
               "reference_videos" : len(references), "reference_videos_found" : len({r["video"] for r in refs}),
               "fps_map_videos" : len(fps_map), "fps_map_mismatch" : sum(1 for v in videos if v["fps_map"] != "" and abs(float(v["fps_map"]) - v["fps"]) > 1e-6),
               "videos_with_varying_fps" : sum(v["fps_varies"] for v in videos)}
    (out / "corpus_totals.json").write_text(json.dumps(summary, indent = 1), encoding = "utf-8")

    print("\nprefix  videos   hours  keyframes    shots  kf/shot mean  median")
    for key, b in summary["totals"].items() :
        print(f"{key:>6} {b['videos']:7d} {b['hours']:7.1f} {b['keyframes']:10d} {b['shots']:8d} {b['keyframes_per_shot_mean']:13.2f} {b['keyframes_per_shot_median']:7}")
    print("hours = last keyframe frame / fps, a lower bound of the true duration")
    print(f"disagreements between scene_id, file name and frame_idx: {disagree}")
    print(f"reference videos of the seeds found in the metadata: {summary['reference_videos_found']} of {summary['reference_videos']}")
    print(f"wrote {out}")
    return 0


if (__name__ == "__main__") :
    raise SystemExit(main())
