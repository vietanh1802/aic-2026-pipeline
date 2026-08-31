# -*- coding: utf-8 -*-
"""Build the submission files.

Row shapes are confirmed against the 2025 ground truth in
docs/Danh_gia_Query_AIC2025.md:

    KIS     L21_V015,25605
    Q&A     L30_V072,1745,Xã Giang Ly
    TRAKE   L26_V194,4707,5100,5425,5850

The output filename reuses the input stem and changes only the extension —
query-p1-15-qa.txt in, query-p1-15-qa.csv out — so a reviewer can line the two
up. That, and the flat one-file-per-task packaging, are the two parts with no
direct evidence behind them; both are settings.
"""
from __future__ import annotations

import io
import json
import sqlite3
import unicodedata
import zipfile
from urllib.parse import quote
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app import audit
from app.auth.deps import active_user
from app.db.connection import get_db
from app.routers._shared import answers, load_task, rows_per_query
from app.settings_store import all_settings

router = APIRouter(prefix="/api", tags=["export"])

# Tên gói tải xuống, cố định. Frontend cũng dùng đúng hằng này (SUBMISSION_ZIP
# trong Export.tsx) — hai chỗ lệch nhau thì tên file lưu xuống máy không phải
# tên máy chủ gửi, vì thẻ <a download> luôn thắng header.
SUBMISSION_ZIP_NAME = "submission.zip"


# Nháy cong vào đây từ đề bài của ban tổ chức và từ mọi thứ dán ra khỏi Word.
# Nắn về dạng thẳng để cùng một đáp án gõ ở hai chỗ ra cùng một byte — dán từ
# đề bài hay gõ tay đều cho “13” thành "13". Chỉ NẮN, không xoá: dấu nháy là
# nội dung người dùng cố ý gõ.
_QUOTE_FOLD = str.maketrans({
    "“": '"', "”": '"', "„": '"', "‟": '"',
    "‘": "'", "’": "'", "‚": "'", "‛": "'",
    "«": '"', "»": '"',
})


def clean_answer(text: str | None) -> str:
    """Đáp án, đúng như người dùng gõ.

    Chỉ làm hai việc: nắn nháy cong về nháy thẳng, và cắt khoảng trắng thừa.
    Nháy được GIỮ NGUYÊN — gõ "13" thì file phải có "13".

    Bản trước xoá sạch dấu nháy. Đó là cách chữa cho lỗi ba-dấu-nháy hồi vòng 1
    (spec.md:35), nhưng chữa nhầm chỗ: thủ phạm là csv.writer bọc cả trường
    rồi nhân đôi nháy bên trong, không phải bản thân dấu nháy. Xoá đi thì hết
    lỗi đó nhưng mất luôn nội dung người ta cố ý gõ.

    Xuống dòng thì bị thay bằng dấu cách. Đây là thứ duy nhất bắt buộc phải
    đụng tới: một ký tự xuống dòng trong ô đáp án sẽ cắt một dòng đáp án thành
    hai, làm lệch toàn bộ thứ hạng phía sau.
    """
    if not text:
        return ""
    folded = text.translate(_QUOTE_FOLD)
    return " ".join(folded.split("\n")).strip()


def export_filename(source_filename: str, settings: dict[str, Any] | None = None,
                    code: str = "", task_type: str = "") -> str:
    """`query-p1-15-qa.txt` -> `query-p1-15-qa.csv`.

    Falls back to the configured pattern when the pack predates the column or a
    task somehow has no source file recorded.
    """
    if source_filename:
        stem = source_filename.rsplit(".", 1)[0]
        return f"{stem}.csv"
    pattern = str((settings or {}).get("export.filename_pattern", "query-{id}-{type}.csv"))
    return pattern.format(id=code, type=task_type)


