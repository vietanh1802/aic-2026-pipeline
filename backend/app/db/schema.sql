-- Schema from the workspace redesign design, §4.
-- Applied on every API startup, so every statement is IF NOT EXISTS.

CREATE TABLE IF NOT EXISTS users (
  id                    INTEGER PRIMARY KEY,
  username              TEXT NOT NULL UNIQUE,
  display_name          TEXT NOT NULL,
  role                  TEXT NOT NULL DEFAULT 'member',   -- 'admin' | 'member'
  password_hash         TEXT NOT NULL,                    -- argon2id
  must_change_password  INTEGER NOT NULL DEFAULT 1,
  disabled              INTEGER NOT NULL DEFAULT 0,
  created_at            TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
  token       TEXT PRIMARY KEY,
  user_id     INTEGER NOT NULL REFERENCES users(id),
  created_at  TEXT NOT NULL,
  expires_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS packs (
  id               INTEGER PRIMARY KEY,
  round_label      TEXT NOT NULL,
  source_filename  TEXT NOT NULL,
  filename_pattern TEXT NOT NULL,      -- the regex the admin used at import time
  imported_by      INTEGER NOT NULL REFERENCES users(id),
  imported_at      TEXT NOT NULL,
  deadline_at      TEXT,               -- NULL = no countdown
  active           INTEGER NOT NULL DEFAULT 1
  -- `phase` KHÔNG khai báo ở đây, dù nó là cột thật. Xem migrations.py bước 4.
  --
  -- Cột thêm sau phải nằm ở đúng MỘT nơi. SQLite không có ALTER TABLE ADD
  -- COLUMN IF NOT EXISTS, nên khai ở cả hai chỗ thì CSDL mới toanh sẽ có sẵn
  -- cột từ file này rồi bước migration ném "duplicate column name" và chết
  -- ngay lúc khởi động. `answers.author_id` và `tasks.chosen_author_id` cũng
  -- vắng mặt ở đây vì đúng lý do đó.
);

CREATE TABLE IF NOT EXISTS tasks (
  id            INTEGER PRIMARY KEY,
  pack_id       INTEGER NOT NULL REFERENCES packs(id),
  code          TEXT NOT NULL,          -- '07'
  type          TEXT NOT NULL,          -- 'kis' | 'qa' | 'trake'
  query_text    TEXT NOT NULL,
  question_text TEXT,                   -- QA only
  n_events      INTEGER,                -- TRAKE only
  event_labels  TEXT,                   -- JSON ["Chạy đà","Giậm nhảy",…]
  owner_id      INTEGER REFERENCES users(id),
  claimed_at    TEXT,
  version       INTEGER NOT NULL DEFAULT 1,
  UNIQUE (pack_id, code)
);

-- sort_key is REAL on purpose (§4.1). Moving an answer from rank 40 to rank 1
-- with an integer rank column means renumbering 40 rows in a transaction; with
-- a float key it is the midpoint of two neighbours and one UPDATE. The
-- displayed rank is derived at read time with ROW_NUMBER() OVER (ORDER BY sort_key).
CREATE TABLE IF NOT EXISTS answers (
  id           INTEGER PRIMARY KEY,
  task_id      INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
  sort_key     REAL NOT NULL,
  video_id     TEXT NOT NULL,
  frames       TEXT NOT NULL,           -- JSON [25605] or [1102,1580,2043,2455]
  answer_text  TEXT,                    -- QA only
  origin       TEXT NOT NULL,           -- 'auto' | 'manual'
  created_by   INTEGER NOT NULL REFERENCES users(id),
  updated_by   INTEGER REFERENCES users(id),
  updated_at   TEXT NOT NULL,
  version      INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS idx_answers_task ON answers(task_id, sort_key);

CREATE TABLE IF NOT EXISTS presence (
  user_id       INTEGER PRIMARY KEY REFERENCES users(id),
  task_id       INTEGER REFERENCES tasks(id),
  last_seen_at  TEXT NOT NULL
);

-- Chỗ làm việc của mỗi người trên mỗi câu: câu truy vấn họ đang gõ, tham số
-- kèm theo, và khung hình họ vừa bấm vào.
--
-- Khác `presence` ở chỗ presence chỉ nói "đang mở câu nào" rồi hết hạn sau vài
-- chục giây. Bảng này KHÔNG hết hạn: nó tồn tại để người khác mở lại được thứ
-- bạn đã tìm ra, kể cả khi bạn đã đóng máy.
--
-- Khoá theo (user, task) chứ không riêng user: mỗi người có thể đã làm nhiều
-- câu, và xem lại câu 7 của bạn không nên bị mất chỉ vì bạn đã chuyển sang
-- câu 12.
CREATE TABLE IF NOT EXISTS search_states (
  user_id           INTEGER NOT NULL REFERENCES users(id),
  task_id           INTEGER NOT NULL REFERENCES tasks(id),
  query_text        TEXT NOT NULL DEFAULT '',
  search_type       TEXT NOT NULL DEFAULT 'ensemble',
  params            TEXT NOT NULL DEFAULT '{}',   -- JSON: topM, rerank, limit…
  picked_frame      TEXT,                         -- 'L21_V001-0028-3175.jpg'
  picked_video      TEXT,
  picked_frame_idx  INTEGER,
  updated_at        TEXT NOT NULL,
  PRIMARY KEY (user_id, task_id)
);
CREATE INDEX IF NOT EXISTS idx_search_states_task ON search_states(task_id);

-- Mọi lần tìm, giữ lại hết. search_states chỉ có MỘT dòng mỗi người mỗi câu và
-- bị đè mỗi lần search, nên truy vấn cũ biến mất ngay khi người đó gõ câu
-- khác — kể cả khi câu cũ mới là câu tìm ra đáp án.
--
-- Ghi thêm chứ không thay: search_states vẫn trả lời "ai đang tìm gì NGAY BÂY
-- GIỜ" cho dòng tóm tắt, còn bảng này trả lời "đã từng tìm bằng gì".
--
-- Một dòng cho mỗi TRUY VẤN khác nhau, không phải mỗi lần bấm. Bấm mười khung
-- trên cùng một truy vấn chỉ cập nhật khung đã chọn của dòng đó.
CREATE TABLE IF NOT EXISTS search_history (
  id                INTEGER PRIMARY KEY,
  user_id           INTEGER NOT NULL REFERENCES users(id),
  task_id           INTEGER NOT NULL REFERENCES tasks(id),
  query_text        TEXT NOT NULL DEFAULT '',
  search_type       TEXT NOT NULL DEFAULT 'ensemble',
  params            TEXT NOT NULL DEFAULT '{}',
  picked_frame      TEXT,
  picked_video      TEXT,
  picked_frame_idx  INTEGER,
  created_at        TEXT NOT NULL,
  updated_at        TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_search_history_task
  ON search_history(task_id, updated_at DESC);

CREATE TABLE IF NOT EXISTS settings (
  key    TEXT PRIMARY KEY,
  value  TEXT NOT NULL
);

-- Who did what. The round that "disappeared" was never deleted — it was
-- deactivated by the next import, and nothing recorded that, which is exactly
-- why nobody could answer "ai đã bấm gì". Every state change and every deletion
-- writes a row here.
--
-- `detail` carries the deleted rows themselves for the destructive actions, so
-- an admin can put them back. A hundred answers is a few KB of JSON.
-- `restored_at` is what stops one entry being restored twice.
CREATE TABLE IF NOT EXISTS audit_log (
  id           INTEGER PRIMARY KEY,
  at           TEXT NOT NULL,
  user_id      INTEGER NOT NULL REFERENCES users(id),
  action       TEXT NOT NULL,          -- 'pack.import' | 'pack.activate' | 'answers.clear' | ...
  target       TEXT NOT NULL,          -- 'pack:12' | 'task:47'
  summary      TEXT NOT NULL,          -- one line, already in the admin's language
  detail       TEXT,                   -- JSON payload; restorable rows live here
  restored_at  TEXT
);
CREATE INDEX IF NOT EXISTS idx_audit_at ON audit_log(at DESC, id DESC);
