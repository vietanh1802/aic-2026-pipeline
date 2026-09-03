# -*- coding: utf-8 -*-
"""Chỗ làm việc của mỗi người trên một câu, để người khác mở lại được.

Cả nhóm cùng làm một câu nhưng mỗi người gõ một truy vấn khác nhau. Khi một
người tìm ra khung hình đúng, thứ đáng chia sẻ không phải là kết quả — kết quả
tính lại được — mà là ĐƯỜNG ĐI: họ đã gõ gì, đặt tham số nào, rồi bấm vào khung
nào trong đám kết quả đó.

Cho nên bảng này lưu truy vấn chứ không lưu danh sách kết quả. Cùng một truy
vấn với cùng tham số chạy trên cùng bộ index sẽ ra đúng kết quả đó, nên chép
lại 100 dòng kết quả vào CSDL chỉ là nhân bản thứ tính lại được trong 1,5 giây
— và sẽ sai ngay khi index được cập nhật.
"""
from __future__ import annotations

import json
import sqlite3
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app import audit
from app.auth.deps import active_user
from app.db.connection import get_db, utcnow_iso
from app.routers._shared import load_task

router = APIRouter(prefix="/api", tags=["search-state"])

# Truy vấn dài nhất từng thấy là một đề bài chép nguyên vào ô search, khoảng
# 600 ký tự. 4000 để rộng cửa mà vẫn không cho một request duy nhất nhét cả
# megabyte vào CSDL.
MAX_QUERY_CHARS = 4000
MAX_PARAMS_CHARS = 2000


class SearchStateRequest(BaseModel):
    """Toàn bộ trạng thái, gửi trọn gói mỗi lần.

    Không có ghi từng phần. Người gửi luôn biết cả truy vấn lẫn khung đang
    chọn, nên gửi cả hai rẻ hơn nhiều so với việc backend phải đoán trường nào
    "không gửi" nghĩa là giữ nguyên và trường nào nghĩa là xoá.
    """

    query_text: str = Field("", max_length=MAX_QUERY_CHARS)
    search_type: str = Field("ensemble", max_length=32)
    params: dict[str, Any] = Field(default_factory=dict)
    # Khung người này bấm vào. None = vừa tìm xong, chưa chọn khung nào.
    picked_frame: str | None = Field(None, max_length=255)
    picked_video: str | None = Field(None, max_length=64)
    picked_frame_idx: int | None = None


def _state_row(row: sqlite3.Row) -> dict[str, Any]:
    try:
        params = json.loads(row["params"])
    except (ValueError, TypeError):
        # Một dòng hỏng không được làm chết cả danh sách của những người khác.
        params = {}
    return {
        "user": {
            "id": row["user_id"],
            "username": row["username"],
            "display_name": row["display_name"],
        },
        "query_text": row["query_text"],
        "search_type": row["search_type"],
        "params": params,
        "picked_frame": row["picked_frame"],
        "picked_video": row["picked_video"],
        "picked_frame_idx": row["picked_frame_idx"],
        "updated_at": row["updated_at"],
    }


@router.put("/tasks/{task_id}/search-state")
def save_search_state(
    task_id: int,
    payload: SearchStateRequest,
    user: Annotated[sqlite3.Row, Depends(active_user)],
    conn: Annotated[sqlite3.Connection, Depends(get_db)],
) -> dict[str, Any]:
    """Ghi trạng thái của CHÍNH người đang đăng nhập.

    user_id lấy từ token, không nhận từ body — nếu không thì ai cũng giả được
    trạng thái của người khác, và cả tính năng này dựa trên việc tin rằng dòng
    mang tên ai là do người đó gõ.
    """
    load_task(conn, task_id)
    params = json.dumps(payload.params, ensure_ascii=False)
    if len(params) > MAX_PARAMS_CHARS:
        params = "{}"
    conn.execute(
        "INSERT INTO search_states (user_id, task_id, query_text, search_type, "
        "params, picked_frame, picked_video, picked_frame_idx, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(user_id, task_id) DO UPDATE SET "
        "  query_text = excluded.query_text, "
        "  search_type = excluded.search_type, "
        "  params = excluded.params, "
        "  picked_frame = excluded.picked_frame, "
        "  picked_video = excluded.picked_video, "
        "  picked_frame_idx = excluded.picked_frame_idx, "
        "  updated_at = excluded.updated_at",
        (
            user["id"],
            task_id,
            payload.query_text,
            payload.search_type,
            params,
            payload.picked_frame,
            payload.picked_video,
            payload.picked_frame_idx,
            utcnow_iso(),
        ),
    )
    _remember(conn, user["id"], task_id, payload, params)
    return {"ok": True}