def csv_content(
    settings: dict[str, Any], task: sqlite3.Row, rows: list[dict[str, Any]]
) -> str:
    """Nội dung một file nộp.

    Ghép trường bằng tay, KHÔNG dùng csv.writer.

    csv.writer tuân thủ RFC 4180: gặp dấu nháy trong một trường, nó bọc cả
    trường trong nháy rồi nhân đôi nháy bên trong, nên đáp án 13 kèm hai dấu
    nháy sẽ ra thành sáu dấu nháy — ba mỗi bên. Đúng chuẩn CSV, nhưng luật
    thi (§2.1.2) viết một dòng đáp án
    là `L05_V005, 888, màu xanh` — thẳng, không bọc, không thoát ký tự. Ở định
    dạng đó thì mọi thao tác thoát ký tự đều là làm hỏng nội dung.

    Đánh đổi: dấu phân cách nằm TRONG đáp án sẽ đi thẳng ra file và bên chấm
    đọc thành hai trường. Không có cách nào vừa giữ nguyên chữ vừa tránh được
    điều đó ở một định dạng không có quy ước bọc trường — chọn giữ nguyên chữ,
    vì đó là thứ người dùng gõ ra và nhìn thấy ở khung xem trước.
    """
    delimiter = str(settings.get("export.delimiter", ","))
    line_ending = "\r\n" if settings.get("export.line_ending") == "CRLF" else "\n"
    include_header = bool(settings.get("export.header", False))

    lines: list[str] = []

    if include_header:
        header = ["video_id", "frame"]
        if task["type"] == "qa":
            header.append("answer")
        elif task["type"] == "trake":
            header = ["video_id"] + [
                f"frame_{i + 1}" for i in range(int(task["n_events"] or 1))
            ]
        lines.append(delimiter.join(header))

    for row in rows:
        frames = row["frames"]
        first = str(frames[0]) if frames else ""
        if task["type"] == "qa":
            fields = [row["video_id"], first, clean_answer(row["answer_text"])]
        elif task["type"] == "trake":
            fields = [row["video_id"], *(str(frame) for frame in frames)]
        else:
            fields = [row["video_id"], first]
        lines.append(delimiter.join(fields))

    # Kết thúc bằng dấu xuống dòng sau dòng CUỐI, y như csv.writer trước đây —
    # nhiều bộ đọc coi file thiếu dấu xuống dòng cuối là file bị cắt dở.
    return "".join(line + line_ending for line in lines)


def ascii_fallback(name: str) -> str:
    """"Vòng sơ tuyển — thử local.zip" -> "Vong so tuyen  thu local.zip".

    Bỏ dấu bằng NFKD rồi vứt mọi ký tự ngoài ASCII. Chỉ dùng cho tham số
    `filename=` cũ, thứ mà trình duyệt đời cũ đọc khi không hiểu `filename*`.
    """
    stripped = unicodedata.normalize("NFKD", name)
    ascii_only = stripped.encode("ascii", "ignore").decode("ascii")
    # Dấu " và \ sẽ phá chuỗi trong ngoặc kép của header.
    ascii_only = ascii_only.replace('"', "").replace("\\", "")
    return ascii_only.strip() or "submission.zip"


def content_disposition(filename: str) -> str:
    """Header tải file, an toàn với tên có dấu tiếng Việt.

    Header HTTP chỉ mã hoá được latin-1. Nhét thẳng "Vòng sơ tuyển" vào đây
    khiến Starlette ném UnicodeEncodeError và nút "Tải zip" trả 500 — mà nhãn
    vòng thì gần như luôn có dấu, nên lỗi này chỉ chờ đúng vòng thi mới hiện.

    RFC 6266: `filename=` giữ bản ASCII cho trình duyệt cũ, `filename*=` mang
    tên thật đã mã hoá UTF-8. Trình duyệt nào hiểu cả hai sẽ ưu tiên cái sau.
    """
    return (
        f'attachment; filename="{ascii_fallback(filename)}"; '
        f"filename*=UTF-8''{quote(filename, safe='')}"
    )


