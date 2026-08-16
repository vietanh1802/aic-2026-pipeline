# Staging — collaboration, query import, submission export

2026-08-16 · AIC 2026 · branch `staging` (forked from `ensemble-search` at `288986e`)

A software requirements specification for the work that turns the working ensemble search
prototype into a tool five people can compete with.

**Source of requirements:** `dev` branch —
`docs/superpowers/specs/2026-08-09-workspace-collab-redesign-design.md` (Vietnamese, the
approved redesign) and `docs/superpowers/specs/2026-08-10-ux-flow-and-business-logic.md`
(the screen-by-screen wiring). Where this document and those disagree about *what* to
build, they win. Where they disagree with the **real organizer files** now in
`sample-data/`, this document wins — §5 explains each divergence and why.

**Language:** English throughout — code, UI, comments, docs. The single exception is
organizer query text, which is Vietnamese and is stored and displayed **verbatim, never
translated**.

---

## 1. Purpose and scope

### 1.1 The problem

`ensemble-search` retrieves well and cannot compete. It has a search box, a results grid,
and nowhere to put an answer. Five people working one round on it would coordinate over
chat, keep their candidate lists in browser memory that `F5` erases, and hand-assemble a
submission file that nothing verifies.

### 1.2 What this specification covers

| In scope | Out of scope |
| --- | --- |
| Accounts, login, admin-managed members | Self-registration, password recovery |
| Importing the organizer's query pack | Automatic download of the pack |
| Task board: claim, release, presence | WebSocket transport (polling, with the upgrade seam) |
| Workspace: search → results grid → 100-row answer basket | Changing what search returns |
| Submission export: validate → preview → zip | Automatic upload to the organizer |
| Pin-frame: exact integer frame selection | Video download cache, real frame decoding |
| Rebuilding the UI to the approved 3-column workspace | The lexical BM25 route, `/temporal-search` UI |

### 1.3 Definitions

| Term | Meaning |
| --- | --- |
| **Task** | One organizer query. Has a code, a type, the Vietnamese query text, and an owner. |
| **Answer** | One submitted row: a `video_id` plus one frame (KIS/Q&A) or N frames (TRAKE). |
| **Basket** | The ordered list of up to 100 answers for one task. Row order **is** the score. |
| **Pack** | One organizer archive of query files, imported as a set of tasks. |
| **Core** | `backend/app/preprocess.py` — index loading, encoding, FAISS search, rerank, ensemble. |
| **R@k** | `max` R-Score over the first `k` answers, `k ∈ {1,5,20,50,100}`. |

---

## 2. Baseline — what exists on 2026-08-16

### 2.1 Backend (`staging`, inherited from `ensemble-search`)

| Component | State |
| --- | --- |
| `app/preprocess.py` (751 lines) | BEiT3 + OpenCLIP, two FAISS indexes, per-model neighbour rerank (Alg.2), weighted ensemble (Alg.3), `temporal_search` (Alg.4). `ACTIVE_MODELS` env gate. `_has_image()` per result. **No demo mode** — it was removed on this branch. |
| `app/main.py` (255 lines) | `/ensemble-search`, `/single-search`, `/temporal-search`, `/status`, `/health`, static image mount, permissive CORS. |
| `app/__init__.py` | Loads `backend/.env` before any submodule reads `AIC_*`. |
| Persistence | **None.** No database, no users, no tasks. |
| Indexes on disk | `beit3.index`, `clip.index`, `beit3_mapping.json`, `clip_mapping.json`, `keyframe_metadata.json` present. 35,481 keyframe images in `app/static/images/`. |

### 2.2 Frontend (`staging`)

One screen. `App.tsx` → `QueryInput` + `FrameDisplay` + `VideoPopUp`, three Zustand stores,
all in memory. Known defects carried from the pre-redesign code:

| Defect | Location | Consequence |
| --- | --- | --- |
| Frame number re-derived from filename as milliseconds | `App.tsx:141-142`, `:175-176` | Frame 25605 seeks to second 25.6 instead of second 853. Wrong by 25–30×, while the correct `frame_idx` is already in the response. |
| Tile colour computed from `distance` | `FrameDisplay/index.tsx:55-92` | Every tile is green because every distance is high. Tells the user nothing. |
| `routes` present in every response, used nowhere | — | The one signal that separates a two-model agreement from a one-model guess is discarded. |
| Google OAuth client id + two API keys hardcoded | `SubmitForm/index.tsx:16,17`, `VideoPopUp/VideoDisplay.tsx:30` | Committed to git history. Must be treated as leaked and revoked. |
| `react-csv` imported, never rendered | `SubmitForm/index.tsx:11` | There has never been a CSV export. |
| Submission list in memory only | `store/submitStore.ts` | `F5` loses the round's work. |

