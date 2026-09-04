# -*- coding: utf-8 -*-
"""The answer basket: a hundred rows per task, ordered by sort_key.

Two things carry over from dev unchanged because they were already right: the
optimistic `version` check on PATCH, and deriving rank at read time so moving a
row is one UPDATE rather than a renumbering.

Autofill is a rewrite. dev copied the search order verbatim and derived TRAKE
frames as `base + i*18`, where 18 came from nowhere. Spec §7 replaces both with
the tactic the team actually uses: pin a video by hand, then spread frames
around the row you trust most.
"""
from __future__ import annotations

import json
import sqlite3
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app import audit
from app.answers import autofill
from app.auth.deps import active_user
from app.db.connection import get_db, utcnow_iso
from app.routers._shared import (
    after_sort_key,
    answer_payload,
    answers,
    answers_by_author,
    before_sort_key,
    load_task,
    next_sort_key,
    rows_per_query,
    top_sort_key,
)

router = APIRouter(prefix="/api", tags=["answers"])


class ChosenAuthorRequest(BaseModel):
    """Chọn bài của ai làm bài nộp cho câu này. None = bỏ chọn."""

    author_id: int | None = None


class AnswerCreateRequest(BaseModel):
    video_id: str
    frames: list[int]
    answer_text: str | None = None
    position: Any = None


class AnswerPatchRequest(BaseModel):
    version: int
    video_id: str | None = None
    frames: list[int] | None = None
    answer_text: str | None = None
    origin: str | None = None


class ReorderRequest(BaseModel):
    answer_id: int
    before_id: int | None = None
    after_id: int | None = None


class EventRange(BaseModel):
    """Khoảng người dùng khoanh cho MỘT sự kiện của câu TRAKE.

    Người làm bài xem video, thấy hành động 1 nằm đâu đó giữa frame 90 và 120,
    thì gõ đúng hai số đó. Chính xác hơn hẳn một "bước" chung: mỗi hành động
    dài ngắn khác nhau, và cái người ta THẤY là hai đầu, không phải khoảng cách.
    """

    lo: int = Field(0, ge=0)
    hi: int = Field(0, ge=0)
    # both | up | down — chỉ lấy phía trên mốc gốc, phía dưới, hay cả hai.
    mode: str = autofill.BOTH


class AutofillRequest(BaseModel):
    limit: int = Field(100, ge=1, le=500)
    # One second at 25 fps for KIS and Q&A. TRAKE overrides it to 2 from the
    # client: the rules put each event's window at "usually under 10 frames",
    # so a one-second step would jump clean over it.
    step: int = Field(25, ge=1, le=2000)
    # append       add rows until the basket reaches the target
    # replace_auto drop the generated rows, then refill - for changing the step
    # clear        drop the generated rows and stop
    mode: str = "append"

    # ── Rải quanh NHIỀU mốc ──────────────────────────────────────────────────
    #
    # Mặc định lấy mọi dòng ghim tay trong giỏ làm mốc. Trước đây chỉ lấy dòng
    # đầu, nên thấy bốn khung cùng đúng thì ba khung kia không được rải quanh —
    # phải tự ngồi tính từng số frame.
    #
    # anchor_ids khoanh lại còn đúng những dòng muốn dùng; bỏ trống là dùng hết.
    anchor_ids: list[int] | None = None
    # Bước riêng cho từng mốc, theo đúng thứ tự mốc. Thiếu phần tử nào thì phần
    # tử cuối được dùng tiếp; bỏ trống hẳn thì mọi mốc dùng chung `step`. Có
    # mặt vì hành động ở video quay chậm trải dài hơn hẳn video quay nhanh.
    steps: list[int] | None = None
    # both | up | down, dùng cho MỌI mốc chưa có chiều riêng.
    direction: str = autofill.BOTH
    # Chiều riêng cho từng mốc, cùng thứ tự với mốc. Mốc nằm giữa cảnh dài thì
    # rải hai phía; mốc nằm ngay đầu cảnh thì rải xuống là ném đi nửa số dòng.
    # Ép cả ba dùng chung một chiều là bắt hai mốc chịu thiệt vì mốc thứ ba.
    directions: list[str] | None = None
    # Độ dời LỚN NHẤT của từng mốc, cùng thứ tự với mốc — nửa rộng của đoạn
    # người dùng đã khoanh quanh nó. 0 hoặc thiếu = mốc đó không có mép.
    #
    # Đây là thứ cho phép mọi mốc dùng CHUNG một bước mà đoạn dài hơn vẫn nhận
    # nhiều dòng hơn: cùng bước, mốc có cửa sổ hẹp chạm mép sớm rồi nghỉ, mốc
    # có cửa sổ rộng đi tiếp. Tỉ lệ dòng rơi ra từ hình học nên không ai phải
    # tính nó, và thứ tự vòng tròn theo k giữ nguyên nên các hạng đầu vẫn chia
    # đều cho mọi phỏng đoán.
    #
    # Gửi một CON SỐ chứ không phải hai mép như `event_ranges`: bộ sinh chỉ cần
    # biết "đi xa nhất tới đâu". Gửi lo/hi thì backend phải tự tính lại đúng
    # phép max() mà giao diện vừa tính, và hai bên có thể bất đồng về khung nào
    # là tâm.
    reaches: list[int] | None = None

    # ── TRAKE: khoảng của từng SỰ KIỆN ───────────────────────────────────────
    #
    # Có mặt thì câu TRAKE chuyển hẳn sang cách rải khác: giữ nguyên N−1 mốc
    # của dòng neo và chỉ đổi MỘT mốc mỗi dòng, thay vì dời cả bộ đi cùng một
    # lượng. TRAKE chấm theo từng mốc nên sai một mốc chỉ mất 1/N — giữ lại
    # phần đúng của dòng hạng 1 đáng giá hơn nhiều so với đoán lại cả bộ.
    #
    # Bỏ trống thì giữ nguyên cách cũ (dời cả bộ), nên mọi lời gọi hiện có
    # không đổi hành vi.
    event_ranges: list[EventRange] | None = None