def has_answers(conn: sqlite3.Connection, task_id: int) -> bool:
    """Câu này đã có ai bỏ dòng nào vào chưa, bất kể của ai."""
    return (
        conn.execute(
            "SELECT 1 FROM answers WHERE task_id = ? LIMIT 1", (task_id,)
        ).fetchone()
        is not None
    )


DEFAULT_PHASE = "p1"


def normalize_phase(raw: str | None) -> str:
    """"2", "p2", "P2", " p2 " -> "p2". Rỗng hoặc vô nghĩa -> "p1".

    Nhận cả dạng chỉ có số vì đó là thứ người ta gõ khi được hỏi "vòng mấy".
    Không nhận bừa mọi chuỗi: giá trị này đi thẳng vào tên file nộp, nên một
    ký tự lạ lọt vào là hỏng cả gói.
    """
    if raw is None:
        return DEFAULT_PHASE
    text = raw.strip().lower().lstrip("p")
    return f"p{text}" if text.isdigit() else DEFAULT_PHASE


def pack_phase(conn: sqlite3.Connection, pack_id: int) -> str:
    row = conn.execute(
        "SELECT phase FROM packs WHERE id = ?", (pack_id,)
    ).fetchone()
    return normalize_phase(row["phase"] if row else None)


def _task_source_filename(conn: sqlite3.Connection, task: sqlite3.Row) -> str:
    """Dựng lại tên file đề bài mà ban tổ chức đã phát, vd query-p2-15-qa.txt.

    Số vòng lấy từ packs.phase, đặt lúc nhập gói từ chính tên file trong zip.
    Trước đây chỗ này viết cứng "p1", nên một gói vòng 2 xuất ra vẫn mang tên
    vòng 1 — sai tên file nộp và không có gì báo.
    """
    return (
        f"query-{pack_phase(conn, task['pack_id'])}-"
        f"{task['code']}-{task['type']}.txt"
    )


class PhaseRequest(BaseModel):
    """Số vòng, gõ kiểu gì cũng nhận: "2", "p2", "P2"."""

    phase: str


@router.get("/export/phase")
def read_phase(
    _: Annotated[sqlite3.Row, Depends(active_user)],
    conn: Annotated[sqlite3.Connection, Depends(get_db)],
    pack_id: int,
) -> dict[str, Any]:
    """Số vòng hiện tại, kèm một tên file mẫu.

    Tên mẫu mới là thứ đáng nhìn: "p2" không nói lên gì, còn
    `query-p2-15-qa.csv` thì đối chiếu được ngay với file ban tổ chức phát.
    """
    phase = pack_phase(conn, pack_id)
    stored = conn.execute(
        "SELECT phase FROM packs WHERE id = ?", (pack_id,)
    ).fetchone()
    sample = conn.execute(
        "SELECT code, type FROM tasks WHERE pack_id = ? "
        "ORDER BY CAST(code AS INTEGER), code LIMIT 1",
        (pack_id,),
    ).fetchone()
    return {
        "phase": phase,
        # True khi gói được nhập trước khi có cột này, hoặc tên file không khớp
        # mẫu nên không tách ra được số vòng. Giao diện cảnh báo để người dùng
        # tự kiểm, thay vì im lặng nộp bằng "p1".
        "guessed": stored is None or stored["phase"] is None,
        "sample_filename": (
            f"query-{phase}-{sample['code']}-{sample['type']}.csv"
            if sample
            else None
        ),
    }