### 2.3 The `dev` branch

Carries a working prototype of nearly everything this document specifies: SQLite schema,
argon2id auth, admin members and settings, task board with atomic claim, presence, the
answer basket with optimistic-concurrency `version` checks, autofill, pack import with a
regex preview, CSV/ZIP export, and `frameMath.ts`. It also carries the approved hi-fi
mockups at `.superpowers/brainstorm/1877-1786204313/content/workspace-hifi-v3.html`.

Its weakness is that its import parser and its exporter were written against a **guessed**
format. §5 replaces both guesses with the real ones.

---

## 3. Constraints and invariants

These are not preferences. A change that violates one of them is a defect regardless of
what else it improves.

### INV-1 — The retrieval core does not change

`backend/app/preprocess.py` is frozen. No edits to encoding, index loading, `_search_one`,
`rerank_one_model`, `_merge_ensemble`, `ensemble_search`, `single_model_search`, or
`temporal_search`. Search parameters (`limit`, `top_m`, `use_rerank`, `AIC_MODELS`) keep
their current defaults and meanings.

Enforcement is a test, not a promise — see **TST-1** in §10.

### INV-2 — A frame number is passed through or computed, never re-derived

Two legal origins:

1. **Pass-through.** A search result carries an exact `frame_idx`. Accepting the result
   submits that integer untouched.
2. **Computed from a player clock.** `floor(fps · t + offset)`, with the calibration in
   force displayed next to the number.

Banned: deriving a frame from a filename, multiplying `seconds × fps` ad hoc, and snapping
a computed frame to the nearest keyframe. Keyframes sit ~3.5 s apart; a scoring window is
far narrower, so snapping submits a confident answer that scores zero.

### INV-3 — Nothing important lives only in the browser

Every answer, every claim, every ordering change goes to the server before it is considered
real. The browser may hold the auth token, UI state, and one integer `frameIdx`.

### INV-4 — Organizer query text is never translated

Stored and rendered verbatim. A translation helper may exist for the *user's* search query;
it must never write back to `tasks.query_text`.

### INV-5 — Concurrency is resolved in the database, not the client

Claiming is one conditional `UPDATE`. Editing an answer carries the `version` the client
last saw. A lost race produces `409` and a user-facing choice — never a silent overwrite.

### INV-6 — Secrets never enter source

The three leaked Google credentials are removed in S0 and must be revoked in Google Cloud
Console independently, because deleting them from the working tree does not delete them
from history.

---

## 4. Functional requirements

Numbered for traceability. The **Why** column cites the scoring rule or defect that forces
the requirement, so nothing here is decoration.

### 4.1 Identity and administration

| ID | Requirement | Why |
| --- | --- | --- |
| FR-1.1 | Members sign in with username + password. Wrong username and wrong password return the **same** message. | Distinguishing them turns the form into a username directory. |
| FR-1.2 | Passwords are stored argon2id. Plaintext appears exactly once, in the creation response. | A "resend credentials" endpoint would mean the server kept the plaintext. |
| FR-1.3 | A first login forces a password change; until it is done the API answers `403` to everything except `/api/me`. | The generated password travelled through a chat app. |
| FR-1.4 | An admin bulk-creates members and downloads the credential list as client-built CSV with a BOM. | Excel needs the BOM to render Vietnamese display names. |
| FR-1.5 | An admin can reset a password, rename, and disable a member. | Round-day recovery without database access. |
| FR-1.6 | An admin edits the settings in §7.4. | Format changes become a form field, not a rebuild. |

### 4.2 Query import

| ID | Requirement | Why |
| --- | --- | --- |
| FR-2.1 | An admin uploads the organizer ZIP (`multipart/form-data`) and sees a per-file preview before anything is written. | An import that silently drops files is discovered at export time. |
| FR-2.2 | The filename rule is an admin-supplied regex with named groups, pre-filled with the real pattern. | The organizer changed the layout between our guess and the real file once already. |
| FR-2.3 | The preview shows, per file: matched or not, code, type, query text, inferred Q&A question, TRAKE event labels, and any warning. | §5.2 lists three ways a real file can be structurally odd. |
| FR-2.4 | The inferred Q&A question is **editable in the preview**. | Inference from punctuation is right most of the time, and the human is already looking at it. |
| FR-2.5 | A TRAKE file with duplicate or non-sequential `E` numbers imports with the correct event *count* and raises a warning. | `query-p1-18-trake.txt` ships two `E2:` and no `E3:`. |
| FR-2.6 | Commit creates one task per matched file and reports created and skipped counts. | |
| FR-2.7 | Re-importing the same pack does not duplicate tasks. | `UNIQUE (pack_id, code)`. |

