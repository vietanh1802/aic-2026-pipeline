# -*- coding: utf-8 -*-
"""Expand: một endpoint, một nhiệm vụ — dịch và mở rộng đề bài tiếng Việt.

POST /api/expansion  {query_text, task_type}
→ {eng_query, check_units, translated_query, provider, elapsed_ms}

Auth: mọi người đã đăng nhập (active_user), không khoá admin — đây là công cụ
soạn truy vấn, không phải thao tác xoá/chỉnh dữ liệu chung. Mỗi call tốn quota
Gemini hoặc GPU local nên không để truy cập ẩn danh.
"""
from __future__ import annotations

import sqlite3
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.auth.deps import active_user
from app.db.connection import get_db
from app.expansion import expand_query

router = APIRouter(prefix="/api/expansion", tags=["expansion"])

# Giới hạn khớp mọi đề bài đã thấy (dài nhất ~700 ký tự) nhưng chặn nút gửi
# cả đoạn văn bản vào API trả phí theo token.
_MAX_QUERY_CHARS = 2000


class ExpandRequest(BaseModel) :
    query_text : str = Field(min_length = 1, max_length = _MAX_QUERY_CHARS)
    task_type : str = Field(default = "KIS", pattern = "^(KIS|QA|TRAKE)$")


@router.post("")
def run_expand(
    payload : ExpandRequest,
    user : Annotated[sqlite3.Row, Depends(active_user)],
    conn : Annotated[sqlite3.Connection, Depends(get_db)],
) -> dict[str, Any] :
    result = expand_query(payload.query_text, payload.task_type)
    if (result.get("error")) :
        # Provider chết cả hai — 502 hợp hơn 200-with-error để frontend hiện
        # lỗi rõ ràng thay vì lặng lẽ ghi chuỗi rỗng vào ô search.
        from fastapi import HTTPException

        raise HTTPException(status_code = 502, detail = result["error"])
    return result
