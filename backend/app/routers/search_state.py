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

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

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
    return {"ok": True}


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