### 4.3 Search inside a task

| ID | Requirement | Why |
| --- | --- | --- |
| FR-3.1 | `POST /api/search` accepts `task_id` and delegates to the unchanged `ensemble_search()` / `single_model_search()`. | INV-1. |
| FR-3.2 | `frame_idx` and `routes` pass through the API untouched. | INV-2, and `routes` drives tile colour. |
| FR-3.3 | A result tile is coloured by **model agreement**: both models found it, or one did. Not by distance. | Distance colouring paints every tile green. |
| FR-3.4 | The last search per `(user_id, task_id)` is retained in process memory for 30 minutes to serve autofill. | Losing it costs one re-search; a database write costs a schema. |
| FR-3.5 | A tile shows its basket position when present, and the name of a teammate who already saved it. | Stops two people verifying the same frame. |

### 4.4 The answer basket

| ID | Requirement | Why |
| --- | --- | --- |
| FR-4.1 | A task holds up to `export.rows_per_query` (default 100) ordered answers, persisted server-side. | INV-3. |
| FR-4.2 | Autofill takes the last search's results and fills the basket to the limit. `append` keeps existing rows; `replace_auto` replaces only `origin=auto` rows. | `R@k` is a `max`: an extra answer can never lower a score, so an empty row 51–100 is a discarded point. |
| FR-4.3 | Any row is editable and re-orderable. Reordering is one `UPDATE` on a `REAL` sort key. | Dragging rank 40 to rank 1 must not renumber 40 rows mid-round. |
| FR-4.4 | The basket draws the five boundaries `R@1 / R@5 / R@20 / R@50 / R@100` between rows. | Rank 7 → 6 gains nothing; 6 → 5 gains 20%. Nobody computes that under a clock. |
| FR-4.5 | Row origin is visible: verified by me, added by a teammate, or auto-filled. | |
| FR-4.6 | `PATCH` carries `version`; a lost race returns `409` with the current row and the UI asks which version to keep. | INV-5. |
| FR-4.7 | KIS rows carry one frame; Q&A rows add an answer text that can be applied to all rows or empty rows only; TRAKE rows carry N frames labelled with the event names. | Three different submission shapes. |
| FR-4.8 | A TRAKE row missing an event is flagged, never silently dropped, and the UI warns that a wrong `video_id` scores zero for the whole row. | Partial events still score `1/N` each; a wrong video scores nothing. |
| FR-4.9 | The system never caps how many rows a user may verify by hand. | "Verify the top 5" is tactical advice, not a rule software should enforce. |

### 4.5 Collaboration

| ID | Requirement | Why |
| --- | --- | --- |
| FR-5.1 | Claiming is `UPDATE tasks SET owner_id=:me … WHERE id=:id AND owner_id IS NULL`. `rowcount=1` wins; `rowcount=0` returns `409` with the current owner. | Never `SELECT`-then-`IF`. |
| FR-5.2 | The client updates optimistically and rolls back with a toast naming the winner on `409`. | Own actions must feel instant; only watching teammates may lag. |
| FR-5.3 | Presence heartbeat every 10 s; silent for 30 s means offline. | |
| FR-5.4 | An offline owner's task is **not** auto-released; the row warns, and an admin can force-release. | A one-minute network drop is not abandonment. |
| FR-5.5 | Board data is polled every 3 s through exactly one hook, `useBoard()`. | A dead WebSocket shows stale data that looks live. One hook keeps the upgrade to one file. |

### 4.6 Export

| ID | Requirement | Why |
| --- | --- | --- |
| FR-6.1 | `validate` reports per-task issues: empty Q&A answers, TRAKE rows with missing events, duplicate rows, tasks with zero answers. | |
| FR-6.2 | `preview` returns the exact bytes of one task's file. | A preview that renders rather than shows bytes hides the failure this is meant to catch. |
| FR-6.3 | `zip` returns one flat archive, one file per task, **including tasks with zero answers**. | An empty file says "we had nothing". A missing file is indistinguishable from a packaging bug. |
| FR-6.4 | Row order in the file is basket order. | Row order is the score. |
| FR-6.5 | Fields are CSV-quoted per RFC 4180 when they contain the delimiter, a quote, or a newline. | A real 2025 Q&A answer contains a comma: `"Hoả hồng Nhật Tảo oanh thiên địa, Kiếm bạch Kiên Giang khấp quỷ thần."` |
| FR-6.6 | Delimiter, header, line ending, encoding, filename pattern and row limit are settings. Default encoding emits **no BOM**. | If the organizer's parser does not strip a BOM, the first field of the first row is corrupt in every file and nothing on our side looks wrong. |

