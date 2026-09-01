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
