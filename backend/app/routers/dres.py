# -*- coding: utf-8 -*-
"""Nộp bài vòng chung kết lên DRES: đề xuất, rồi duyệt.

Nộp sai trừ 10 điểm và cả đội dùng chung một tài khoản DRES, nên mọi bài đi
qua hai bước: "Đề xuất" (POST /submissions) ghi lại đúng chuỗi sẽ gửi, "Duyệt"
(POST /submissions/{id}/approve) mới ra mạng.

Ai được duyệt do `dres_config.submit_mode` quyết định, admin đổi trên tab DRES:
- 'admin_only' (mặc định): thành viên đề xuất, chỉ admin duyệt.
- 'everyone': ai cũng duyệt được — kể cả bài của chính mình, tức là tìm ra thì
  nộp luôn. Nhanh hơn vài giây mỗi câu, đổi lại mất lớp soát thứ hai.
Đổi tài khoản, evaluation và chính chế độ này thì luôn chỉ admin.

Ba thứ chặn mất điểm oan, đều ở server chứ không ở giao diện, và giữ nguyên ở
cả hai chế độ:
- Duyệt chiếm dòng bằng một UPDATE có điều kiện, nên bấm đúp hay hai người
  cùng bấm không thành hai lần nộp.
- Cùng một chuỗi, cùng một câu, không đề xuất được hai lần (BTC: "không được
  nộp trùng kết quả cho cùng một truy vấn").
- Lúc duyệt, nếu DRES đã chuyển sang câu khác so với lúc đề xuất thì từ chối:
  đáp án của câu trước gửi vào câu sau là một lần sai chắc chắn.

Mili-giây và số frame tính ở server từ fps trong keyframe_metadata.json (fps
của BTC), không lấy từ trình duyệt — một nguồn duy nhất, giống export.
"""
from __future__ import annotations

import json
import re
import sqlite3
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from app import audit, dres, preprocess
from app.auth.deps import active_user, require_admin
from app.db.connection import get_db, utcnow_iso

router = APIRouter(prefix="/api/dres", tags=["dres"])

# Dòng mà hệ thống coi là "đã/đang nộp" khi xét trùng. 'failed' và 'rejected'
# không tính: bài chưa tới được DRES thì đề xuất lại phải được.
_LIVE_STATUSES = ("proposed", "sending", "sent")

# Khớp CHECK của cột dres_config.submit_mode (migrations.py bước 9).
DEFAULT_SUBMIT_MODE = "admin_only"
SUBMIT_MODE_LABELS = {"admin_only": "chỉ admin nộp", "everyone": "mọi người nộp được"}

_VIDEO_RE = re.compile(r"^[A-Za-z0-9_\-]{1,64}$")


# ── cấu hình và phiên ─────────────────────────────────────────────────────────


def _config(conn: sqlite3.Connection) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM dres_config WHERE id = 1").fetchone()


def _require_config(conn: sqlite3.Connection) -> sqlite3.Row:
    cfg = _config(conn)
    if cfg is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail="Admin chưa nhập tài khoản DRES")
    return cfg


def _save_session(conn: sqlite3.Connection, session_id: str) -> None:
    conn.execute("UPDATE dres_config SET session_id = ? WHERE id = 1", (session_id,))


def _relogin(conn: sqlite3.Connection, cfg: sqlite3.Row) -> str:
    session_id = dres.login(cfg["base_url"], cfg["username"], cfg["password"])
    _save_session(conn, session_id)
    return session_id


def _with_session(conn: sqlite3.Connection, cfg: sqlite3.Row, call):
    """Gọi `call(session_id)`, đăng nhập lại đúng một lần nếu DRES báo 401.

    Phiên DRES có thể hết hạn giữa buổi thi; bắt admin đăng nhập lại bằng tay
    giữa một câu 5 phút là mất điểm vô ích.
    """
    session_id = cfg["session_id"] or _relogin(conn, cfg)
    try:
        return call(session_id)
    except dres.DresError as e:
        if e.http_status != 401:
            raise
    return call(_relogin(conn, cfg))


