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
