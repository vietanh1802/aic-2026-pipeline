# -*- coding: utf-8 -*-
"""Spread frames around an anchor.

The team pins one or two videos by hand and then wants the remaining rows to
cover the time axis inside them. R@k is a max over the first k rows, so the
candidates nearest the anchor have to occupy the highest ranks — hence the
alternation rather than a sweep in one direction. Running +1, +2, +3… first
would push -1×step down to rank 51 despite it being as good a guess as +1×step.
"""
from __future__ import annotations


def spread(anchor: int, step: int, count: int) -> list[int]:
    """`count` frame numbers around `anchor`, nearest first, alternating sides."""
    if count <= 0 or step <= 0:
        return []

    frames: list[int] = []
    seen: set[int] = {anchor}
    k = 1
    # Bounded so an anchor near frame 0 cannot spin forever once the low side is
    # exhausted; count is at most a few hundred, so this is never approached.
    while len(frames) < count and k <= count * 4 + 10:
        for sign in (1, -1):
            if len(frames) >= count:
                break
            frame = anchor + sign * k * step
            if frame < 0 or frame in seen:
                continue
            seen.add(frame)
            frames.append(frame)
        k += 1
    return frames