def _bad_gateway(e: dres.DresError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e))


def _status_payload(conn: sqlite3.Connection) -> dict[str, Any]:
    cfg = _config(conn)
    if cfg is None:
        return {"configured": False, "base_url": dres.DEFAULT_BASE_URL,
                "submit_mode": DEFAULT_SUBMIT_MODE}
    # Không bao giờ trả mật khẩu, kể cả cho admin: ô mật khẩu trên UI để trống
    # nghĩa là "giữ mật khẩu cũ".
    return {
        "configured": True,
        "base_url": cfg["base_url"],
        "username": cfg["username"],
        "logged_in": bool(cfg["session_id"]),
        "evaluation_id": cfg["evaluation_id"],
        "evaluation_name": cfg["evaluation_name"],
        "submit_mode": cfg["submit_mode"],
        "updated_at": cfg["updated_at"],
    }


def _can_submit(user: sqlite3.Row, cfg: sqlite3.Row | None) -> bool:
    mode = cfg["submit_mode"] if cfg is not None else DEFAULT_SUBMIT_MODE
    return user["role"] == "admin" or mode == "everyone"


def _require_submitter(user: sqlite3.Row, conn: sqlite3.Connection) -> sqlite3.Row:
    """Cấu hình DRES, sau khi chắc người này được gửi bài theo chế độ hiện tại.

    Đọc chế độ NGAY LÚC bấm, không tin thứ giao diện đang hiện: admin có thể
    vừa chuyển về 'admin_only' mà tab của thành viên chưa kịp cập nhật.
    """
    cfg = _require_config(conn)
    if not _can_submit(user, cfg):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Đang ở chế độ chỉ admin nộp bài")
    return cfg


def _auto_pick_evaluation(conn: sqlite3.Connection, evaluations: list[dict[str, Any]]) -> None:
    """Đúng một evaluation ACTIVE thì chọn luôn — buổi thi thường chỉ có một."""
    active = [e for e in evaluations if e.get("status") == "ACTIVE"]
    if len(active) == 1:
        conn.execute("UPDATE dres_config SET evaluation_id = ?, evaluation_name = ? WHERE id = 1",
                     (active[0]["id"], active[0]["name"]))


class ConfigIn(BaseModel):
    base_url: str = Field(default=dres.DEFAULT_BASE_URL, max_length=200)
    username: str = Field(min_length=1, max_length=200)
    # None / "" = giữ mật khẩu đã lưu.
    password: str | None = Field(default=None, max_length=200)


class EvaluationIn(BaseModel):
    evaluation_id: str = Field(min_length=1, max_length=200)


class SubmitModeIn(BaseModel):
    mode: Literal["admin_only", "everyone"]


@router.get("/status")
def get_status(
    _: Annotated[sqlite3.Row, Depends(active_user)],
    conn: Annotated[sqlite3.Connection, Depends(get_db)],
) -> dict[str, Any]:
    return _status_payload(conn)