@router.post("/export/phase")
def set_phase(
    payload: PhaseRequest,
    user: Annotated[sqlite3.Row, Depends(active_user)],
    conn: Annotated[sqlite3.Connection, Depends(get_db)],
    pack_id: int,
) -> dict[str, Any]:
    """Đặt số vòng cho gói này.

    Không giới hạn cho admin. Cả nhóm ngồi cùng lúc và người phát hiện tên file
    sai thường là người đang mở màn Export — bắt chờ một người bấm là dựng lại
    đúng nút cổ chai mà việc bỏ Nhận/Nhả đã gỡ. Bù lại thì ghi nhật ký.
    """
    before = conn.execute(
        "SELECT phase FROM packs WHERE id = ?", (pack_id,)
    ).fetchone()
    if before is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Không có gói này."
        )
    phase = normalize_phase(payload.phase)
    conn.execute("UPDATE packs SET phase = ? WHERE id = ?", (phase, pack_id))
    if phase != before["phase"]:
        audit.record(
            conn,
            user["id"],
            audit.PACK_SET_PHASE,
            f"pack:{pack_id}",
            f"Đổi số vòng trong tên file nộp: "
            f"{before['phase'] or '(chưa đặt)'} → {phase}",
        )
    return read_phase(user, conn, pack_id)


@router.get("/export/validate")
def validate_export(
    _: Annotated[sqlite3.Row, Depends(active_user)],
    conn: Annotated[sqlite3.Connection, Depends(get_db)],
    pack_id: int,
) -> dict[str, Any]:
    target = rows_per_query(conn)
    issues: list[dict[str, str]] = []

    for task in conn.execute(
        "SELECT * FROM tasks WHERE pack_id = ? ORDER BY CAST(code AS INTEGER), code",
        (pack_id,),
    ):
        # Bài nộp là MỘT danh sách, nên phải biết lấy của ai. answers() không
        # truyền tác giả sẽ gộp cả 5 người lại — ra một file trộn lẫn mà không
        # ai để ý, vì nó vẫn đủ 100 dòng và vẫn hợp lệ về hình thức.
        if task["chosen_author_id"] is None:
            # Câu chưa ai làm thì không có gì để chọn, và nó ra file rỗng —
            # đúng như trước khi có nhiều người. Báo là "error" ở đây sẽ khiến
            # cả 25 câu của một vòng mới toanh đều đỏ lòm ngay lúc vừa nhập
            # gói, che mất những cảnh báo thật.
            if has_answers(conn, task["id"]):
                issues.append(
                    {
                        "task_code": task["code"],
                        "severity": "error",
                        "message": "có người làm nhưng chưa chọn nộp bài của ai",
                    }
                )
            else:
                issues.append(
                    {
                        "task_code": task["code"],
                        "severity": "info",
                        "message": "chưa ai làm — sẽ nộp file rỗng",
                    }
                )
            continue
        rows = answers(conn, task["id"], task["chosen_author_id"])

        if len(rows) < target:
            issues.append(
                {
                    "task_code": task["code"],
                    "severity": "warning",
                    "message": f"thiếu {target - len(rows)} dòng",
                }
            )

        if task["type"] == "qa":
            empty = sum(1 for row in rows if not (row["answer_text"] or "").strip())
            if empty:
                issues.append(
                    {
                        "task_code": task["code"],
                        "severity": "warning",
                        "message": f"{empty} dòng chưa có đáp án chữ",
                    }
                )

            # Dấu phân cách nằm trong đáp án giờ đi thẳng ra file, nên bên
            # chấm sẽ đọc thành hai trường. Không tự sửa được mà không làm
            # hỏng chữ, nên chỉ báo ra để nhóm tự chỉnh lại câu văn.
            has_comma = sum(1 for row in rows if "," in (row["answer_text"] or ""))
            if has_comma:
                issues.append(
                    {
                        "task_code": task["code"],
                        "severity": "warning",
                        "message": f"{has_comma} dòng có dấu phẩy trong đáp án, kiểm tra lại trước khi nộp",
                    }
                )

        if task["type"] == "trake":
            n_events = int(task["n_events"] or 1)
            short = sum(1 for row in rows if len(row["frames"]) < n_events)
            if short:
                issues.append(
                    {
                        "task_code": task["code"],
                        "severity": "warning",
                        "message": f"{short} dòng chưa đủ {n_events} mốc",
                    }
                )

        seen: set[tuple[str, str, str | None]] = set()
        dupes = 0
        for row in rows:
            key = (row["video_id"], json.dumps(row["frames"]), row["answer_text"])
            if key in seen:
                dupes += 1
            seen.add(key)
        if dupes:
            issues.append(
                {
                    "task_code": task["code"],
                    "severity": "info",
                    "message": f"{dupes} dòng trùng nhau",
                }
            )

    return {"ready": not issues, "issues": issues}


