# -*- coding: utf-8 -*-
"""Nói chuyện với DRES — hệ thống chấm điểm trực tiếp của vòng chung kết.

Tài liệu BTC: docs/HD-ChungKet-2026.pdf. Đặc tả chính thức:
https://github.com/dres-dev/DRES/blob/master/doc/oas-client.json

Ba lời gọi, đúng như tài liệu:
    POST /api/v2/login                          -> sessionId
    GET  /api/v2/client/evaluation/list         -> evaluationId đang ACTIVE
    POST /api/v2/submit/{evaluationId}          -> CORRECT | WRONG | INDETERMINATE | UNDECIDABLE
cộng thêm GET /api/v2/client/evaluation/currentTask/{id} để biết câu nào đang
chạy (ghi vào mỗi lần nộp, và dùng để chặn nộp trùng trong cùng một câu).

Server của mình đứng giữa trình duyệt và DRES, không để trình duyệt gọi thẳng:
khỏi đụng CORS, mật khẩu đội không nằm trên máy từng người, và mọi lần nộp của
cả đội đi qua một chỗ nên ghi lại và chặn trùng được.

urllib chứ không phải requests/httpx: requirements.txt không có thư viện HTTP
nào, và ba lời gọi JSON không đáng thêm một dependency lên image.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

DEFAULT_BASE_URL = "https://eventretrieval.one"

# Mạng phòng thi có thể chậm, nhưng 4–5 phút một câu thì treo 30 giây đã là mất
# 5 điểm. 10 giây rồi báo lỗi rõ ràng để admin quyết định bấm lại.
TIMEOUT_SECONDS = 10

TASK_TYPES = ("kis", "qa", "trake")


class DresError(Exception):
    """DRES trả lỗi hoặc không gọi được. `http_status` = None khi lỗi mạng."""

    def __init__(self, message: str, http_status: int | None = None):
        super().__init__(message)
        self.http_status = http_status


def _http(method: str, url: str, params: dict[str, str] | None = None,
          body: Any = None) -> tuple[int, Any]:
    """Một lời gọi JSON. Trả (mã HTTP, JSON đã parse — hoặc None).

    Không ném với mã 4xx/5xx: DRES trả ErrorStatus {status, description} kèm
    mã lỗi, và description đó là thứ admin cần đọc. Chỉ lỗi mạng mới ném.
    Test thay hàm này bằng một DRES giả.
    """
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    data = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(url, data=data, method=method)
    request.add_header("Accept", "application/json")
    if data is not None:
        request.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            code, raw = response.status, response.read()
    except urllib.error.HTTPError as e:
        code, raw = e.code, e.read()
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise DresError(f"Không gọi được DRES ({url.split('?')[0]}): {e}") from e
    try:
        return code, json.loads(raw) if raw else None
    except ValueError:
        return code, None


def _description(payload: Any, fallback: str) -> str:
    if isinstance(payload, dict) and payload.get("description"):
        return str(payload["description"])
    return fallback


def login(base_url: str, username: str, password: str) -> str:
    """Đăng nhập, trả sessionId."""
    code, payload = _http("POST", f"{base_url}/api/v2/login",
                          body={"username": username, "password": password})
    if code != 200 or not isinstance(payload, dict) or not payload.get("sessionId"):
        raise DresError(_description(payload, f"Đăng nhập DRES thất bại (HTTP {code})"), code)
    return str(payload["sessionId"])


def list_evaluations(base_url: str, session_id: str) -> list[dict[str, Any]]:
    code, payload = _http("GET", f"{base_url}/api/v2/client/evaluation/list",
                          params={"session": session_id})
    if code != 200 or not isinstance(payload, list):
        raise DresError(_description(payload, f"Không lấy được danh sách evaluation (HTTP {code})"), code)
    return [
        {"id": e.get("id"), "name": e.get("name"), "type": e.get("type"), "status": e.get("status")}
        for e in payload if isinstance(e, dict)
    ]


def current_task(base_url: str, session_id: str, evaluation_id: str) -> dict[str, Any] | None:
    """Câu đang chạy, hoặc None giữa hai câu (DRES trả 404 khi không có câu nào)."""
    code, payload = _http("GET", f"{base_url}/api/v2/client/evaluation/currentTask/{evaluation_id}",
                          params={"session": session_id})
    if code == 404:
        return None
    if code != 200 or not isinstance(payload, dict):
        raise DresError(_description(payload, f"Không lấy được câu hiện tại (HTTP {code})"), code)
    return {k: payload.get(k) for k in ("name", "taskGroup", "taskType", "duration")}


def submit(base_url: str, session_id: str, evaluation_id: str,
           payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    """Gửi một bài. Trả (mã HTTP, {status, submission, description}).

    Không ném khi DRES từ chối (400/404/412): lần từ chối cũng phải được ghi
    lại nguyên văn. Người gọi tự xem mã 401 để đăng nhập lại.
    """
    code, body = _http("POST", f"{base_url}/api/v2/submit/{evaluation_id}",
                       params={"session": session_id}, body=payload)
    return code, body if isinstance(body, dict) else {}


# ── Định dạng bài nộp ─────────────────────────────────────────────────────────
# MỘT chỗ duy nhất quyết định chuỗi gửi đi. Tài liệu BTC còn bốn điểm chưa rõ
# (xem warnings_for) — hỏi xong ở buổi tập huấn thì chỉ sửa ở đây.


def build_payload(task_type: str, video_id: str, times_ms: list[int],
                  frames: list[int], answer: str | None) -> dict[str, Any]:
    if task_type == "kis":
        # start = end: nộp một thời điểm, DRES chấm đúng nếu nó rơi vào đoạn
        # đáp án. start/end là int64 theo oas-client.json — ví dụ trong PDF
        # để trong dấu nháy như chuỗi, nhưng đặc tả mới là thứ server parse.
        answer_item: dict[str, Any] = {
            "mediaItemName": video_id, "start": times_ms[0], "end": times_ms[0],
        }
    elif task_type == "qa":
        answer_item = {"text": f"QA-{answer}-{video_id}-{times_ms[0]}"}
    elif task_type == "trake":
        # FRAME_ID: số thứ tự frame, không phải ms — tài liệu viết TIME(ms) cho
        # KIS/QA nhưng FRAME_ID cho TRAKE. Chưa xác nhận, xem warnings_for.
        answer_item = {"text": f"TR-{video_id}-{','.join(str(f) for f in frames)}"}
    else:
        raise ValueError(f"task_type phải là một trong {TASK_TYPES}")
    return {"answerSets": [{"answers": [answer_item]}]}


def warnings_for(task_type: str, video_id: str, answer: str | None) -> list[str]:
    """Những gì BTC chưa nói rõ và bài này dính vào. Hiện cho admin trước khi
    duyệt — không chặn, vì chưa biết BTC xử lý thế nào."""
    notes: list[str] = []
    if task_type in ("qa", "trake") and "-" in video_id:
        notes.append(f"Tên video '{video_id}' có dấu '-', trùng với dấu phân cách "
                     "của chuỗi nộp. Chưa rõ BTC tách chuỗi thế nào.")
    if task_type == "qa" and answer and "-" in answer:
        notes.append("Đáp án có dấu '-', trùng với dấu phân cách của chuỗi QA.")
    if task_type == "trake":
        notes.append("TRAKE đang nộp SỐ FRAME (theo tài liệu ghi FRAME_ID), chưa xác nhận với BTC.")
    return notes
