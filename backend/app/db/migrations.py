"""Numbered schema steps, applied on top of schema.sql.

schema.sql is the baseline and is deliberately all IF NOT EXISTS, which is also
exactly why it cannot add a column to a table that already exists: the CREATE
is skipped and the new column never appears. That is what this file is for.

`PRAGMA user_version` records how far a database has been taken. Each step runs
at most once, in order, in its own transaction, so a step that fails halfway
leaves the version behind it rather than a half-migrated table.

migrate.py's original note said versioning should arrive the moment a column has
to change shape rather than before. `packs.deleted_at` is that moment.
"""
from __future__ import annotations

import sqlite3

# (version, statements). Never renumber and never edit a shipped step — a
# database that already ran step 1 will not run it again, so changing it only
# splits new deployments from old ones. Add a new step instead.
STEPS: tuple[tuple[int, tuple[str, ...]], ...] = (
    (
        1,
        (
            # Soft delete, for two reasons. A hard DELETE cannot work as-is:
            # tasks.pack_id and presence.task_id carry no ON DELETE CASCADE, so
            # removing a pack mid-round raises a foreign key error. And for a
            # tool whose actual complaint was losing a round's work,
            # unrecoverable deletion is the wrong direction to build in.
            "ALTER TABLE packs ADD COLUMN deleted_at TEXT",
        ),
    ),
    (
        2,
        (
            # Mỗi người một danh sách riêng cho mỗi câu.
            #
            # Trước đây một task có MỘT danh sách xếp hạng dùng chung, cộng với
            # owner_id để giành quyền sửa ("Nhận"/"Nhả"). Cách đó buộc cả nhóm
            # phải chờ nhau: một câu chỉ một người làm được, và ai vào sau thì
            # sửa đè lên danh sách của người trước.
            #
            # answers.author_id là CHỦ CỦA DANH SÁCH, khác created_by (người tạo
            # ra đúng dòng đó). Hai cái trùng nhau ở mọi dòng hiện có, nhưng
            # tách ra thì sau này admin sửa hộ một dòng trong danh sách của
            # người khác mà danh sách vẫn thuộc về người kia.
            "ALTER TABLE answers ADD COLUMN author_id INTEGER REFERENCES users(id)",
            "UPDATE answers SET author_id = created_by WHERE author_id IS NULL",
            # Xếp hạng giờ tính trong phạm vi (task, tác giả), nên chỉ mục cũ
            # theo (task_id, sort_key) không còn phục vụ được truy vấn chính.
            "CREATE INDEX IF NOT EXISTS idx_answers_task_author "
            "ON answers(task_id, author_id, sort_key)",

            # Bài nộp vẫn là MỘT danh sách mỗi câu. Đây là người được chọn cho
            # câu đó. NULL = chưa chọn ai, và lúc xuất sẽ báo thiếu chứ không
            # tự đoán.
            "ALTER TABLE tasks ADD COLUMN chosen_author_id INTEGER REFERENCES users(id)",

            # owner_id và claimed_at KHÔNG bị xoá. Xoá cột trong SQLite là dựng
            # lại cả bảng, mà dữ liệu đó là bằng chứng ai từng giành câu nào —
            # còn giá trị khi lần lại lịch sử. Chỉ ngừng dùng.
        ),
    ),
    (
        3,
        (
            # Xem lại người khác đã tìm bằng gì.
            #
            # schema.sql cũng có bảng này, nhưng schema.sql toàn IF NOT EXISTS
            # và chỉ chạy trên CSDL mới — bước này là cho những CSDL đã tồn tại.
            # Giữ hai bản GIỐNG HỆT nhau; lệch một cột là hai máy chạy hai lược
            # đồ khác nhau mà không ai biết.
            "CREATE TABLE IF NOT EXISTS search_states ("
            "  user_id           INTEGER NOT NULL REFERENCES users(id),"
            "  task_id           INTEGER NOT NULL REFERENCES tasks(id),"
            "  query_text        TEXT NOT NULL DEFAULT '',"
            "  search_type       TEXT NOT NULL DEFAULT 'ensemble',"
            "  params            TEXT NOT NULL DEFAULT '{}',"
            "  picked_frame      TEXT,"
            "  picked_video      TEXT,"
            "  picked_frame_idx  INTEGER,"
            "  updated_at        TEXT NOT NULL,"
            "  PRIMARY KEY (user_id, task_id)"
            ")",
            "CREATE INDEX IF NOT EXISTS idx_search_states_task "
            "ON search_states(task_id)",
        ),
    ),
    (
        4,
        (
            # Số vòng trong TÊN FILE của ban tổ chức: 'p1', 'p2', 'p3'.
            #
            # Trước bước này export luôn sinh `query-p1-…` vì chuỗi "p1" bị
            # viết cứng trong mã. Trình đọc gói vẫn tách được số vòng từ tên
            # file nhưng không có chỗ nào để cất, nên một gói `query-p2-…` xuất
            # ra vẫn mang tên p1 — sai tên file nộp, không cảnh báo, và chỉ
            # phát hiện khi bài đã bị chấm hỏng.
            #
            # NULL với các gói nhập trước đây; export rơi về 'p1' như cũ, và màn
            # Export cho sửa tay.
            "ALTER TABLE packs ADD COLUMN phase TEXT",
        ),
    ),
    (
        5,
        (
            # Lịch sử tìm kiếm: mọi truy vấn đã từng gõ cho một câu.
            #
            # search_states chỉ giữ một dòng mỗi người mỗi câu và bị đè mỗi lần
            # search. Đồng đội bấm "Coi X làm" chỉ xem được truy vấn X đang gõ
            # ngay lúc đó; X gõ câu khác là câu cũ mất hẳn, kể cả khi chính câu
            # cũ mới là câu tìm ra đáp án.
            "CREATE TABLE IF NOT EXISTS search_history ("
            "  id                INTEGER PRIMARY KEY,"
            "  user_id           INTEGER NOT NULL REFERENCES users(id),"
            "  task_id           INTEGER NOT NULL REFERENCES tasks(id),"
            "  query_text        TEXT NOT NULL DEFAULT '',"
            "  search_type       TEXT NOT NULL DEFAULT 'ensemble',"
            "  params            TEXT NOT NULL DEFAULT '{}',"
            "  picked_frame      TEXT,"
            "  picked_video      TEXT,"
            "  picked_frame_idx  INTEGER,"
            "  created_at        TEXT NOT NULL,"
            "  updated_at        TEXT NOT NULL"
            ")",
            "CREATE INDEX IF NOT EXISTS idx_search_history_task "
            "ON search_history(task_id, updated_at DESC)",
        ),
    ),
)


def current_version(conn: sqlite3.Connection) -> int:
    return int(conn.execute("PRAGMA user_version").fetchone()[0])


def apply_steps(conn: sqlite3.Connection) -> int:
    """Run every step this database has not seen. Returns the version reached."""
    version = current_version(conn)
    for step_version, statements in STEPS:
        if step_version <= version:
            continue
        conn.execute("BEGIN IMMEDIATE")
        try:
            for statement in statements:
                conn.execute(statement)
            # PRAGMA takes no bound parameters, so this is interpolated. The
            # value is an int from the tuple above, never from a request.
            conn.execute(f"PRAGMA user_version = {int(step_version)}")
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
        version = step_version
    return version