def _row_with_rank(conn: sqlite3.Connection, answer_id: int) -> sqlite3.Row:
    return conn.execute(
        "SELECT ROW_NUMBER() OVER (ORDER BY sort_key, id) AS rank, * "
        "FROM answers WHERE id = ?",
        (answer_id,),
    ).fetchone()


@router.get("/tasks/{task_id}/answers")
def list_answers(
    task_id: int,
    user: Annotated[sqlite3.Row, Depends(active_user)],
    conn: Annotated[sqlite3.Connection, Depends(get_db)],
    author_id: int | None = None,
) -> dict[str, Any]:
    """Danh sách của MỘT người. Mặc định là của chính người đang đăng nhập.

    author_id truyền vào để xem bài của người khác — màn Export cần nó. Xem
    được nhưng KHÔNG sửa được: mọi endpoint ghi ở dưới đều khoá cứng vào
    user["id"], không nhận author_id từ ngoài.
    """
    load_task(conn, task_id)
    who = author_id if author_id is not None else user["id"]
    return {"answers": answers(conn, task_id, who), "author_id": who}


@router.get("/tasks/{task_id}/answers/by-author")
def list_answers_by_author(
    task_id: int,
    _: Annotated[sqlite3.Row, Depends(active_user)],
    conn: Annotated[sqlite3.Connection, Depends(get_db)],
) -> dict[str, Any]:
    """Mọi danh sách của mọi người cho câu này, mỗi người một khối.

    Đây là thứ màn Export bày ra để bạn so 5 bài rồi chọn một.
    """
    task = load_task(conn, task_id)
    return {
        "groups": answers_by_author(conn, task_id),
        "chosen_author_id": task["chosen_author_id"],
    }


@router.post("/tasks/{task_id}/chosen-author")
def set_chosen_author(
    task_id: int,
    payload: ChosenAuthorRequest,
    user: Annotated[sqlite3.Row, Depends(active_user)],
    conn: Annotated[sqlite3.Connection, Depends(get_db)],
) -> dict[str, Any]:
    """Chọn danh sách của ai làm bài nộp cho câu này.

    Ai cũng chọn được, không chỉ admin: nhóm 5 người ngồi cùng lúc, bắt chờ
    một người bấm là dựng lại đúng cái nút cổ chai mà việc bỏ Nhận/Nhả vừa gỡ.
    Mọi lần đổi đều vào audit log nên vẫn lần lại được ai chọn gì.
    """
    task = load_task(conn, task_id)
    if payload.author_id is not None:
        has = conn.execute(
            "SELECT 1 FROM answers WHERE task_id = ? AND author_id = ? LIMIT 1",
            (task_id, payload.author_id),
        ).fetchone()
        if has is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Người đó chưa có đáp án nào cho câu này.",
            )
    conn.execute(
        "UPDATE tasks SET chosen_author_id = ?, version = version + 1 WHERE id = ?",
        (payload.author_id, task_id),
    )
    audit.record(
        conn, user["id"], audit.TASK_CHOOSE_AUTHOR, f"task:{task_id}",
        f"Chọn bài của user {payload.author_id} cho câu {task['code']}",
        {"chosen_author_id": payload.author_id},
    )
    return {"chosen_author_id": payload.author_id}