### 4.7 Frame selection

| ID | Requirement | Why |
| --- | --- | --- |
| FR-7.1 | Pin-frame state is one integer `frameIdx` plus the video's `fps` and `offset`. | |
| FR-7.2 | Transport `−10 / −1 / [number] / +1 / +10`, the number directly typeable, any integer reachable, no snapping. | TRAKE windows are "usually under 10 frames" — under 0.4 s at 25 fps. No slider hits that. |
| FR-7.3 | Frame, timecode, fps in use, offset in use, and whether the position was confirmed against a thumbnail are all on screen. | A number produced under a corrected fps must never look identical to one produced under the nominal table. |
| FR-7.4 | Seeks target the frame midpoint `(f + 0.5 − offset) / fps`. | A seek rounded the wrong way still lands on the requested frame. |

---

## 5. Data formats — measured, not assumed

### 5.1 Evidence

`sample-data/query-p1-groupA.zip` is a real organizer pack: 24 `.txt` files, UTF-8, no BOM,
LF, some without a trailing newline. Cross-referencing `docs/Danh_gia_Query_AIC2025.md`
shows it is the **AIC 2025 Round 1** query set, and that document carries the ground-truth
answer for all 89 queries of that season in the exact submitted row shape.

This resolves `COMPETITION-UNKNOWNS.md` U2 (pack layout) and gives the export format
concrete evidence. Both are recorded here; §12 lists what remains open.

### 5.2 Import — the real pack

```
query-p1-groupA.zip
├── query-p1-1-kis.txt
├── query-p1-2-kis.txt
├── query-p1-4-trake.txt
├── query-p1-15-qa.txt
└── … 24 files, no file 3
```

Default pattern: `query-(?<phase>p\d+)-(?<code>\d+)-(?<type>kis|qa|trake)\.txt`

Five differences from the provisional template in `dev`'s `docs/DATA-FORMATS.md`, each of
which would have caused a wrong or empty import:

| Provisional guess | Reality |
| --- | --- |
| `.csv` | `.txt` |
| `code` zero-padded, contiguous | not padded, gaps are normal (no `3` in group A) |
| line 0 is the query, later lines are events | KIS/Q&A: the **whole file** is the query, multi-line is normal (7 of 24 files) |
| Q&A question on its own trailing line | Q&A question is the **last sentence of the paragraph** |
| TRAKE: one bare label per line | TRAKE: optional context line, then `E1:` … `EN:` prefixed lines |

Parsing rules, by type:

- **KIS** — `query_text` is the whole file, whitespace-trimmed at both ends, internal line
  breaks preserved.
- **Q&A** — `query_text` is the whole file. `question_text` is inferred as the last
  sentence ending in `?`; if none is found, `question_text` is null and the preview says so.
  The field is editable before commit (FR-2.4).
- **TRAKE** — lines matching `^\s*E\d+\s*[:.]` are events **in file order**. `n_events` is
  their count. Any line before the first event line is context and joins `query_text`.
  Event labels are the text after the colon.
  `n_events` is never taken from the highest `E` number: `query-p1-18-trake.txt` contains
  `E1, E2, E2, E4` — four events, a duplicate label number, and no `E3`. The importer
  produces four events and raises `warning: event numbers are not sequential (E1, E2, E2,
  E4) — labels may be mismatched`.

Unmatched files are listed with a reason and skipped, never imported silently.

`dev`'s design carried a second import knob, `query_source` (`whole_file` / `column:0` /
`column_name:query`), for picking the query out of a CSV column. The real files are plain
text with no columns, so the knob has nothing to select and is dropped. The regex stays —
that is the knob a layout change actually needs.

### 5.3 Export — the submission file

Row shapes, confirmed against the 2025 ground truth:

```
KIS     L21_V015,25605
Q&A     L30_V072,1745,Xã Giang Ly
Q&A     L27_V010,5550,"Hoả hồng Nhật Tảo oanh thiên địa, Kiếm bạch Kiên Giang khấp quỷ thần."
TRAKE   L26_V194,4707,5100,5425,5850
```

