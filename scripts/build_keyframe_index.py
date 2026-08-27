# -*- coding: utf-8 -*-

"""
Build the client-side keyframe index.

frontend/src/mapping/keyframes.json held names shaped "<video>-<frame_idx>",
which is not enough to address an image: the real files are
"<video>-<scene_id:04d>-<frame_idx>.jpg". Anything that wants to show a still
for an arbitrary frame therefore needs the scene id too.

Output shape, chosen so the client can binary-search one video without
scanning the rest:

    {"K19_V001": [[4, 0], [29, 0], [36, 1], ...], ...}

Reading keyframe_metadata.json takes about a minute — it is 437 MB.

Run from the repository root:

    python scripts/build_keyframe_index.py
"""

import json
import os
import sys
from collections import defaultdict

META = os.environ.get(
    "AIC_META",
    os.path.join("backend", "app", "indexes", "keyframe_metadata.json"),
)
OUT = os.path.join("frontend", "src", "mapping", "keyframe_index.json")


def main() -> int:
    if not os.path.exists(META):
        print(f"[FAIL] không tìm thấy {META}", file=sys.stderr)
        return 1

    print(f"đang đọc {META} …")
    with open(META, "r", encoding="utf-8") as f:
        meta = json.load(f)

    by_video = defaultdict(set)
    for row in meta:
        video = row["video"]
        frame = int(row["frame_idx"])
        scene = int(row["scene_id"])
        # The whole index is worthless if the name does not rebuild from these
        # three fields, because that is exactly what the client will do.
        rebuilt = f"{video}-{scene:04d}-{frame}.jpg"
        if rebuilt != row["name"]:
            print(
                f"[FAIL] tên không tái tạo được: {row['name']} != {rebuilt}",
                file=sys.stderr,
            )
            return 1
        by_video[video].add((frame, scene))

    index = {
        video: [list(pair) for pair in sorted(pairs)]
        for video, pairs in sorted(by_video.items())
    }

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(index, f, separators=(",", ":"))

    total = sum(len(pairs) for pairs in index.values())
    size = os.path.getsize(OUT) / 1_000_000
    print(f"{len(index)} video · {total} keyframe · {size:.1f} MB -> {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
