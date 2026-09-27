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


# Trần số khung giữ cho MỘT truy vấn. Bằng số dòng tối đa của một câu — chốt
# nhiều hơn thế thì phần thừa không còn chỗ trong bài nộp. Có trần vì đây là
# JSON nằm trong một cột: không chặn thì một phiên dài biến nó thành vài chục
# KB đọc lại mỗi 5 giây theo nhịp poll của bảng lịch sử.
MAX_PICKS = 100


def _pick_of(payload: "SearchStateRequest") -> dict[str, Any] | None:
    """Khung vừa chốt, hoặc None khi lần ghi này không chốt gì.

    Thiếu `picked_video` hay `picked_frame_idx` thì không dựng lại được nút
    "▶ video · frame", nên nó không phải một lần chốt — lượt dọn cuối phiên đi
    qua đây với cả hai đều None.
    """
    if not payload.picked_video or payload.picked_frame_idx is None:
        return None
    return {
        "video": payload.picked_video,
        "frame": int(payload.picked_frame_idx),
        "name": payload.picked_frame,
    }


def _merge_pick(raw: Any, pick: dict[str, Any] | None) -> str:
    """Nối khung mới vào danh sách cũ, giữ thứ tự bấm.

    Thứ tự bấm là thứ tự người dùng tự xếp hạng, nên nối vào CUỐI chứ không
    chèn lên đầu. Bấm lại đúng khung cũ thì không thêm lần nữa — nó không phải
    một lựa chọn mới, và một dòng lặp lại làm bảng khó đọc mà không nói thêm
    được gì.
    """
    try:
        picks = json.loads(raw) if raw else []
    except (ValueError, TypeError):
        # Một dòng hỏng không được làm mất lần chốt đang diễn ra.
        picks = []
    if not isinstance(picks, list):
        picks = []
    if pick is not None:
        same = any(
            isinstance(p, dict)
            and p.get("video") == pick["video"]
            and p.get("frame") == pick["frame"]
            for p in picks
        )
        if not same and len(picks) < MAX_PICKS:
            picks.append(pick)
    return json.dumps(picks, ensure_ascii=False)


def _picks_of(row: sqlite3.Row) -> list[dict[str, Any]]:
    """Danh sách khung của một dòng lịch sử, đã tính cả dòng ghi trước bước 6.

    Dòng cũ có `picks` rỗng nhưng vẫn mang một khung ở ba cột `picked_*`. Trả
    về nó như một danh sách một phần tử để giao diện chỉ phải biết một hình
    dạng, thay vì mỗi chỗ hiển thị lại tự đi hỏi "dòng này cũ hay mới".
    """
    try:
        picks = json.loads(row["picks"]) if row["picks"] else []
    except (ValueError, TypeError, IndexError):
        picks = []
    if not isinstance(picks, list):
        picks = []
    if picks:
        return [p for p in picks if isinstance(p, dict)]
    if row["picked_video"] and row["picked_frame_idx"] is not None:
        return [
            {
                "video": row["picked_video"],
                "frame": row["picked_frame_idx"],
                "name": row["picked_frame"],
            }
        ]
    return []


def close_attempt_if_basket_empty(
    conn: sqlite3.Connection, user_id: int, task_id: int
) -> None:
    """Giỏ vừa cạn thì khép lượt lịch sử đang mở của người này.

    Gọi từ mọi đường xoá đáp án. Không có nó thì cùng một truy vấn, chốt ba
    khung rồi xoá sạch rồi chốt hai khung khác sẽ dồn cả năm vào một dòng — và
    đọc lại không ai biết ba khung đầu đã bị chính người đó loại.

    Khép theo GIỎ CẠN chứ không theo mỗi lần xoá: xoá một trong ba dòng là sửa
    sai, không phải làm lại, và tách dòng ở đó chỉ làm bảng vụn ra.

    Chỉ khép mục CÓ khung. Mục chưa chốt gì thì không có gì để giữ lại, mà khép
    nó sẽ đẻ thêm một dòng rỗng nữa ngay sau đó.
    """
    left = conn.execute(
        "SELECT COUNT(*) AS n FROM answers WHERE task_id = ? AND author_id = ?",
        (task_id, user_id),
    ).fetchone()["n"]
    if left:
        return
    conn.execute(
        "UPDATE search_history SET closed_at = ? WHERE id = ("
        "  SELECT id FROM search_history"
        "   WHERE user_id = ? AND task_id = ? AND closed_at IS NULL"
        "     AND picks NOT IN ('', '[]')"
        "   ORDER BY updated_at DESC, id DESC LIMIT 1)",
        (utcnow_iso(), user_id, task_id),
    )


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
        # Lượt đã khép thì không nối vào nữa, dù truy vấn y hệt. Giỏ cạn giữa
        # chừng nghĩa là người dùng đã bỏ hết những gì chốt trước đó — hai lượt
        # tách bạch, không phải một lượt kéo dài.
        and latest["closed_at"] is None
        and latest["query_text"] == payload.query_text
        and latest["search_type"] == payload.search_type
        and latest["params"] == params
    )
    pick = _pick_of(payload)
    if same:
        # NỐI vào danh sách chứ không ghi đè. Ba cột picked_* vẫn nhận khung
        # mới nhất — chúng là hình dạng search_states dùng chung — nhưng thứ
        # bảng lịch sử bày ra giờ là cả danh sách.
        #
        # Không chốt gì thì đừng đụng vào: lượt ghi khi vừa đổi tham số cũng đi
        # qua đây với picked_* rỗng, và để nó xoá ba khung vừa chọn thì đúng
        # bằng lỗi cũ, chỉ khác đường tới.
        if pick is None:
            conn.execute(
                "UPDATE search_history SET updated_at = ? WHERE id = ?",
                (now, latest["id"]),
            )
            return
        conn.execute(
            "UPDATE search_history SET picked_frame = ?, picked_video = ?, "
            "picked_frame_idx = ?, picks = ?, updated_at = ? WHERE id = ?",
            (
                payload.picked_frame,
                payload.picked_video,
                payload.picked_frame_idx,
                _merge_pick(latest["picks"], pick),
                now,
                latest["id"],
            ),
        )
        return

    conn.execute(
        "INSERT INTO search_history (user_id, task_id, query_text, search_type, "
        "params, picked_frame, picked_video, picked_frame_idx, picks, "
        "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            user_id,
            task_id,
            payload.query_text,
            payload.search_type,
            params,
            payload.picked_frame,
            payload.picked_video,
            payload.picked_frame_idx,
            _merge_pick(None, pick),
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
            {
                **_state_row(row),
                "id": row["id"],
                "created_at": row["created_at"],
                # Chỉ bảng lịch sử có trường này. `search_states` là "đang tìm
                # gì NGAY BÂY GIỜ", một dòng mỗi người, và ở đó khung mới nhất
                # mới là câu trả lời đúng — gom cả danh sách vào đó sẽ biến nó
                # thành một bảng lịch sử thứ hai.
                "picks": _picks_of(row),
            }
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