| Property | Default | Setting key |
| --- | --- | --- |
| One file per task, flat zip | — | — |
| Filename | `query-{phase}-{code}-{type}.csv` | `export.filename_pattern` |
| Header row | none | `export.header` |
| Delimiter | `,` | `export.delimiter` |
| Quoting | RFC 4180, minimal | — |
| Line ending | `LF` | `export.line_ending` |
| Encoding | `utf-8`, **no BOM** | `export.encoding` |
| Rows per file | 100 | `export.rows_per_query` |

The output filename reuses the input stem and changes only the extension —
`query-p1-15-qa.txt` in, `query-p1-15-qa.csv` out — so a reviewer can line the two up.
Every task in the pack gets a file.

The extension and the per-task-file layout are the two parts of §5.3 with no direct
evidence behind them: the 2025 record confirms the **rows**, not the packaging. Both are
settings, and R-2 in §12 tracks them as open.

---

## 6. Architecture

### 6.1 Component layout

```
staging/
├─ backend/app/
│   ├─ preprocess.py          FROZEN (INV-1) — pinned by TST-1
│   ├─ search_core.py         NEW · the only module that calls preprocess
│   ├─ config.py              PORT · the only module allowed to read os.environ
│   ├─ guard.py               PORT · production refuses to start when misconfigured
│   ├─ db/{connection,migrate,backup}.py + schema.sql    PORT
│   ├─ auth/{passwords,sessions,deps,bootstrap}.py       PORT
│   ├─ settings_store.py      PORT
│   ├─ packs_store.py         NEW · §5.2 parser
│   ├─ export_store.py        NEW · §5.3 writer
│   └─ routers/
│        auth · admin_users · admin_packs · admin_settings ·
│        board · search · answers · export
└─ frontend/src/
    ├─ api/{base,auth,admin,packs,board,search,answers,export}.ts
    ├─ store/{authStore,workspaceStore}.ts
    ├─ hooks/{useBoard,useAnswers}.ts
    ├─ pages/{Login,ChangePassword,AdminMembers,AdminPacks,AdminSettings,Board,Workspace,Export}.tsx
    └─ components/workspace/{TaskRail,ResultGrid,PinFrame,AnswerBasket}.tsx
```

### 6.2 The one seam that needs design

`dev`'s ported modules import `DEMO_MODE` from `preprocess.py`. This branch deleted demo
mode deliberately. Editing `preprocess.py` to re-add it would violate INV-1.

**Resolution:** `config.py` owns the concept instead.

```python
# config.py — demo mode does not exist on this branch. The guard still needs a
# resolved value, and "are the indexes actually there" is the question it was
# really asking.
DEMO_MODE = False

def indexes_present() -> bool:
    return all((index_dir / f).exists()
               for f in ("beit3.index", "keyframe_metadata.json"))
```

`guard.enforce_production_safety()` takes `not indexes_present()` where it previously took
`demo_resolved`. Every other ported module imports the constant from `config`, not from
`preprocess`. `preprocess.py` is not opened.

### 6.3 Flow

```
Login → Board ──claim──→ Workspace ──search──→ Results grid ──Enter──→ Pin frame
                             │                       │                     │
                             └───────── Answer basket (100 rows) ←─────────┘
                                              │
                                          Export → validate → preview → zip
```

### 6.4 State ownership

| State | Owner | Lifetime |
| --- | --- | --- |
| Users, tasks, answers, presence, packs, settings | SQLite (WAL, `busy_timeout=5000`) | durable |
| Last search per `(user, task)` | API process memory | 30 min |
| Auth token + user | `localStorage` | until logout or 401 |
| Board snapshot | `useBoard()` | 3 s poll |
| `frameIdx` | Pin-frame component | until the answer is written |

---

## 7. Interface specification

Prefix `/api`. Bearer token. Every endpoint below is new to this branch; the five existing
search endpoints keep their current paths and shapes, unchanged.

### 7.1 Identity

```
POST /api/auth/login              → { token, user }            | 401 same message both ways
POST /api/auth/change-password    → { ok }
GET  /api/me                      → { user, settings, server_time }
```

### 7.2 Administration

```
POST  /api/admin/users/bulk               → 201 { created: [{username, display_name, password}] }
POST  /api/admin/users/{id}/reset-password
PATCH /api/admin/users/{id}
GET   /api/admin/users
GET   /api/settings · PUT /api/admin/settings
```

### 7.3 Packs

```
POST /api/admin/packs/preview   (multipart: file, filename_pattern)
     → { preview_token, files: [{ filename, matched, code, type, query_text,
                                  question_text, n_events, event_labels, warnings[] }] }
POST /api/admin/packs/commit    { preview_token, round_label, deadline_minutes,
                                  overrides: { <filename>: { question_text } } }
     → 201 { pack_id, tasks_created, skipped }
```

