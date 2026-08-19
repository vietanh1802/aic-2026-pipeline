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

import csv
import io
import json
import sqlite3
import zipfile
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.auth.deps import active_user
from app.db.connection import get_db
from app.routers._shared import answers, load_task, rows_per_query
from app.settings_store import all_settings

router = APIRouter(prefix="/api", tags=["export"])


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
    delimiter = str(settings.get("export.delimiter", ","))
    line_ending = "\r\n" if settings.get("export.line_ending") == "CRLF" else "\n"
    include_header = bool(settings.get("export.header", False))

    output = io.StringIO()
    writer = csv.writer(output, delimiter=delimiter, lineterminator=line_ending)

    if include_header:
        header = ["video_id", "frame"]
        if task["type"] == "qa":
            header.append("answer")
        elif task["type"] == "trake":
            header = ["video_id"] + [
                f"frame_{i + 1}" for i in range(int(task["n_events"] or 1))
            ]
        writer.writerow(header)

    for row in rows:
        frames = row["frames"]
        if task["type"] == "qa":
            writer.writerow(
                [row["video_id"], frames[0] if frames else "", row["answer_text"] or ""]
            )
        elif task["type"] == "trake":
            writer.writerow([row["video_id"], *frames])
        else:
            writer.writerow([row["video_id"], frames[0] if frames else ""])
    return output.getvalue()


def _task_source_filename(conn: sqlite3.Connection, task: sqlite3.Row) -> str:
    """Rebuild the input filename from the pack's pattern and the task's fields."""
    pack = conn.execute(
        "SELECT source_filename FROM packs WHERE id = ?", (task["pack_id"],)
    ).fetchone()
    if pack is None:
        return ""
    # The pack stores the archive name, not per-file names, so reconstruct the
    # member name the same way the importer read it.
    return f"query-p1-{task['code']}-{task['type']}.txt"


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
        rows = answers(conn, task["id"])

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
    rows = answers(conn, task_id)
    content = csv_content(settings, task, rows)
    return {
        "filename": export_filename(
            _task_source_filename(conn, task), settings, task["code"], task["type"]
        ),
        "rows": len(rows),
        "bytes": len(content.encode(str(settings.get("export.encoding", "utf-8")))),
        "content": content,
    }


@router.get("/export/zip")
def export_zip(
    _: Annotated[sqlite3.Row, Depends(active_user)],
    conn: Annotated[sqlite3.Connection, Depends(get_db)],
    pack_id: int,
) -> StreamingResponse:
    settings = all_settings(conn)
    pack = conn.execute("SELECT * FROM packs WHERE id = ?", (pack_id,)).fetchone()
    label = (pack["round_label"] if pack else "submission").replace(" ", "-")

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for task in conn.execute(
            "SELECT * FROM tasks WHERE pack_id = ? ORDER BY CAST(code AS INTEGER), code",
            (pack_id,),
        ):
            content = csv_content(settings, task, answers(conn, task["id"]))
            archive.writestr(
                export_filename(
                    _task_source_filename(conn, task),
                    settings,
                    task["code"],
                    task["type"],
                ),
                content,
            )
    buffer.seek(0)
    return StreamingResponse(
        buffer,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{label}.zip"'},
    )