@router.post("/tasks/{task_id}/answers", status_code=201)
def create_answer(
    task_id: int,
    payload: AnswerCreateRequest,
    user: Annotated[sqlite3.Row, Depends(active_user)],
    conn: Annotated[sqlite3.Connection, Depends(get_db)],
) -> dict[str, Any]:
    load_task(conn, task_id)
    # Khoá cứng vào người đang đăng nhập. Không nhận author_id từ payload — cho
    # nhận thì một người ghi được vào danh sách của người khác, đúng thứ vừa bỏ đi.
    author = user["id"]
    if isinstance(payload.position, dict) and "after_id" in payload.position:
        sort_key = after_sort_key(
            conn, task_id, int(payload.position["after_id"]), author
        )
    elif payload.position == "top":
        sort_key = top_sort_key(conn, task_id, author)
    else:
        sort_key = next_sort_key(conn, task_id, author)

    now = utcnow_iso()
    cursor = conn.execute(
        "INSERT INTO answers "
        "(task_id, author_id, sort_key, video_id, frames, answer_text, origin, "
        " created_by, updated_by, updated_at, version) "
        "VALUES (?, ?, ?, ?, ?, ?, 'manual', ?, ?, ?, 1)",
        (
            task_id,
            author,
            sort_key,
            payload.video_id,
            json.dumps(payload.frames),
            payload.answer_text,
            user["id"],
            user["id"],
            now,
        ),
    )
    return {"answer": answer_payload(conn, _row_with_rank(conn, cursor.lastrowid))}


@router.patch("/answers/{answer_id}")
def patch_answer(
    answer_id: int,
    payload: AnswerPatchRequest,
    user: Annotated[sqlite3.Row, Depends(active_user)],
    conn: Annotated[sqlite3.Connection, Depends(get_db)],
):
    # author_id trong WHERE, giống delete_answer và reorder_answer. Thiếu nó ở
    # đây là lỗ tôi bỏ sót khi tách danh sách theo người: gửi id dòng của người
    # khác lên là sửa được đáp án chữ của họ, mà đúng ô đó mới là thứ được chấm
    # ở câu Q&A. Lọc ngay lúc đọc để "không phải của bạn" trả 404 chứ không rơi
    # xuống nhánh 409 bên dưới — 409 nói "người khác vừa sửa", một câu sai.
    row = conn.execute(
        "SELECT * FROM answers WHERE id = ? AND author_id = ?",
        (answer_id, user["id"]),
    ).fetchone()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="No such answer"
        )

    cursor = conn.execute(
        "UPDATE answers SET video_id = ?, frames = ?, answer_text = ?, origin = ?, "
        "updated_by = ?, updated_at = ?, version = version + 1 "
        "WHERE id = ? AND version = ?",
        (
            payload.video_id if payload.video_id is not None else row["video_id"],
            json.dumps(payload.frames) if payload.frames is not None else row["frames"],
            payload.answer_text
            if payload.answer_text is not None
            else row["answer_text"],
            payload.origin if payload.origin is not None else row["origin"],
            user["id"],
            utcnow_iso(),
            answer_id,
            payload.version,
        ),
    )
    if cursor.rowcount != 1:
        # Somebody edited this row between the client reading it and writing it.
        # Hand back what is there now so the UI can show both.
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={
                "detail": "Modified by someone else",
                "current": answer_payload(conn, _row_with_rank(conn, answer_id)),
            },
        )
    return {"answer": answer_payload(conn, _row_with_rank(conn, answer_id))}