`preview_token` holds the uploaded bytes server-side for 30 minutes so commit does not
re-upload, and so what is committed is exactly what was previewed.

### 7.4 Board and tasks

```
GET  /api/board?pack_id=1   → { round, tasks[{ id, code, type, query_text, owner,
                                answer_count, verified_count, version, viewers[] }] }
POST /api/tasks/{id}/claim   → 200 { task } | 409 { detail, owner }
POST /api/tasks/{id}/release
POST /api/tasks/{id}/force-release      (admin)
POST /api/presence { task_id }          heartbeat, 10 s
```

### 7.5 Search

```
POST /api/search { task_id, query, mode: ensemble|beit3|clip,
                   limit, top_m, use_rerank }
     → { count, took_ms, results[{ name, url, video, frame_idx, timestamp,
                                   distance, routes, has_image }] }
```

The handler validates, calls `search_core`, records the result set for autofill, and
returns. It performs no ranking, no filtering, and no field rewriting.

### 7.6 Answers

```
GET    /api/tasks/{id}/answers
POST   /api/tasks/{id}/answers          { video_id, frames[], answer_text, position }
POST   /api/tasks/{id}/answers/autofill { source: last_search, limit, mode }
PATCH  /api/answers/{id}                { …, version }   → 200 | 409 { current }
DELETE /api/answers/{id}
POST   /api/tasks/{id}/answers/reorder  { answer_id, before_id | after_id }
POST   /api/tasks/{id}/answers/dedupe
PUT    /api/tasks/{id}/answer-text      { answer_text, apply: all|empty_only }
```

### 7.7 Export

```
GET /api/export/validate?pack_id=1  → { ready, issues[{ task_code, severity, message }] }
GET /api/export/preview?task_id=7   → { filename, rows, bytes, content }
GET /api/export/zip?pack_id=1       → application/zip
```

### 7.8 Settings keys

| Key | Default |
| --- | --- |
| `edit_mode` | `open` |
| `export.filename_pattern` | `query-{phase}-{code}-{type}.csv` |
| `export.delimiter` | `,` |
| `export.header` | `false` |
| `export.line_ending` | `LF` |
| `export.encoding` | `utf-8` |
| `export.rows_per_query` | `100` |
| `frames.strip_radius` | `30` |

---

## 8. Data model

`dev`'s schema is adopted unchanged (`backend/app/db/schema.sql`): `users`, `sessions`,
`packs`, `tasks`, `answers`, `presence`, `edit_requests`, `settings`, `video_cache`. SQLite
with `journal_mode=WAL` and `busy_timeout=5000`. Every statement is `IF NOT EXISTS`, applied
on startup, so a fresh deploy needs no separate migration step.

Two additive changes this specification requires:

| Change | Reason |
| --- | --- |
| `packs.phase TEXT` | The real filename carries `p1`; the export filename must reproduce it. |
| `tasks.import_warnings TEXT` (JSON) | The E-number anomaly must survive from preview to the board, not vanish at commit. |

`answers.sort_key` stays `REAL`. Displayed rank is derived at read time with
`ROW_NUMBER() OVER (ORDER BY sort_key)`; when the gap between neighbours falls below `1e-9`
the task is renumbered in the background.

---

## 9. User interface

The approved drawings are `.superpowers/brainstorm/1877-1786204313/content/` —
`workspace-hifi-v3.html` for the workspace, `screens-board-admin.html` for the board, login
and admin screens.

### 9.1 Task board

Answers three questions and nothing else: which task is free, what does it ask, who holds
it. Columns: code · type · query (Vietnamese, verbatim, two lines) · owner or `Claim` ·
answers `42 / 100` where the denominator is `export.rows_per_query` · viewer avatars.

### 9.2 Workspace

Three columns. Switching mode changes only the middle one.

```
┌────────────┬────────────────────────────┬──────────────────┐
│ task rail  │  Results grid / Pin frame  │  answer basket   │
│ (collapse) │                            │  100 rows        │
└────────────┴────────────────────────────┴──────────────────┘
```

- **Task rail** — one coloured dot per task: full, in progress, unclaimed. No numbers.
- **Results grid** — tile background from `routes` (both models / one model), `#1`/`#2`
  basket badge, teammate name, timestamp.
- **Pin frame** — one viewport, two timelines, the transport row of FR-7.2, and every term
  of the calibration on screen.
- **Answer basket** — 100 real rows, the five R@k lines drawn between them, origin stripe
  on the left, type-specific fields on the right.