@router.put("/config")
def put_config(
    payload: ConfigIn,
    user: Annotated[sqlite3.Row, Depends(require_admin)],
    conn: Annotated[sqlite3.Connection, Depends(get_db)],
) -> dict[str, Any]:
    base_url = payload.base_url.strip().rstrip("/")
    if not re.match(r"^https?://[^\s/]+", base_url):
        raise HTTPException(status_code=400, detail="URL DRES phải bắt đầu bằng http:// hoặc https://")
    old = _config(conn)
    password = payload.password or (old["password"] if old else None)
    if not password:
        raise HTTPException(status_code=400, detail="Cần nhập mật khẩu DRES")

    # Đăng nhập TRƯỚC khi lưu: sai mật khẩu thì báo ngay lúc admin còn đang
    # nhìn ô nhập, không để lộ ra ở lần nộp đầu tiên giữa câu thi.
    try:
        session_id = dres.login(base_url, payload.username.strip(), password)
    except dres.DresError as e:
        # Nói rõ đã thử tài khoản nào ở server nào: trình duyệt hay tự điền
        # tài khoản web của đội vào ô username, và "Invalid credentials" trần
        # trụi thì không ai nghĩ ra là ô đó đã bị đổi.
        raise HTTPException(
            status_code=400,
            detail=f"{e} — đã thử đăng nhập '{payload.username.strip()}' tại {base_url}",
        ) from e

    # Đổi server hay đổi tài khoản thì evaluation cũ không còn nghĩa gì.
    same_target = old is not None and old["base_url"] == base_url \
        and old["username"] == payload.username.strip()
    conn.execute(
        "INSERT INTO dres_config (id, base_url, username, password, session_id, "
        "evaluation_id, evaluation_name, updated_by, updated_at) "
        "VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(id) DO UPDATE SET base_url = excluded.base_url, "
        "username = excluded.username, password = excluded.password, "
        "session_id = excluded.session_id, evaluation_id = excluded.evaluation_id, "
        "evaluation_name = excluded.evaluation_name, updated_by = excluded.updated_by, "
        "updated_at = excluded.updated_at",
        (base_url, payload.username.strip(), password, session_id,
         old["evaluation_id"] if same_target else None,
         old["evaluation_name"] if same_target else None,
         user["id"], utcnow_iso()),
    )

    evaluations: list[dict[str, Any]] = []
    try:
        evaluations = dres.list_evaluations(base_url, session_id)
        if not same_target or not old["evaluation_id"]:
            _auto_pick_evaluation(conn, evaluations)
    except dres.DresError:
        pass  # đăng nhập được là đủ lưu; danh sách lấy lại sau cũng được
    return {**_status_payload(conn), "evaluations": evaluations}


@router.get("/evaluations")
def get_evaluations(
    _: Annotated[sqlite3.Row, Depends(require_admin)],
    conn: Annotated[sqlite3.Connection, Depends(get_db)],
) -> dict[str, Any]:
    cfg = _require_config(conn)
    try:
        evaluations = _with_session(conn, cfg, lambda s: dres.list_evaluations(cfg["base_url"], s))
    except dres.DresError as e:
        raise _bad_gateway(e) from e
    return {"evaluations": evaluations}


@router.put("/evaluation")
def put_evaluation(
    payload: EvaluationIn,
    _: Annotated[sqlite3.Row, Depends(require_admin)],
    conn: Annotated[sqlite3.Connection, Depends(get_db)],
) -> dict[str, Any]:
    cfg = _require_config(conn)
    try:
        evaluations = _with_session(conn, cfg, lambda s: dres.list_evaluations(cfg["base_url"], s))
    except dres.DresError as e:
        raise _bad_gateway(e) from e
    match = next((e for e in evaluations if e["id"] == payload.evaluation_id), None)
    if match is None:
        raise HTTPException(status_code=404, detail="DRES không có evaluation này")
    conn.execute("UPDATE dres_config SET evaluation_id = ?, evaluation_name = ? WHERE id = 1",
                 (match["id"], match["name"]))
    return _status_payload(conn)


@router.put("/submit-mode")
def put_submit_mode(
    payload: SubmitModeIn,
    user: Annotated[sqlite3.Row, Depends(require_admin)],
    conn: Annotated[sqlite3.Connection, Depends(get_db)],
) -> dict[str, Any]:
    cfg = _require_config(conn)
    if cfg["submit_mode"] != payload.mode:
        conn.execute("UPDATE dres_config SET submit_mode = ? WHERE id = 1", (payload.mode,))
        audit.record(
            conn, user["id"], audit.DRES_SUBMIT_MODE, "dres:config",
            f"Đổi chế độ nộp DRES: {SUBMIT_MODE_LABELS[cfg['submit_mode']]} → "
            f"{SUBMIT_MODE_LABELS[payload.mode]}",
            {"from": cfg["submit_mode"], "to": payload.mode},
        )
    return _status_payload(conn)


