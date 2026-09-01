# -*- coding: utf-8 -*-
"""Rải frame quanh các mốc người dùng đã ghim.

Nhóm ghim vài khung chắc chắn đúng rồi muốn những dòng còn lại phủ trục thời
gian quanh chúng. R@k lấy giá trị lớn nhất trong k dòng đầu, nên ứng viên gần
mốc nhất phải chiếm hạng cao nhất — vì thế phải xen kẽ hai bên chứ không quét
một chiều. Chạy +1, +2, +3… trước sẽ đẩy −1×bước xuống tận hạng 51 dù nó là
phỏng đoán ngang ngửa +1×bước.
"""
from __future__ import annotations

from typing import Iterator

# Ba chiều rải. "up"/"down" có mặt vì đôi khi người dùng BIẾT hành động chỉ có
# thể nằm về một phía — mốc đang ở ngay đầu cảnh chẳng hạn — và rải sang phía
# kia là ném đi một nửa số dòng.
BOTH = "both"
UP = "up"
DOWN = "down"
DIRECTIONS = (BOTH, UP, DOWN)

_SIGNS = {BOTH: (1, -1), UP: (1,), DOWN: (-1,)}


def spread(anchor: int, step: int, count: int) -> list[int]:
    """`count` số frame quanh `anchor`, gần trước, xen kẽ hai bên.

    Giữ lại cho mã cũ và cho các bài test đang gọi thẳng. Bản nhiều mốc là
    `plan` bên dưới; hàm này chính là plan với đúng một mốc.
    """
    if count <= 0 or step <= 0:
        return []
    frames: list[int] = []
    seen = {anchor}
    for _, delta in plan(1, [step], [BOTH], count * 4 + 10):
        frame = anchor + delta
        if frame < 0 or frame in seen:
            continue
        seen.add(frame)
        frames.append(frame)
        if len(frames) >= count:
            break
    return frames


def _at(values: list, index: int):
    """Phần tử thứ `index`, thiếu thì lấy phần tử cuối.

    Giao diện có thể gửi danh sách ngắn hơn số mốc — thêm một dòng ghim tay
    ngay trước khi bấm chẳng hạn. Rơi về phần tử cuối vẫn rải được, còn báo lỗi
    thì chặn mất một thao tác hợp lệ.
    """
    return values[index] if index < len(values) else values[-1]


def plan(
    anchor_count: int,
    steps: list[int],
    directions: list[str],
    limit: int = 4000,
) -> Iterator[tuple[int, int]]:
    """Sinh ra (chỉ số mốc, độ dời) theo đúng thứ tự sẽ chèn vào giỏ.

    Vòng ngoài là bội số k, rồi tới dấu, rồi mới tới từng mốc. Với ba mốc cùng
    để "hai phía" thì trật tự là::

        hạng 4  = mốc 1 + bước      hạng 7  = mốc 1 − bước
        hạng 5  = mốc 2 + bước      hạng 8  = mốc 2 − bước
        hạng 6  = mốc 3 + bước      hạng 9  = mốc 3 − bước
        hạng 10 = mốc 1 + 2×bước    …

    Thứ tự đó không tuỳ tiện. Ba mốc do người dùng ghim là ba phỏng đoán NGANG
    NHAU về việc hành động nằm ở đâu; rải hết mốc 1 rồi mới tới mốc 2 sẽ dồn
    toàn bộ hạng cao cho một phỏng đoán và đẩy hai cái kia xuống đáy. Vòng
    tròn qua từng mốc giữ cho ba nhánh cùng tiến.

    Bước VÀ chiều đều riêng cho từng mốc. Mốc nằm giữa một cảnh dài thì rải hai
    phía; mốc nằm ngay đầu cảnh thì rải xuống là ném đi một nửa số dòng. Ép cả
    ba dùng chung một chiều là bắt hai mốc chịu thiệt vì mốc thứ ba.

    Mốc không nhận dấu này thì bị BỎ QUA ở lượt đó, không đẩy lịch: mốc 2 chỉ
    cộng lên sẽ vắng mặt ở mọi lượt dấu trừ, chứ không lấn chỗ của mốc 3.

    `limit` chặn số lượt sinh ra: hàm gọi lọc bớt trùng lặp nên phải sinh dư,
    còn cái chặn này để một mốc sát frame 0 không quay vô hạn khi phía dưới đã
    cạn.
    """
    if anchor_count <= 0 or not steps or not directions:
        return
    signs_of = [
        _SIGNS.get(_at(directions, i), _SIGNS[BOTH]) for i in range(anchor_count)
    ]
    steps_of = [_at(steps, i) for i in range(anchor_count)]

    # Mốc chỉ dùng được khi vừa có dấu để nhận vừa có bước dương. Phải kiểm
    # TRƯỚC vòng lặp: nếu không mốc nào dùng được thì thân vòng lặp bỏ qua hết,
    # `produced` đứng im ở 0, điều kiện `produced < limit` mãi mãi đúng và k cứ
    # tăng vô tận — request treo cứng chứ không báo lỗi.
    usable = [
        i for i in range(anchor_count) if signs_of[i] and steps_of[i] > 0
    ]
    if not usable:
        return

    produced = 0
    k = 1
    while produced < limit:
        for sign in (1, -1):
            for index in usable:
                if sign not in signs_of[index]:
                    continue
                yield index, sign * k * steps_of[index]
                produced += 1
                if produced >= limit:
                    return
        k += 1