### 9.3 Keyboard

`←/→` select or step one frame · `Shift+←/→` step ten · `Enter` open pin frame · `Esc` back
to grid · `1` promote to rank 1 · `A` append to basket · `X` discard · `/` focus search.

### 9.4 Removed from the current screen

`Rank`, `Unique Keywords`, `Filter` and the standalone `Translate` panel are deleted — they
were parameters of six endpoints removed in `d09cf9b` and send nothing today. `Show Top`
reads `export.rows_per_query`. The Google Sheets submit path and `gapi-script`, `firebase`,
`react-csv` go with them.

---

## 10. Implementation plan

Seven slices. Each is independently verifiable and leaves the branch working. **S4 is the
line at which the system can compete**; slices after it improve speed and accuracy, not
capability.

### S0 — Baseline and guardrail

1. Commit the inherited work-tree changes (`has_image`, `.env` loading, `AIC_MODELS`,
   requirements) as the `staging` baseline.
2. Add `argon2-cffi`, `python-multipart` to `requirements.txt`; add
   `requirements-dev.txt` with `pytest`, `httpx`; add `vitest` to the frontend.
3. **TST-1 — the golden search test.** Run five fixed queries through `ensemble_search()`
   and snapshot the top-20 `(name, frame_idx, distance, routes)` tuples. The test compares
   against the snapshot on every run. Skips loudly, never silently, when indexes are absent.
4. Remove the three leaked Google credentials and the Google Sheets submit path. Record in
   the commit message that they require revocation in Google Cloud Console.
5. Commit `sample-data/query-p1-groupA.zip` as a test fixture.

**Done when:** `pytest` green, TST-1 passing against real indexes, `/ensemble-search`
byte-identical to `288986e`.

### S1 — Foundation

1. Port `config.py` with the §6.2 seam, `guard.py`, `db/`, `auth/`, `settings_store.py`.
2. Port routers `auth`, `admin_users`, `admin_settings`; wire `lifespan` → `migrate()` →
   guard.
3. Port frontend `api/base.ts` (401 → clear store), `authStore`, `Login`,
   `ChangePassword`, `AdminMembers`, `AdminSettings`, `AdminNav`, `credentialsCsv`.
4. Replace `App.tsx` with the screen switch; move the existing search screen to
   `pages/Search.tsx` untouched so it keeps working throughout S1–S2.
5. Bootstrap the first admin from environment at first start.

**Done when:** an admin creates five accounts, all five log in, each is forced to change
password once, and the plaintext is shown exactly once.

### S2 — Query import

1. Write `packs_store.py`: `parse_pack(zip_bytes, pattern)` implementing §5.2 in one
   function, with the type-specific rules isolated so a format change is a small edit.
2. Routers `admin_packs`: `preview` (multipart, token-held bytes) and `commit`
   (with `overrides`).
3. `AdminPacks.tsx`: drop-zone, pre-filled regex, per-file preview table with warnings, an
   editable Q&A question field, then commit.
4. Schema additions from §8.

**Done when:** `query-p1-groupA.zip` imports 24 tasks; `query-p1-18-trake.txt` yields
`n_events = 4` **and** a visible non-sequential-E warning; `readme`-style unmatched files
are listed with a reason; a second import creates zero duplicates.

### S3 — Workspace, search and basket

1. `search_core.py` + `routers/search.py`, with the last-search cache.
2. `routers/answers.py`: list, create, autofill, patch with `version`, delete, reorder,
   dedupe, Q&A bulk answer text.
3. `hooks/useAnswers()`, `components/workspace/{ResultGrid,AnswerBasket,TaskRail}`.
4. Tile colour from `routes`; delete the distance colouring and the dead controls (§9.4).
5. Replace the filename-milliseconds path with `result.frame_idx` (INV-2).
6. KIS / Q&A / TRAKE basket variants.

**Done when:** one search fills a basket to 100 rows, the rows survive `F5`, reordering is
one `UPDATE`, and a simulated stale `PATCH` returns `409` with the current row.

### S4 — Export · the competition-ready line

1. `export_store.py`: row builders per type, RFC 4180 quoting, settings-driven bytes.
2. `routers/export.py`: `validate`, `preview`, `zip`.
3. `Export.tsx`: issue list, byte preview, download.

**Done when:** exporting a pack whose baskets are seeded from the 2025 ground truth
reproduces the expected bytes for one KIS, one Q&A **with an embedded comma**, and one
TRAKE task; every task in the pack has a file; no BOM.

### S5 — Collaboration

