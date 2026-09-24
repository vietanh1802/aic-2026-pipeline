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
    (
        6,
        (
            # MỌI khung đã chốt trên một truy vấn, không phải khung cuối cùng.
            #
            # Ba cột picked_* là số ít, mà một lượt tìm thường chốt nhiều khung:
            # gõ một câu, bấm ba thẻ khác nhau trong lưới. Mỗi lần bấm lại ghi
            # đè lên lần trước, nên bảng lịch sử chỉ còn khung thứ ba — hai
            # khung đầu biến mất dù chúng đã nằm trong giỏ.
            #
            # JSON trong một cột chứ không phải bảng riêng: danh sách này luôn
            # được đọc trọn gói cùng dòng của nó, không ai truy vấn theo khung,
            # và một bảng nữa nghĩa là một JOIN nữa cho mỗi lần mở lịch sử.
            #
            # Ba cột cũ GIỮ NGUYÊN và vẫn mang khung mới nhất: chúng là thứ
            # search_states dùng chung hình dạng, và dòng lịch sử cũ chỉ có
            # chúng.
            "ALTER TABLE search_history ADD COLUMN picks TEXT NOT NULL "
            "DEFAULT '[]'",
        ),
    ),
    (
        7,
        (
            # Lượt đã khép. NULL = còn đang làm dở.
            #
            # Một mục lịch sử trước đây chỉ khép khi người dùng gõ truy vấn
            # khác. Nhưng cùng một truy vấn vẫn có thể là hai lượt tách bạch:
            # chốt ba khung, thấy sai cả ba, xoá sạch giỏ rồi chốt hai khung
            # khác. Không có cột này thì cả năm khung dồn vào một dòng, và
            # không đọc ra được rằng ba khung đầu đã bị chính người đó loại.
            #
            # Mốc khép là lúc GIỎ CẠN — xoá bằng nút "Xoá sạch" hay bấm x từng
            # dòng đều tính. Xoá một trong ba dòng thì không: giỏ còn hai, đó
            # là sửa sai chứ không phải làm lại.
            "ALTER TABLE search_history ADD COLUMN closed_at TEXT",
        ),
    ),
    (
        8,
        (
            # Retrieval Evaluation benchmark: score the translated visual
            # ensemble pipeline against manually reviewed Round 1 / Round 2
            # references. Six tables, added together because they are one
            # feature and none of them existed before this step.
            #
            # These are the reference SET tables and the RUN tables, kept
            # apart on purpose: a dataset + its reference set is seeded once
            # from a JSON file and never touched by a run, while runs and
            # their per-query results accumulate over time.
            "CREATE TABLE evaluation_datasets ("
            "  id               INTEGER PRIMARY KEY,"
            "  slug             TEXT NOT NULL,"
            "  version          TEXT NOT NULL,"
            "  display_name     TEXT NOT NULL,"
            "  query_count      INTEGER NOT NULL,"
            "  source_filename  TEXT,"
            # sha256 of the seed file, or of its canonicalised query list when
            # the file declares none — either way, re-seeding an edited file
            # is refused rather than silently merged.
            "  source_sha256    TEXT,"
            "  created_at       TEXT NOT NULL,"
            "  UNIQUE(slug, version)"
            ")",
            "CREATE TABLE evaluation_queries ("
            "  id          INTEGER PRIMARY KEY,"
            "  dataset_id  INTEGER NOT NULL REFERENCES evaluation_datasets(id) ON DELETE CASCADE,"
            "  query_key   TEXT NOT NULL,"           # 'p1-1', 'p2-16'
            "  ordinal     INTEGER NOT NULL,"
            "  task_type   TEXT NOT NULL,"           # 'KIS' | 'QA' | 'TRAKE'
            "  query_vi    TEXT NOT NULL,"
            "  UNIQUE(dataset_id, query_key)"
            ")",
            "CREATE TABLE evaluation_reference_sets ("
            "  id                   INTEGER PRIMARY KEY,"
            "  dataset_id           INTEGER NOT NULL REFERENCES evaluation_datasets(id) ON DELETE CASCADE,"
            "  version              TEXT NOT NULL,"
            "  label_semantics      TEXT NOT NULL,"
            "  interval_annotation  TEXT,"
            "  notes                TEXT,"
            "  created_at           TEXT NOT NULL,"
            "  UNIQUE(dataset_id, version)"
            ")",
            # One reference per (reference_set, query). valid_intervals_json is
            # a JSON list of {start,end} inclusive frame ranges — a query is a
            # hit when any candidate frame for the right video lands in any
            # listed interval. It is NULL only for TRAKE, which stays scored on
            # video ranking alone (Tier 0). reference_frame_idx is kept for
            # display and is just the first interval's start.
            "CREATE TABLE evaluation_references ("
            "  id                    INTEGER PRIMARY KEY,"
            "  reference_set_id      INTEGER NOT NULL REFERENCES evaluation_reference_sets(id) ON DELETE CASCADE,"
            "  query_id              INTEGER NOT NULL REFERENCES evaluation_queries(id) ON DELETE CASCADE,"
            "  video_id              TEXT NOT NULL,"
            "  valid_intervals_json  TEXT,"
            "  interval_count        INTEGER NOT NULL DEFAULT 0,"
            "  reference_frame_idx   INTEGER,"
            "  status                TEXT NOT NULL,"
            "  confidence            TEXT,"
            "  provenance            TEXT,"
            "  notes                 TEXT NOT NULL DEFAULT '',"
            "  qa_answer             TEXT,"           # QA reference answer — stored, never scored
            "  trake_events_json     TEXT,"           # TRAKE events — descriptive only, never scored
            "  UNIQUE(reference_set_id, query_id)"
            ")",
            # A run is one (dataset, reference_set) scored under one translation
            # policy and model config. summary_json is the blended headline;
            # task_type_summary_json breaks the same run out by KIS / QA / TRAKE,
            # which now matters because their scoring semantics differ.
            "CREATE TABLE evaluation_runs ("
            "  id                       INTEGER PRIMARY KEY,"
            "  dataset_id               INTEGER NOT NULL REFERENCES evaluation_datasets(id) ON DELETE CASCADE,"
            "  reference_set_id         INTEGER NOT NULL REFERENCES evaluation_reference_sets(id) ON DELETE CASCADE,"
            "  strategy                 TEXT NOT NULL,"
            "  video_ranking_policy     TEXT NOT NULL,"
            "  interval_scoring_policy  TEXT NOT NULL,"
            "  translator               TEXT NOT NULL,"
            "  status                   TEXT NOT NULL,"
            "  query_count              INTEGER NOT NULL,"
            "  completed_count          INTEGER NOT NULL DEFAULT 0,"
            "  failed_count             INTEGER NOT NULL DEFAULT 0,"
            "  created_by_user_id       INTEGER,"
            "  configuration_json       TEXT NOT NULL,"
            "  runtime_json             TEXT,"
            "  summary_json             TEXT,"
            "  task_type_summary_json   TEXT,"
            "  error                    TEXT,"
            "  created_at               TEXT NOT NULL,"
            "  started_at               TEXT,"
            "  finished_at              TEXT,"
            "  updated_at               TEXT NOT NULL,"
            "  resume_count             INTEGER NOT NULL DEFAULT 0"
            ")",
            # reference_intervals_json / reference_notes are frozen copies taken
            # at run creation, so a later edit to the reference set cannot change
            # what a past run was scored against. interval_rank is the smallest
            # submitted rank whose frame is a correct-video-in-interval hit;
            # every R@k and final_score for KIS/QA derives from it. All the
            # interval_* columns are NULL for TRAKE.
            "CREATE TABLE evaluation_query_results ("
            "  id                       INTEGER PRIMARY KEY,"
            "  run_id                   INTEGER NOT NULL REFERENCES evaluation_runs(id) ON DELETE CASCADE,"
            "  query_id                 INTEGER NOT NULL REFERENCES evaluation_queries(id) ON DELETE CASCADE,"
            "  query_key                TEXT NOT NULL,"
            "  ordinal                  INTEGER NOT NULL,"
            "  task_type                TEXT NOT NULL,"
            "  status                   TEXT NOT NULL,"
            "  query_vi                 TEXT NOT NULL,"
            "  query_en                 TEXT,"
            "  translator               TEXT NOT NULL,"
            "  reference_video          TEXT NOT NULL,"
            "  reference_intervals_json TEXT,"
            "  reference_frame_idx      INTEGER,"
            "  reference_notes          TEXT NOT NULL DEFAULT '',"
            "  predicted_top1_video     TEXT,"
            "  reference_video_rank     INTEGER,"
            "  hit_at_1                 INTEGER,"
            "  hit_at_3                 INTEGER,"
            "  hit_at_5                 INTEGER,"
            "  hit_at_10                INTEGER,"
            "  reciprocal_rank          REAL,"
            "  not_retrieved            INTEGER,"
            "  interval_hit             INTEGER,"
            "  interval_rank            INTEGER,"
            "  matched_interval_index   INTEGER,"
            "  final_score              REAL,"
            "  translation_ms           REAL,"
            "  retrieval_ms             REAL,"
            "  aggregation_ms           REAL,"
            "  total_ms                 REAL,"
            "  frame_results_json       TEXT,"
            "  ranked_videos_json       TEXT,"
            "  error                    TEXT,"
            "  started_at               TEXT,"
            "  finished_at              TEXT,"
            "  UNIQUE(run_id, query_id)"
            ")",
            "CREATE INDEX idx_evaluation_runs_status "
            "ON evaluation_runs(status)",
            "CREATE INDEX idx_evaluation_query_results_run "
            "ON evaluation_query_results(run_id, ordinal)",
        ),
    ),
    (
        9,
        (
            # Nộp bài vòng chung kết lên DRES (app/dres.py).
            #
            # dres_config chỉ có MỘT dòng (id = 1): cả đội dùng chung một tài
            # khoản DRES. Mật khẩu lưu dạng rõ vì server phải tự đăng nhập lại
            # khi phiên DRES hết hạn giữa buổi thi; nó không bao giờ được trả ra
            # qua API. Bảng riêng chứ không nhét vào `settings`: settings là
            # danh sách khoá có kiểu, đọc được một phần từ trình duyệt thành
            # viên, không phải chỗ để bí mật.
            "CREATE TABLE dres_config ("
            "  id               INTEGER PRIMARY KEY CHECK (id = 1),"
            "  base_url         TEXT NOT NULL,"
            "  username         TEXT NOT NULL,"
            "  password         TEXT NOT NULL,"
            "  session_id       TEXT,"
            "  evaluation_id    TEXT,"
            "  evaluation_name  TEXT,"
            # Ai được bấm gửi lên DRES: 'admin_only' (mặc định — thành viên đề
            # xuất, admin duyệt) hoặc 'everyone' (ai tìm ra thì người đó nộp
            # luôn, nhanh hơn vài giây mỗi câu). Admin đổi trên tab DRES.
            "  submit_mode      TEXT NOT NULL DEFAULT 'admin_only'"
            "                   CHECK (submit_mode IN ('admin_only', 'everyone')),"
            "  updated_by       INTEGER REFERENCES users(id),"
            "  updated_at       TEXT NOT NULL"
            ")",
            # Mỗi đề xuất nộp là một dòng, kể cả khi bị từ chối: nộp sai trừ 10
            # điểm, nên phải trả lời được "ai đề xuất, ai duyệt, gửi đúng chuỗi
            # gì, DRES trả gì". payload là JSON gửi đi NGUYÊN VĂN — thứ admin
            # thấy trong hộp xác nhận cũng là thứ đi ra mạng.
            #
            # status: proposed → sending → sent | failed ; proposed → rejected.
            # 'sending' là khoá: chỉ một lần duyệt chiếm được dòng, nên bấm đúp
            # hay hai admin cùng bấm không thành hai lần nộp (hai lần trừ điểm).
            "CREATE TABLE dres_submissions ("
            "  id               INTEGER PRIMARY KEY,"
            "  created_at       TEXT NOT NULL,"
            "  proposed_by      INTEGER NOT NULL REFERENCES users(id),"
            "  task_type        TEXT NOT NULL,"
            "  video_id         TEXT NOT NULL,"
            "  frames           TEXT NOT NULL,"
            "  times_ms         TEXT NOT NULL,"
            "  answer_text      TEXT,"
            "  evaluation_id    TEXT NOT NULL,"
            "  dres_task_name   TEXT,"
            "  payload          TEXT NOT NULL,"
            "  status           TEXT NOT NULL,"
            "  reviewed_by      INTEGER REFERENCES users(id),"
            "  reviewed_at      TEXT,"
            "  verdict          TEXT,"
            "  dres_description TEXT,"
            "  http_status      INTEGER,"
            "  error            TEXT"
            ")",
            "CREATE INDEX idx_dres_submissions_created "
            "ON dres_submissions(created_at DESC, id DESC)",
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