# ─── TRAKE: đổi MỘT mốc mỗi dòng ────────────────────────────────────────────
#
# Cách rải ở trên dời CẢ BỘ mốc đi cùng một lượng, giữ nguyên khoảng cách giữa
# chúng. Đúng khi bạn tin cả bộ chỉ lệch pha, sai khi bạn tin hầu hết đã đúng
# và chỉ một mốc còn ngờ.
#
# TRAKE chấm theo TỪNG MỐC — sai một mốc mất 1/N, không phải mất trắng. Nên khi
# dòng hạng 1 đã tốt, cách sinh 99 dòng còn lại đáng giá nhất là giữ nguyên
# N−1 mốc và chỉ đổi một. Mỗi dòng dưới vì thế vẫn thừa hưởng gần hết cái đúng
# của hạng 1, thay vì là một phỏng đoán mới hoàn toàn.


def even_positions(lo: int, hi: int, n: int) -> list[int]:
    """`n` vị trí chia đều từ lo tới hi, hai đầu nằm đúng hai mút."""
    if n <= 0:
        return []
    lo, hi = min(lo, hi), max(lo, hi)
    if n == 1 or hi == lo:
        return [lo]
    return [round(lo + index * (hi - lo) / (n - 1)) for index in range(n)]


def event_variants(
    anchor: int, lo: int, hi: int, mode: str, want: int
) -> list[int]:
    """Các giá trị thay thế cho MỘT mốc: phủ đều khoảng, gần mốc gốc trước.

    Hai tiêu chí kéo ngược nhau và đều cần thiết, nên tách làm hai bước:

    - CHỌN thì phủ đều `[lo, hi]`. Lấy `want` số gần mốc gốc nhất sẽ dồn hết
      vào một cụm hẹp và bỏ trắng hai đầu khoảng người dùng vừa khoanh.
    - XẾP thì gần mốc gốc trước. R@k chỉ nhìn k dòng đầu, nên phỏng đoán tốt
      nhất phải lên trên, dù bộ đã chọn trải khắp khoảng.

    `mode` cắt bớt khoảng chứ không lọc sau: "chỉ lên" nghĩa là khoảng thật sự
    thu về `[anchor, hi]`, nên `want` vị trí vẫn phủ đều nửa đó thay vì chỉ còn
    một nửa số dòng.
    """
    if want <= 0:
        return []
    lo, hi = min(lo, hi), max(lo, hi)
    lo = max(0, lo)
    signs = _SIGNS.get(mode, _SIGNS[BOTH])
    if 1 not in signs:
        hi = min(hi, anchor)
    if -1 not in signs:
        lo = max(lo, anchor)
    if hi < lo:
        return []

    # Sinh ĐÚNG `want` vị trí, không sinh dư rồi cắt.
    #
    # Sinh want+1 rồi cắt theo khoảng cách nghe hợp lý — trừ một chỗ cho mốc
    # gốc — nhưng cái bị cắt luôn là vị trí XA NHẤT, tức một trong hai mút. Thế
    # là khoảng người dùng vừa khoanh bị hụt đúng cái đầu họ gõ vào.
    #
    # Mốc gốc trùng một vị trí thì bỏ vị trí đó và chịu mất một dòng. Không
    # đáng bù: vòng quay ở trake_plan sẽ lấy thêm từ sự kiện khác.
    count = min(want, hi - lo + 1)
    picks = {frame for frame in even_positions(lo, hi, count) if frame >= 0}
    picks.discard(anchor)
    return sorted(picks, key=lambda frame: (abs(frame - anchor), frame))[:want]


def trake_plan(
    variants: list[list[list[int]]], limit: int = 4000
) -> Iterator[tuple[int, int, int]]:
    """Sinh ra (chỉ số mốc neo, chỉ số sự kiện, frame mới).

    `variants[a][e]` là danh sách giá trị thay thế cho sự kiện `e` của mốc neo
    `a`, đã xếp sẵn theo thứ tự ưu tiên.

    Vòng ngoài là bậc k, rồi tới SỰ KIỆN, rồi mới tới mốc neo. Thứ tự đó là
    yêu cầu thẳng: với hai dòng neo, hạng 3 lấy từ dòng 1 và hạng 4 lấy từ dòng
    2 — nên mốc neo phải là vòng trong cùng, nếu không hạng 3 và 4 sẽ cùng đến
    từ dòng 1.

    Sự kiện quay vòng để mỗi sự kiện đều có mặt ở hạng cao. Rải hết biến thể
    của E1 rồi mới tới E2 sẽ dồn 25 hạng đầu cho một mốc duy nhất, trong khi ba
    mốc kia cũng đáng ngờ ngang nhau.

    Dừng khi mọi danh sách đã cạn — không quay không tải như bản đầu tôi viết.
    """
    if not variants:
        return
    event_count = max((len(per_event) for per_event in variants), default=0)
    if event_count == 0:
        return
    produced = 0
    k = 0
    while produced < limit:
        moved = False
        for event in range(event_count):
            for anchor_index, per_event in enumerate(variants):
                if event >= len(per_event) or k >= len(per_event[event]):
                    continue
                yield anchor_index, event, per_event[event][k]
                produced += 1
                moved = True
                if produced >= limit:
                    return
        if not moved:
            return
        k += 1