@router.delete("/answers/{answer_id}")
def delete_answer(
    answer_id: int,
    user: Annotated[sqlite3.Row, Depends(active_user)],
    conn: Annotated[sqlite3.Connection, Depends(get_db)],
) -> dict[str, Any]:
    # Read the row before destroying it: the audit entry carries it, so a
    # misclick is recoverable rather than only explainable.
    snapshot = audit.snapshot_answers(conn, "id = ?", (answer_id,))
    # author_id trong WHERE: không có nó thì gửi id dòng của người khác lên là
    # xoá được bài của họ.
    cursor = conn.execute(
        "DELETE FROM answers WHERE id = ? AND author_id = ?",
        (answer_id, user["id"]),
    )
    if cursor.rowcount != 1:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="No such answer"
        )
    gone = snapshot[0]
    audit.record(
        conn,
        user["id"],
        audit.ANSWER_DELETE,
        f"task:{gone['task_id']}",
        f"Xoá 1 dòng ({gone['video_id']} · {gone['frames']})",
        {"answers": snapshot},
    )
    return {"ok": True}


@router.delete("/tasks/{task_id}/answers")
def clear_answers(
    task_id: int,
    user: Annotated[sqlite3.Row, Depends(active_user)],
    conn: Annotated[sqlite3.Connection, Depends(get_db)],
) -> dict[str, Any]:
    """Throw away the whole answer set for one task.

    Distinct from `autofill mode="clear"`, which spares the manual pins because
    its job is to let the spread be redone with a different step. This one is
    for the export screen: the reviewer looks at the CSV a query is about to
    submit, decides it is wrong, and starts that query over.

    `removed` rather than a bare ok, so the screen can say what it just threw
    away instead of leaving the reviewer guessing whether the click landed.

    This throws away a whole query's work for everyone, so the rows go into the
    audit entry on the way out and an admin can put them back.
    """
    task = load_task(conn, task_id)
    snapshot = audit.snapshot_answers(
        conn, "task_id = ? AND author_id = ?", (task_id, user["id"])
    )
    removed = conn.execute(
        "DELETE FROM answers WHERE task_id = ? AND author_id = ?",
        (task_id, user["id"]),
    ).rowcount
    if removed:
        audit.record(
            conn,
            user["id"],
            audit.ANSWERS_CLEAR,
            f"task:{task_id}",
            f"Xoá sạch {removed} dòng của task {task['code']}",
            {"answers": snapshot},
        )
    return {"removed": removed, "total": 0}


@router.post("/tasks/{task_id}/answers/reorder")
def reorder_answer(
    task_id: int,
    payload: ReorderRequest,
    # Trước đây là `_` vì không ai cần biết người gọi là ai. Giờ cần: mỗi người
    # một danh sách, nên phải biết đang sắp lại danh sách của ai.
    user: Annotated[sqlite3.Row, Depends(active_user)],
    conn: Annotated[sqlite3.Connection, Depends(get_db)],
) -> dict[str, Any]:
    load_task(conn, task_id)
    author = user["id"]
    if payload.before_id is not None:
        sort_key = before_sort_key(conn, task_id, payload.before_id, author)
    elif payload.after_id is not None:
        sort_key = after_sort_key(conn, task_id, payload.after_id, author)
    else:
        sort_key = top_sort_key(conn, task_id, author)
    # author_id trong WHERE: không có nó thì gửi id của dòng người khác lên là
    # xáo được thứ tự bài của họ.
    cursor = conn.execute(
        "UPDATE answers SET sort_key = ?, updated_at = ?, version = version + 1 "
        "WHERE id = ? AND task_id = ? AND author_id = ?",
        (sort_key, utcnow_iso(), payload.answer_id, task_id, author),
    )
    # Không khớp dòng nào thì nói ra, đừng trả 200. Trước đây gửi id dòng của
    # người khác lên sẽ được đáp "xong" kèm danh sách của chính mình — không hư
    # hại gì, nhưng là một câu trả lời sai, và giống hệt delete_answer ở trên
    # thì dễ đoán hơn.
    if cursor.rowcount != 1:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không có dòng này trong danh sách của bạn",
        )
    return {"answers": answers(conn, task_id, author)}