def _evaluation_id(conn: sqlite3.Connection, cfg: sqlite3.Row) -> str:
    if cfg["evaluation_id"]:
        return cfg["evaluation_id"]
    try:
        evaluations = _with_session(conn, cfg, lambda s: dres.list_evaluations(cfg["base_url"], s))
    except dres.DresError as e:
        raise _bad_gateway(e) from e
    _auto_pick_evaluation(conn, evaluations)
    picked = _config(conn)["evaluation_id"]
    if not picked:
        # Hai trường hợp cần làm khác nhau: 0 thì chờ BTC mở, nhiều thì admin
        # phải chọn. Đã gặp thật: team_460 ngoài buổi thi nhận về [].
        active = sum(1 for e in evaluations if e.get("status") == "ACTIVE")
        raise HTTPException(
            status_code=409,
            detail="DRES chưa mở evaluation nào cho đội — chờ BTC bắt đầu" if active == 0
            else f"DRES đang mở {active} evaluation — admin phải chọn một")
    return picked


def _current_task(conn: sqlite3.Connection, cfg: sqlite3.Row, evaluation_id: str):
    return _with_session(conn, cfg,
                         lambda s: dres.current_task(cfg["base_url"], s, evaluation_id))


@router.get("/current-task")
def get_current_task(
    _: Annotated[sqlite3.Row, Depends(active_user)],
    conn: Annotated[sqlite3.Connection, Depends(get_db)],
) -> dict[str, Any]:
    cfg = _require_config(conn)
    evaluation_id = _evaluation_id(conn, cfg)
    try:
        task = _current_task(conn, _config(conn), evaluation_id)
    except dres.DresError as e:
        raise _bad_gateway(e) from e
    return {"evaluation_id": evaluation_id, "task": task}


# ── đề xuất và duyệt ──────────────────────────────────────────────────────────


class ProposalIn(BaseModel):
    task_type: Literal["kis", "qa", "trake"]
    video_id: str = Field(min_length=1, max_length=64)
    # Đúng MỘT trong hai. `frames` khi chốt từ keyframe; `times_ms` khi chốt từ
    # trình phát video (thời điểm đang phát, chính xác hơn keyframe gần nhất).
    frames: list[int] | None = None
    times_ms: list[int] | None = None
    answer: str | None = Field(default=None, max_length=300)


def _fps(video_id: str) -> float:
    # _load_meta() trước, như route OCR: metadata chỉ được warm-up nạp, nên
    # thiếu dòng này thì trong 90–145 giây đầu sau mỗi lần restart, mọi video
    # đều "không có trong index". Chạy một lần rồi thành no-op.
    preprocess._load_meta()
    # frames_for_video trước: fps_for_video lùi về 25.0 khi không biết video,
    # và nộp theo một fps đoán là lệch mốc thời gian mà không ai hay.
    if not preprocess.frames_for_video(video_id):
        raise HTTPException(status_code=400,
                            detail=f"Video {video_id} không có trong index — không biết fps để quy đổi")
    return preprocess.fps_for_video(video_id)


def _points(p: ProposalIn) -> tuple[list[int], list[int]]:
    """(frames, times_ms) cùng độ dài, quy đổi bằng fps của BTC."""
    if (p.frames is None) == (p.times_ms is None):
        raise HTTPException(status_code=400, detail="Gửi đúng một trong hai: frames hoặc times_ms")
    given = p.frames if p.frames is not None else p.times_ms
    if not given or any(v < 0 for v in given):
        raise HTTPException(status_code=400, detail="Danh sách mốc rỗng hoặc có số âm")
    if p.task_type in ("kis", "qa") and len(given) != 1:
        raise HTTPException(status_code=400, detail=f"{p.task_type.upper()} nộp đúng một mốc")
    fps = _fps(p.video_id)
    if p.frames is not None:
        frames = list(p.frames)
        times = [round(f / fps * 1000) for f in frames]
    else:
        times = list(p.times_ms)
        frames = [round(t / 1000 * fps) for t in times]
    if p.task_type == "trake" and len(set(frames)) != len(frames):
        raise HTTPException(status_code=400, detail="TRAKE có hai mốc trùng frame")
    return frames, times