1. `routers/board.py`: board, claim, release, force-release, presence.
2. `hooks/useBoard()` with the 3 s poll; optimistic claim with rollback toast.
3. `Board.tsx` per §9.1; viewer avatars; offline-owner warning.
4. Conflict-resolution dialog for `409` on answers.

**Done when:** two browsers claiming one task **in parallel** produce exactly one `200` and
one `409` naming the winner — the test issues both requests concurrently, because a
sequential test passes against a broken implementation.

### S6 — Frame precision and polish

1. Port `frameMath.ts` (`frameAtTime` / `timeForFrame` round-trip, two-landmark
   calibration, `driftFrames`).
2. `PinFrame` component per §9.2 and FR-7.
3. Keyboard map (§9.3), R@k boundary lines, task rail dots, layout to the v3 mockup.
4. Remove `drive-video-proxy` from the main flow; drop `gapi-script`, `firebase`,
   `react-csv`.

**Done when:** stepping is exact integer arithmetic, the calibration in force is displayed
wherever a computed frame is, and no `seconds × fps` remains in the frontend.

---

## 11. Test strategy

| ID | Test | Slice |
| --- | --- | --- |
| TST-1 | Golden search snapshot — top-20 tuples for five fixed queries | S0 |
| TST-2 | Login: wrong user and wrong password return identical bodies | S1 |
| TST-3 | Forced password change blocks every route except `/api/me` | S1 |
| TST-4 | Parse the real pack: 24 files, correct types, gaps tolerated | S2 |
| TST-5 | `E1,E2,E2,E4` → `n_events = 4` plus a warning | S2 |
| TST-6 | Q&A question inference, including a file with no `?` | S2 |
| TST-7 | Search response preserves `frame_idx` and `routes` exactly | S3 |
| TST-8 | Autofill `append` leaves manual rows untouched | S3 |
| TST-9 | Stale `PATCH` version → `409` with the current row | S3 |
| TST-10 | Reorder is a single row `UPDATE`; derived ranks stay contiguous | S3 |
| TST-11 | Byte-exact export for KIS, Q&A-with-comma, TRAKE | S4 |
| TST-12 | Zip contains one file per task including empty tasks; no BOM | S4 |
| TST-13 | **Parallel** claim: exactly one winner | S5 |
| TST-14 | Presence expires at 30 s | S5 |
| TST-15 | `frameAtTime` / `timeForFrame` round-trip at 24, 25, 29.97, 30, 59.94 fps | S6 |
| TST-16 | Calibration refuses landmarks under 10 s apart or a fit >20% off nominal | S6 |

---

## 12. Risks and open questions

| ID | Risk | Mitigation | Status |
| --- | --- | --- | --- |
| R-1 | Under a week for full accounts plus a ground-up UI rebuild | Slice order puts the submission path (S0–S4) before collaboration and polish (S5–S6). If the clock runs out, the system still competes. | accepted |
| R-2 | Submission **file** shape (as opposed to row shape) is inferred from the input pack's naming, not published | Every byte is a setting; changing it is a form edit plus one test update | open |
| R-3 | BOM tolerance of the organizer's parser is unknown | Default no BOM; `utf-8-sig` remains a legal setting value | open (U3) |
| R-4 | `fps_map.json` provenance — organizer table or our probe (U1) | Per-video calibration measures it in ~30 s; `driftFrames()` reports how far the correction moved the answer | mitigated, still worth confirming |
| R-5 | Group A is 24 of the round's queries; other groups may differ | Regex + preview absorb a naming change; the line-position rules live in one function | accepted |
| R-6 | `watch_url` per video is not in the repo (U7) | Organizer metadata JSON per video is documented to exist; pin-frame works from keyframes without it | open |
| R-7 | A port from `dev` silently changes search behaviour | TST-1 fails the build | mitigated |

---

## 13. Explicitly not in this specification

WebSocket transport · the full lexical route (OCR/ASR/caption/tag → BM25 → RRF) · a UI for
`/temporal-search` · the Q4 single-vs-ensemble experiment screen · bounded video cache and
eviction · real frame-strip decoding from video · automatic submission upload.

---

## 14. Definition of done

The whole of this specification reduces to one sentence, and every requirement above traces
to a clause of it:

> The team logs in, imports the organizer's pack, splits the round's queries with no two
> people on the same one, searches with the ensemble pipeline behaving **exactly** as it
> does on `ensemble-search` today, ranks 100 answers per query with the scoring boundaries
> drawn on screen, and exports a submission zip whose bytes are correct — with a test that
> fails the moment anyone changes what search returns.