@router.post("/tasks/{task_id}/answers/autofill")
def autofill_answers(
    task_id: int,
    payload: AutofillRequest,
    user: Annotated[sqlite3.Row, Depends(active_user)],
    conn: Annotated[sqlite3.Connection, Depends(get_db)],
) -> dict[str, Any]:
    task = load_task(conn, task_id)
    target = min(payload.limit, rows_per_query(conn))

    if payload.mode in ("replace_auto", "clear"):
        # author_id phải có Ở CẢ HAI câu. Thiếu nó ở câu chụp ảnh, nhật ký sẽ
        # ghi luôn các dòng auto của người khác — những dòng KHÔNG hề bị xoá —
        # và bấm hoàn tác sẽ chèn lại chúng lần nữa, nhân đôi bài của họ.
        snapshot = audit.snapshot_answers(
            conn,
            "task_id = ? AND author_id = ? AND origin = 'auto'",
            (task_id, user["id"]),
        )
        removed = conn.execute(
            "DELETE FROM answers WHERE task_id = ? AND author_id = ? "
            "AND origin = 'auto'",
            (task_id, user["id"]),
        ).rowcount
        if removed:
            audit.record(
                conn,
                user["id"],
                audit.ANSWERS_AUTOFILL_CLEAR,
                f"task:{task_id}",
                f"Xoá {removed} dòng auto của task {task['code']}",
                {"answers": snapshot},
            )
        if payload.mode == "clear":
            total = conn.execute(
                "SELECT COUNT(*) AS n FROM answers WHERE task_id = ? "
                "AND author_id = ?",
                (task_id, user["id"]),
            ).fetchone()["n"]
            return {"added": 0, "removed": removed, "total": total}

    rows = conn.execute(
        "SELECT * FROM answers WHERE task_id = ? AND author_id = ? "
        "ORDER BY sort_key, id",
        (task_id, user["id"]),
    ).fetchall()
    if not rows:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Pin at least one answer first — autofill spreads around it.",
        )

    # Mốc là NHỮNG DÒNG NGƯỜI DÙNG TỰ GHIM, theo đúng thứ hạng họ xếp — không
    # phải thứ máy chấm cho là nhất (spec §7.1). Trước đây chỉ lấy rows[0]: thấy
    # bốn khung cùng đúng thì ba khung sau bị bỏ mặc.
    #
    # Dòng auto của lần điền trước không được làm mốc, nếu không thì mỗi lần
    # bấm lại sẽ rải quanh chính thứ mình vừa sinh ra và trôi xa dần khỏi khung
    # thật.
    candidates = [row for row in rows if row["origin"] != "auto"] or [rows[0]]
    if payload.anchor_ids:
        wanted = set(payload.anchor_ids)
        chosen = [row for row in candidates if row["id"] in wanted]
        if not chosen:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Không có dòng nào trong số đã chọn để làm mốc.",
            )
        candidates = chosen

    anchors: list[tuple[str, list[int], str | None]] = []
    for row in candidates:
        frames_of = [int(f) for f in json.loads(row["frames"])]
        if frames_of:
            anchors.append(
                (
                    row["video_id"],
                    frames_of,
                    row["answer_text"] if task["type"] == "qa" else None,
                )
            )
    if not anchors:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Không mốc nào có số frame để rải quanh.",
        )

    steps = [s for s in (payload.steps or []) if s > 0] or [payload.step]
    fallback = (
        payload.direction
        if payload.direction in autofill.DIRECTIONS
        else autofill.BOTH
    )
    # Chiều lạ rơi về `fallback` chứ không làm hỏng cả lượt điền: giá trị này
    # tới từ giao diện, và một chuỗi sai chính tả không đáng để mất 97 dòng.
    directions = [
        d if d in autofill.DIRECTIONS else fallback
        for d in (payload.directions or [])
    ] or [fallback]
    # Số âm về 0 = "không có mép" thay vì bị từ chối: một tầm âm là vô nghĩa,
    # và bỏ cả lượt điền vì nó thì mất 97 dòng cho một con số giao diện gửi
    # nhầm. KHÔNG cắt ngắn hay đệm cho đủ số mốc — `_reach_at` cố ý không rơi
    # về phần tử cuối, vì làm vậy là gán cửa sổ của mốc này cho mốc khác.
    reaches = [max(0, int(r)) for r in (payload.reaches or [])]

    taken = {
        (row["video_id"], tuple(int(f) for f in json.loads(row["frames"])))
        for row in rows
    }
    needed = max(0, target - len(rows))
    now = utcnow_iso()
    added = 0

    # Hai cách sinh, chọn theo việc người dùng có khoanh khoảng cho từng sự
    # kiện hay không. Sinh dư rồi lọc ở cả hai: một dòng có thể va vào dòng đã
    # có hoặc tụt xuống dưới 0, nên số lượt sinh luôn nhiều hơn số dòng thêm
    # được.
    budget = needed * 8 + 64
    use_events = bool(payload.event_ranges) and task["type"] == "trake"

    if use_events:
        # Đổi MỘT mốc mỗi dòng, giữ nguyên phần còn lại của dòng neo.
        ranges = payload.event_ranges or []
        reference = anchors[0][1]

        def build(want: int) -> list[list[list[int]]]:
            out: list[list[list[int]]] = []
            for _, anchor_frames, _ in anchors:
                per_event: list[list[int]] = []
                for position, base in enumerate(anchor_frames):
                    if position >= len(ranges):
                        # Sự kiện không được khoanh thì đứng yên. Đoán bừa một
                        # khoảng cho nó là bịa ra thông tin chưa ai đưa.
                        per_event.append([])
                        continue
                    window = ranges[position]
                    # Khoảng người dùng gõ là số frame TUYỆT ĐỐI, đọc từ dòng
                    # neo đầu tiên. Đem nguyên si áp lên dòng neo thứ hai ở một
                    # video khác thì vô nghĩa — nó từng cho ra [120, 800, ...],
                    # tức lấy khoảng của video này gán cho hành động của video
                    # kia. Nên quy về ĐỘ LỆCH quanh mốc gốc rồi mới áp.
                    origin = (
                        reference[position]
                        if position < len(reference)
                        else base
                    )
                    per_event.append(
                        autofill.event_variants(
                            base,
                            base + (window.lo - origin),
                            base + (window.hi - origin),
                            window.mode,
                            want,
                        )
                    )
                out.append(per_event)
            return out

        # Hạn mức cho TỪNG sự kiện, không phải cho cả lượt.
        #
        # Truyền cả `budget` vào đây là sai: nó sinh mọi frame trong khoảng rồi
        # vòng quay chỉ lấy phần GẦN mốc gốc nhất, cắt mất đúng hai đầu người
        # dùng vừa khoanh. Chia đều theo số dòng thật sự sẽ tới lượt mỗi sự
        # kiện thì bộ vị trí phủ trọn khoảng.
        slots = max(1, len(anchors) * max(1, len(ranges)))
        quota = -(-needed // slots)

        def events_source():
            seen: set[tuple[int, int, int]] = set()
            # Lượt một: đúng mật độ, phủ trọn khoảng.
            for triple in autofill.trake_plan(build(quota), budget):
                seen.add(triple)
                yield triple
            # Lượt hai: vét nốt nếu lượt một chưa đủ dòng — vài sự kiện có thể
            # có khoảng quá hẹp và cạn sớm.
            for triple in autofill.trake_plan(build(budget), budget):
                if triple not in seen:
                    yield triple

        source = (
            (index, list(anchors[index][1]), event, frame)
            for index, event, frame in events_source()
        )
    else:
        source = (
            (index, None, -1, delta)
            for index, delta in autofill.plan(
                len(anchors), steps, directions, budget, reaches
            )
        )

    for index, base_frames, event, value in source:
        if added >= needed:
            break
        video_id, anchor_frames, answer_text = anchors[index]
        if base_frames is not None:
            # Chỉ sự kiện `event` đổi; N−1 mốc kia giữ nguyên của dòng neo.
            frames = list(base_frames)
            frames[event] = value
        else:
            # Cách cũ: dời cả bộ đi cùng một lượng nên khoảng cách giữa các mốc
            # còn nguyên. Vẫn đúng khi người dùng tin cả bộ chỉ lệch pha.
            frames = [f + value for f in anchor_frames]
        key = (video_id, tuple(frames))
        if any(f < 0 for f in frames) or key in taken:
            continue
        taken.add(key)
        conn.execute(
            # 11 cột, 11 giá trị. Thêm author_id vào danh sách cột mà quên thêm
            # ô ở VALUES là lỗi tôi vừa mắc: SQLite đếm 10 giá trị cho 11 cột và
            # ném lỗi, còn nếu số có khớp thì 'auto' sẽ lặng lẽ rơi vào
            # answer_text — hỏng mà không báo gì.
            "INSERT INTO answers (task_id, author_id, sort_key, video_id, frames, "
            "answer_text, origin, created_by, updated_by, updated_at, version) "
            "VALUES (?, ?, ?, ?, ?, ?, 'auto', ?, NULL, ?, 1)",
            (
                task_id,
                user["id"],
                next_sort_key(conn, task_id, user["id"]),
                video_id,
                json.dumps(frames),
                answer_text,
                user["id"],
                now,
            ),
        )
        added += 1

    total = conn.execute(
        "SELECT COUNT(*) AS n FROM answers WHERE task_id = ? AND author_id = ?",
        (task_id, user["id"]),
    ).fetchone()["n"]
    return {"added": added, "total": total}