def _remember(
    conn: sqlite3.Connection,
    user_id: int,
    task_id: int,
    payload: SearchStateRequest,
    params: str,
) -> None:
    """Ghi truy vấn này vào lịch sử — hoặc cập nhật dòng cũ nếu vẫn là nó.

    Gộp theo TRUY VẤN, không theo mỗi lần bấm. Giao diện gọi endpoint này hai
    lần cho một lượt tìm — một lần khi search, một lần nữa mỗi khi bấm vào một
    khung — nên chèn mù sẽ đẻ ra mười dòng giống hệt nhau chỉ khác cái khung,
    và bảng lịch sử thành vô dụng.

    Chỉ so với dòng MỚI NHẤT của người đó. Quay lại một truy vấn đã bỏ từ lâu
    thì đáng là một mục mới: nó nói rằng bạn đã thử lại, và nó nổi lên đầu danh
    sách đúng như bạn vừa làm.
    """
    if not payload.query_text.strip():
        # Chưa gõ gì thì chưa có gì để nhớ. Lượt dọn dẹp cuối phiên cũng đi qua
        # đây với chuỗi rỗng, và nó không phải một lần tìm.
        return

    now = utcnow_iso()
    latest = conn.execute(
        "SELECT * FROM search_history WHERE user_id = ? AND task_id = ? "
        "ORDER BY updated_at DESC, id DESC LIMIT 1",
        (user_id, task_id),
    ).fetchone()
    same = (
        latest is not None
        and latest["query_text"] == payload.query_text
        and latest["search_type"] == payload.search_type
        and latest["params"] == params
    )
    if same:
        conn.execute(
            "UPDATE search_history SET picked_frame = ?, picked_video = ?, "
            "picked_frame_idx = ?, updated_at = ? WHERE id = ?",
            (
                payload.picked_frame,
                payload.picked_video,
                payload.picked_frame_idx,
                now,
                latest["id"],
            ),
        )
        return

    conn.execute(
        "INSERT INTO search_history (user_id, task_id, query_text, search_type, "
        "params, picked_frame, picked_video, picked_frame_idx, created_at, "
        "updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            user_id,
            task_id,
            payload.query_text,
            payload.search_type,
            params,
            payload.picked_frame,
            payload.picked_video,
            payload.picked_frame_idx,
            now,
            now,
        ),
    )


@router.get("/tasks/{task_id}/search-states")
def list_search_states(
    task_id: int,
    _: Annotated[sqlite3.Row, Depends(active_user)],
    conn: Annotated[sqlite3.Connection, Depends(get_db)],
) -> dict[str, Any]:
    """Trạng thái của MỌI người trên câu này, mới nhất đứng trước.

    Kể cả của chính mình. Giao diện tự lọc ra — trả về hết thì màn hình nào cần
    hiện "bạn đang tìm gì" cũng có sẵn, mà không phải gọi thêm lần nữa.
    """
    load_task(conn, task_id)
    rows = conn.execute(
        "SELECT s.*, u.username, u.display_name "
        "  FROM search_states s JOIN users u ON u.id = s.user_id "
        " WHERE s.task_id = ? "
        " ORDER BY s.updated_at DESC",
        (task_id,),
    )
    return {"states": [_state_row(row) for row in rows]}