@router.get("/export/preview")
def preview_export(
    _: Annotated[sqlite3.Row, Depends(active_user)],
    conn: Annotated[sqlite3.Connection, Depends(get_db)],
    task_id: int,
) -> dict[str, Any]:
    task = load_task(conn, task_id)
    settings = all_settings(conn)
    if task["chosen_author_id"] is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Câu {task['code']} chưa chọn bài của ai để nộp.",
        )
    rows = answers(conn, task_id, task["chosen_author_id"])
    content = csv_content(settings, task, rows)
    return {
        "filename": export_filename(
            _task_source_filename(conn, task), settings, task["code"], task["type"]
        ),
        "rows": len(rows),
        "bytes": len(content.encode(str(settings.get("export.encoding", "utf-8")))),
        "content": content,
    }


def build_zip(conn: sqlite3.Connection, pack_id: int) -> bytes:
    """Gói nộp, dưới dạng bytes.

    Tách khỏi endpoint để đọc được kết quả mà không phải rút một
    StreamingResponse: `body_iterator` của nó là async, nên kiểm tên file bên
    trong zip từ một test đồng bộ là không làm được.
    """
    settings = all_settings(conn)

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for task in conn.execute(
            "SELECT * FROM tasks WHERE pack_id = ? ORDER BY CAST(code AS INTEGER), code",
            (pack_id,),
        ):
            # Ba trường hợp, chỉ MỘT trong ba là lỗi:
            #
            #   chưa ai làm          -> file rỗng, như trước khi có nhiều người
            #   đã chọn người        -> lấy bài của người đó
            #   có người làm, chưa chọn -> từ chối
            #
            # Bản trước từ chối cả trường hợp đầu, nên chỉ cần một câu trong 25
            # câu chưa ai đụng tới là không tải được zip — mà câu chưa ai làm
            # thì vĩnh viễn không thể chọn được ai. Gói nộp bao giờ cũng phải
            # đủ 25 file; câu bỏ trống ra file rỗng mới đúng.
            rows: list[dict[str, Any]] = []
            if task["chosen_author_id"] is not None:
                rows = answers(conn, task["id"], task["chosen_author_id"])
            elif has_answers(conn, task["id"]):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Câu {task['code']} có người làm nhưng chưa chọn nộp "
                           f"bài của ai. Sang tab Evaluation chọn trước khi tải zip.",
                )
            content = csv_content(settings, task, rows)
            archive.writestr(
                export_filename(
                    _task_source_filename(conn, task),
                    settings,
                    task["code"],
                    task["type"],
                ),
                content,
            )
    return buffer.getvalue()


@router.get("/export/zip")
def export_zip(
    _: Annotated[sqlite3.Row, Depends(active_user)],
    conn: Annotated[sqlite3.Connection, Depends(get_db)],
    pack_id: int,
) -> StreamingResponse:
    # LUÔN "submission.zip", không lấy theo nhãn vòng nữa. Ban tổ chức chỉ
    # quan tâm tên các file BÊN TRONG; tên gói ngoài mà đổi theo nhãn thì mỗi
    # lần tải lại ra một tên khác, và nhãn tiếng Việt còn từng làm hỏng cả
    # header (xem content_disposition).
    return StreamingResponse(
        io.BytesIO(build_zip(conn, pack_id)),
        media_type="application/zip",
        headers={"Content-Disposition": content_disposition(SUBMISSION_ZIP_NAME)},
    )