def _row_out(row: sqlite3.Row) -> dict[str, Any]:
    out = dict(row)
    for key in ("frames", "times_ms", "payload"):
        out[key] = json.loads(out[key])
    out["warnings"] = dres.warnings_for(row["task_type"], row["video_id"], row["answer_text"])
    return out


_SELECT_ROW = (
    "SELECT s.*, p.display_name AS proposed_by_name, r.display_name AS reviewed_by_name "
    "FROM dres_submissions s JOIN users p ON p.id = s.proposed_by "
    "LEFT JOIN users r ON r.id = s.reviewed_by "
)


def _load_row(conn: sqlite3.Connection, submission_id: int) -> sqlite3.Row:
    row = conn.execute(_SELECT_ROW + "WHERE s.id = ?", (submission_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Không có đề xuất này")
    return row


@router.get("/submissions")
def list_submissions(
    _: Annotated[sqlite3.Row, Depends(active_user)],
    conn: Annotated[sqlite3.Connection, Depends(get_db)],
    limit: int = Query(default=50, ge=1, le=500),
) -> dict[str, Any]:
    rows = conn.execute(_SELECT_ROW + "ORDER BY s.created_at DESC, s.id DESC LIMIT ?",
                        (limit,)).fetchall()
    return {"submissions": [_row_out(r) for r in rows]}


@router.post("/submissions", status_code=status.HTTP_201_CREATED)
def propose(
    payload: ProposalIn,
    user: Annotated[sqlite3.Row, Depends(active_user)],
    conn: Annotated[sqlite3.Connection, Depends(get_db)],
) -> dict[str, Any]:
    video_id = payload.video_id.strip()
    if not _VIDEO_RE.match(video_id):
        raise HTTPException(status_code=400, detail="Tên video không hợp lệ")
    answer = (payload.answer or "").strip() or None
    if payload.task_type == "qa":
        if not answer:
            raise HTTPException(status_code=400, detail="Câu Q&A phải có đáp án")
        if "\n" in answer or "\r" in answer:
            raise HTTPException(status_code=400, detail="Đáp án không được xuống dòng")
    else:
        answer = None
    frames, times = _points(payload.model_copy(update={"video_id": video_id}))

    cfg = _require_config(conn)
    evaluation_id = _evaluation_id(conn, cfg)
    # Tên câu đang chạy để lúc duyệt biết câu đã đổi chưa. Không lấy được thì
    # vẫn cho đề xuất — kiểm tra phụ không được phép chặn việc chính.
    try:
        task = _current_task(conn, _config(conn), evaluation_id)
    except dres.DresError:
        task = None
    task_name = task["name"] if task else None

    body = dres.build_payload(payload.task_type, video_id, times, frames, answer)
    body_json = json.dumps(body, ensure_ascii=False, sort_keys=True)

    conn.execute("BEGIN IMMEDIATE")
    try:
        duplicate = conn.execute(
            "SELECT id FROM dres_submissions WHERE evaluation_id = ? AND payload = ? "
            "AND COALESCE(dres_task_name, '') = COALESCE(?, '') "
            f"AND status IN ({','.join('?' * len(_LIVE_STATUSES))})",
            (evaluation_id, body_json, task_name, *_LIVE_STATUSES),
        ).fetchone()
        if duplicate is not None:
            conn.execute("ROLLBACK")
            raise HTTPException(status_code=409,
                                detail=f"Bài này đã được đề xuất/nộp (#{duplicate['id']})")
        cursor = conn.execute(
            "INSERT INTO dres_submissions (created_at, proposed_by, task_type, video_id, "
            "frames, times_ms, answer_text, evaluation_id, dres_task_name, payload, status) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'proposed')",
            (utcnow_iso(), user["id"], payload.task_type, video_id, json.dumps(frames),
             json.dumps(times), answer, evaluation_id, task_name, body_json),
        )
        conn.execute("COMMIT")
    except HTTPException:
        raise
    except Exception:
        conn.execute("ROLLBACK")
        raise
    return _row_out(_load_row(conn, cursor.lastrowid))


@router.post("/submissions/{submission_id}/approve")
def approve(
    submission_id: int,
    # active_user chứ không phải require_admin: quyền duyệt tuỳ submit_mode,
    # kiểm trong _require_submitter.
    user: Annotated[sqlite3.Row, Depends(active_user)],
    conn: Annotated[sqlite3.Connection, Depends(get_db)],
    # Bỏ qua kiểm tra "câu đã đổi". Chỉ dùng khi chắc chắn, ví dụ DRES đổi tên
    # câu giữa chừng.
    force: bool = Query(default=False),
) -> dict[str, Any]:
    cfg = _require_submitter(user, conn)
    row = _load_row(conn, submission_id)

    if not force and row["dres_task_name"]:
        try:
            task = _current_task(conn, cfg, row["evaluation_id"])
        except dres.DresError:
            task = {"name": row["dres_task_name"]}  # không kiểm được thì không chặn
        if task is None:
            raise HTTPException(status_code=409, detail="DRES không có câu nào đang chạy")
        if task["name"] != row["dres_task_name"]:
            raise HTTPException(
                status_code=409,
                detail=f"Đề xuất này cho câu '{row['dres_task_name']}', "
                       f"DRES đang chạy câu '{task['name']}'")

    # Chiếm dòng. rowcount = 0 nghĩa là người khác đã duyệt/từ chối trước.
    claimed = conn.execute(
        "UPDATE dres_submissions SET status = 'sending', reviewed_by = ?, reviewed_at = ?, "
        "error = NULL WHERE id = ? AND status IN ('proposed', 'failed')",
        (user["id"], utcnow_iso(), submission_id),
    ).rowcount
    if claimed == 0:
        raise HTTPException(status_code=409, detail="Đề xuất này đã được xử lý")

    body = json.loads(row["payload"])

    def send(session_id: str):
        code, result = dres.submit(cfg["base_url"], session_id, row["evaluation_id"], body)
        if code == 401:
            raise dres.DresError("Phiên DRES hết hạn", 401)
        return code, result

    try:
        code, result = _with_session(conn, _config(conn), send)
    except dres.DresError as e:
        # Lỗi mạng: KHÔNG biết bài đã tới DRES hay chưa. Để 'failed' cho admin
        # tự quyết bấm lại — tự thử lại có thể thành nộp hai lần.
        conn.execute("UPDATE dres_submissions SET status = 'failed', http_status = ?, error = ? "
                     "WHERE id = ?", (e.http_status, str(e), submission_id))
        return _row_out(_load_row(conn, submission_id))

    accepted = code in (200, 202)
    conn.execute(
        "UPDATE dres_submissions SET status = ?, http_status = ?, verdict = ?, "
        "dres_description = ?, error = ? WHERE id = ?",
        ("sent" if accepted else "failed", code,
         result.get("submission") if accepted else None,
         result.get("description"),
         None if accepted else (result.get("description") or f"DRES trả HTTP {code}"),
         submission_id),
    )
    return _row_out(_load_row(conn, submission_id))


@router.post("/submissions/{submission_id}/reject")
def reject(
    submission_id: int,
    user: Annotated[sqlite3.Row, Depends(active_user)],
    conn: Annotated[sqlite3.Connection, Depends(get_db)],
) -> dict[str, Any]:
    # Cùng quyền với duyệt: ai được gửi thì cũng được gạt một đề xuất đi — ở
    # chế độ 'everyone' đó là cách người đề xuất tự rút bài của mình.
    _require_submitter(user, conn)
    _load_row(conn, submission_id)
    changed = conn.execute(
        "UPDATE dres_submissions SET status = 'rejected', reviewed_by = ?, reviewed_at = ? "
        "WHERE id = ? AND status IN ('proposed', 'failed')",
        (user["id"], utcnow_iso(), submission_id),
    ).rowcount
    if changed == 0:
        raise HTTPException(status_code=409, detail="Đề xuất này đã được xử lý")
    return _row_out(_load_row(conn, submission_id))
