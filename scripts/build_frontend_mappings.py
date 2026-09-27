# -*- coding: utf-8 -*-

"""
Build the frontend's bundled mapping files from the index the API actually serves.

The cloud is the source of truth. `s3://aic2026-artifacts/indexes/` is what the
API host syncs from, so it is what this script reads — never a copy that happens
to be sitting in `backend/app/indexes/`.

That distinction is not academic. A hand-maintained copy drifted badly:

  - `keyframe_index.json` was generated from a local `keyframe_metadata.json`
    covering K01-K19 + L25-L30, while the deployed index covers L21-L30. Every
    preview for L21-L24 fell back to "Chưa tải ảnh" even though the image was
    sitting on the CDN.
  - `fps_map.json` carried 29 for 30 videos whose real rate is 29.97, and 26 for
    one whose real rate is 26.44. At frame 26253 that is a 29-second seek error,
    and submitting from the same position lands 877 frames off — far outside any
    R@k window.

Both files are derivable from one cloud artifact, so both are generated here and
neither is edited by hand again.

Outputs
-------
frontend/src/mapping/keyframe_index.json
    {"<video>": [[frame_idx, scene_id], ...]} sorted by frame_idx, so the client
    can binary-search one video. Carries the scene id because the image filename
    is "<video>-<scene_id:04d>-<frame_idx>.jpg" and the scene id cannot be
    guessed from a video and a frame alone.

frontend/src/mapping/fps_map.json
    {"<video>": fps}. Merged, not replaced: the cloud's value wins wherever the
    cloud knows the video, and existing entries survive for videos it does not.
    The video store holds more videos than the search index does, and goto-frame
    must keep working for them.

Usage
-----
    python scripts/build_frontend_mappings.py            # pull from S3
    python scripts/build_frontend_mappings.py --strict   # ...and fail on drift
    AIC_META=path/to/keyframe_metadata.json python scripts/build_frontend_mappings.py

Environment
-----------
    AIC_META          Read this local file instead of downloading from S3.
    AIC_S3_INDEXES    Default s3://aic2026-artifacts/indexes
    AIC_AWS_PROFILE   Default "aic"
    AIC_API_URL       Default https://aic-api.umaga.fun. Set empty to skip the
                      drift check (offline).
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from collections import defaultdict

# The Vietnamese progress lines below are unprintable on a default Windows
# console (cp1252), and the failure lands before any work is done.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

S3_PREFIX = os.environ.get("AIC_S3_INDEXES", "s3://aic2026-artifacts/indexes")
AWS_PROFILE = os.environ.get("AIC_AWS_PROFILE", "aic")
API_URL = os.environ.get("AIC_API_URL", "https://aic-api.umaga.fun")
LOCAL_META = os.environ.get("AIC_META")

MAPPING_DIR = os.path.join("frontend", "src", "mapping")
INDEX_OUT = os.path.join(MAPPING_DIR, "keyframe_index.json")
FPS_OUT = os.path.join(MAPPING_DIR, "fps_map.json")


def fetch_from_s3(destination: str) -> str:
    """Download the metadata the API host syncs from. Returns the local path."""
    key = f"{S3_PREFIX}/keyframe_metadata.json"
    print(f"tải {key} …")
    subprocess.run(
        ["aws", "s3", "cp", key, destination, "--profile", AWS_PROFILE],
        check=True,
    )
    return destination


def deployed_metadata_bytes() -> "int | None":
    """What the running API reports it has loaded, or None if unreachable."""
    if not API_URL:
        return None
    # Cloudflare sits in front of the API and 403s urllib's default agent, which
    # would silently disable this whole check.
    request = urllib.request.Request(
        f"{API_URL}/status",
        headers={"User-Agent": "aic-build-frontend-mappings/1.0", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            status = json.load(response)
    except (urllib.error.URLError, OSError, ValueError) as err:
        print(f"[cảnh báo] không hỏi được {API_URL}/status: {err}")
        return None
    entry = status.get("index_files", {}).get("keyframe_metadata.json", {})
    return entry.get("loaded", {}).get("bytes")


def check_drift(source: str, strict: bool) -> bool:
    """
    Compare the source against what the API is actually serving.

    This is the only check that can catch the failure that prompted this script:
    the wrong input file still produces a valid-looking index, every test stays
    green, and the only symptom is images that never load.
    """
    served = deployed_metadata_bytes()
    if served is None:
        print("[cảnh báo] bỏ qua đối chiếu với API — không lấy được /status")
        return True

    actual = os.path.getsize(source)
    if actual == served:
        print(f"khớp với API đang chạy: {actual} byte")
        return True

    print(
        f"[LỆCH] nguồn {actual} byte, nhưng API đang nạp {served} byte.\n"
        f"        Chỉ mục sinh ra sẽ không khớp thứ backend trả về.",
        file=sys.stderr,
    )
    if strict:
        print("        --strict → dừng.", file=sys.stderr)
        return False
    print("        Chạy tiếp vì không có --strict.", file=sys.stderr)
    return True


def load_existing(path: str) -> dict:
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def build(meta: list) -> "tuple[dict, dict]":
    """Return (keyframe index, fps map) from the metadata rows."""
    by_video = defaultdict(set)
    fps = {}

    for row in meta:
        video = row["video"]
        frame = int(row["frame_idx"])
        scene = int(row["scene_id"])
        # The whole index is worthless if the name does not rebuild from these
        # three fields, because that is exactly what the client will do.
        rebuilt = f"{video}-{scene:04d}-{frame}.jpg"
        if rebuilt != row["name"]:
            raise SystemExit(
                f"[LỖI] tên không tái tạo được: {row['name']} != {rebuilt}"
            )
        by_video[video].add((frame, scene))
        fps[video] = row["fps"]

    index = {
        video: [list(pair) for pair in sorted(pairs)]
        for video, pairs in sorted(by_video.items())
    }
    return index, fps


def report_fps_changes(old: dict, new: dict) -> None:
    """Say exactly what moved, so a silent correction is impossible."""
    changed = [
        (v, old[v], new[v])
        for v in sorted(set(old) & set(new))
        if abs(float(old[v]) - float(new[v])) > 1e-9
    ]
    added = sorted(set(new) - set(old))
    kept = sorted(set(old) - set(new))

    print(f"fps: {len(changed)} sửa · {len(added)} thêm · {len(kept)} giữ lại (cloud không biết)")
    for video, was, now in changed:
        print(f"  {video}: {was} → {now}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--strict",
        action="store_true",
        help="dừng nếu nguồn lệch với thứ API đang nạp",
    )
    args = parser.parse_args()

    if not os.path.isdir(MAPPING_DIR):
        print(f"[LỖI] chạy từ gốc repo — không thấy {MAPPING_DIR}", file=sys.stderr)
        return 1

    with tempfile.TemporaryDirectory() as tmp:
        if LOCAL_META:
            source = LOCAL_META
            print(f"dùng file local (AIC_META): {source}")
            if not os.path.exists(source):
                print(f"[LỖI] không thấy {source}", file=sys.stderr)
                return 1
        else:
            source = fetch_from_s3(os.path.join(tmp, "keyframe_metadata.json"))

        if not check_drift(source, args.strict):
            return 1

        print("đang đọc metadata …")
        with open(source, "r", encoding="utf-8") as f:
            meta = json.load(f)

        index, cloud_fps = build(meta)

    # Merge rather than replace: the video store carries more videos than the
    # search index does, and goto-frame must keep working for them.
    existing_fps = load_existing(FPS_OUT)
    merged_fps = dict(existing_fps)
    merged_fps.update(cloud_fps)

    report_fps_changes(existing_fps, cloud_fps)

    with open(INDEX_OUT, "w", encoding="utf-8") as f:
        json.dump(index, f, separators=(",", ":"))
    with open(FPS_OUT, "w", encoding="utf-8") as f:
        json.dump({k: merged_fps[k] for k in sorted(merged_fps)}, f, indent=2)

    frames = sum(len(pairs) for pairs in index.values())
    size = os.path.getsize(INDEX_OUT) / 1_000_000
    print(
        f"{len(index)} video · {frames} keyframe · {size:.1f} MB -> {INDEX_OUT}\n"
        f"{len(merged_fps)} video fps -> {FPS_OUT}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