@router.get("/tasks/{task_id}/search-history")
def list_search_history(
    task_id: int,
    _: Annotated[sqlite3.Row, Depends(active_user)],
    conn: Annotated[sqlite3.Connection, Depends(get_db)],
    limit: int = 200,
) -> dict[str, Any]:
    """Mọi truy vấn cả nhóm đã từng gõ cho câu này, mới nhất trước.

    Khác `/search-states` ở chỗ đó chỉ trả về MỘT dòng mỗi người — thứ họ đang
    gõ ngay bây giờ. Bảng này giữ cả những câu đã bỏ, nên "Coi Bằng làm" mở
    lại được truy vấn Bằng thử hồi mười phút trước, kể cả khi Bằng đã chuyển
    sang cách khác.
    """
    load_task(conn, task_id)
    rows = conn.execute(
        "SELECT h.*, u.username, u.display_name "
        "  FROM search_history h JOIN users u ON u.id = h.user_id "
        " WHERE h.task_id = ? "
        " ORDER BY h.updated_at DESC, h.id DESC LIMIT ?",
        (task_id, max(1, min(limit, 500))),
    )
    return {
        "entries": [
            {**_state_row(row), "id": row["id"], "created_at": row["created_at"]}
            for row in rows
        ]
    }


# Hai phạm vi xoá, và chỉ hai. Không có "xoá của Nam": bảng này là đường tìm của
# người ta, người duy nhất được quyết định bỏ nó đi là chính họ — hoặc admin khi
# cần dọn sạch cả câu trước một vòng thi mới.
CLEAR_MINE = "mine"
CLEAR_ALL = "all"


@router.delete("/tasks/{task_id}/search-history")
def clear_search_history(
    task_id: int,
    user: Annotated[sqlite3.Row, Depends(active_user)],
    conn: Annotated[sqlite3.Connection, Depends(get_db)],
    scope: str = CLEAR_MINE,
) -> dict[str, Any]:
    """Dọn lịch sử tìm của một câu.

    `scope="mine"` xoá các dòng của chính người gọi, `scope="all"` xoá của cả
    nhóm và đòi quyền admin. Khoá theo user_id lấy từ token, cùng luật với
    `save_search_state`: nếu không thì một người xoá được đường tìm của người
    khác giữa lúc đang thi.

    KHÔNG đụng vào `search_states`. Đó là "cả nhóm đang tìm gì ngay bây giờ",
    một thứ khác hẳn — xoá nó đi thì bảng trạng thái trống trơn trong khi mọi
    người vẫn đang gõ. Hệ quả: người vừa xoá mà còn nguyên truy vấn trên màn
    hình, bấm tiếp một khung là `_remember` chèn lại một dòng mới. Đúng như vậy
    — họ vẫn đang tìm truy vấn đó, và dòng mới mang giờ mới.

    Trả về `removed` chứ không phải một `ok` trơn, để màn hình nói được nó vừa
    bỏ đi bao nhiêu thay vì để người bấm đoán xem cú bấm có ăn không.
    """
    if scope not in (CLEAR_MINE, CLEAR_ALL):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"scope phải là '{CLEAR_MINE}' hoặc '{CLEAR_ALL}'",
        )
    if scope == CLEAR_ALL and user["role"] != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Chỉ admin xoá được lịch sử của cả nhóm",
        )

    task = load_task(conn, task_id)
    if scope == CLEAR_ALL:
        removed = conn.execute(
            "DELETE FROM search_history WHERE task_id = ?", (task_id,)
        ).rowcount
    else:
        removed = conn.execute(
            "DELETE FROM search_history WHERE task_id = ? AND user_id = ?",
            (task_id, user["id"]),
        ).rowcount

    if removed:
        audit.record(
            conn,
            user["id"],
            audit.SEARCH_HISTORY_CLEAR,
            f"task:{task_id}",
            f"Xoá {removed} dòng lịch sử tìm của câu {task['code']} (scope={scope})",
        )
    return {"removed": removed}
