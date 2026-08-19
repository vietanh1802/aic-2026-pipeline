# -*- coding: utf-8 -*-
"""Read an organizer query pack.

Every rule here was measured on sample-data/query-p1-groupA.zip rather than
assumed — see spec §5.2 for the five ways the real pack differs from the layout
the first importer was written against:

    .csv                        -> .txt
    codes zero-padded, dense    -> not padded, gaps are normal (no 3 in group A)
    line 0 is the query         -> KIS/Q&A: the whole file is, multi-line is normal
    Q&A question on its own line-> the last sentence of the paragraph
    TRAKE: one bare label a line-> optional context, then E1: … EN: prefixed lines

The filename regex is a parameter, not a constant, because the organizer has
not frozen the format. Changing the layout should be an admin editing one field,
not a rebuild.
"""
from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass, field

DEFAULT_PATTERN = r"query-(?P<phase>p\d+)-(?P<code>\d+)-(?P<type>kis|qa|trake)\.txt"

_EVENT = re.compile(r"^\s*E(\d+)\s*[:.]\s*(.*)$")


@dataclass
class ParsedTask:
    filename: str
    matched: bool
    error: str | None = None
    phase: str | None = None
    code: str | None = None
    type: str | None = None
    query_text: str = ""
    question_text: str | None = None
    n_events: int | None = None
    event_labels: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    lines: int = 0


def parse_member(filename: str, text: str, pattern: str) -> ParsedTask:
    match = re.fullmatch(pattern, filename)
    if match is None:
        return ParsedTask(
            filename=filename,
            matched=False,
            error="filename does not match the pattern",
        )

    groups = match.groupdict()
    task = ParsedTask(
        filename=filename,
        matched=True,
        phase=groups.get("phase"),
        code=groups.get("code"),
        type=groups.get("type"),
    )

    body = text.lstrip("﻿").strip()
    task.lines = len(body.splitlines())

    if task.type == "trake":
        _parse_trake(task, body)
    else:
        task.query_text = body
        if task.type == "qa":
            _parse_question(task, body)
    return task


def _parse_trake(task: ParsedTask, body: str) -> None:
    context: list[str] = []
    numbers: list[int] = []
    seen_event = False

    for line in body.splitlines():
        event = _EVENT.match(line)
        if event:
            seen_event = True
            numbers.append(int(event.group(1)))
            task.event_labels.append(event.group(2).strip())
        elif not seen_event and line.strip():
            context.append(line.strip())

    task.query_text = "\n".join(context)
    # Counted from how many event LINES there are, never from the highest E
    # number: query-p1-18-trake.txt carries E1, E2, E2, E4 — four events, a
    # duplicated number, and no E3.
    task.n_events = len(task.event_labels)

    if numbers != list(range(1, len(numbers) + 1)):
        listed = ", ".join(f"E{number}" for number in numbers)
        task.warnings.append(
            f"event numbers are not sequential ({listed}) — labels may be mismatched"
        )


def _parse_question(task: ParsedTask, body: str) -> None:
    # The question is the last sentence ending in '?', plus whatever trails it.
    # "Hỏi xã này có tên là gì? (tại thời điểm đó)" is one question, not a
    # question and a stray fragment.
    hits = list(re.finditer(r"[^.!?\n]*\?", body))
    if not hits:
        task.question_text = None
        task.warnings.append("no sentence ending in '?' was found")
        return
    task.question_text = body[hits[-1].start():].strip()


def parse_zip(data: bytes, pattern: str) -> list[ParsedTask]:
    """Parse every member of the archive, sorted by numeric code.

    Unmatched members are returned too, each carrying its reason, so the preview
    can list what it is skipping instead of dropping it silently.
    """
    tasks: list[ParsedTask] = []
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        for info in sorted(archive.infolist(), key=lambda i: i.filename):
            if info.is_dir():
                continue
            name = info.filename.rsplit("/", 1)[-1]
            if not name or name.startswith("."):
                continue
            tasks.append(
                parse_member(name, archive.read(info.filename).decode("utf-8"), pattern)
            )

    def order(task: ParsedTask) -> tuple[int, int, str]:
        if task.matched and task.code and task.code.isdigit():
            return (0, int(task.code), "")
        return (1, 0, task.filename)

    tasks.sort(key=order)
    return tasks
