# Staging — Collaboration, Query Import and Submission Export Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the working ensemble-search prototype into a system five people can compete with — accounts, the organizer's query pack imported as tasks, a 100-row answer basket per task, and a byte-correct submission zip — without changing a single line of what search returns.

**Architecture:** `backend/app/preprocess.py` is frozen and pinned by a golden snapshot test. A new `search_core.py` is the only module that calls it. Around that core we add the layer `dev` already proved: SQLite (WAL) for durable state, argon2id sessions, FastAPI routers under `/api`, and a React front end that replaces the single search screen with Login → Board → Workspace → Export. The pack parser and the exporter are written fresh against the real organizer files, not against `dev`'s guesses.

**Tech Stack:** FastAPI · SQLite (WAL) · argon2-cffi · pytest + httpx TestClient · React 19 + Vite + TypeScript · Zustand · Tailwind 4 · vitest

**Spec:** `docs/superpowers/specs/2026-08-16-staging-collab-import-export-design.md`

---

## Global Constraints

Every task's requirements implicitly include this section.

- **Branch:** all work lands on `staging`. Never commit to `ensemble-search`, `dev`, or `main`.
- **INV-1 — `backend/app/preprocess.py` is frozen.** No task in this plan edits it. If a task appears to require an edit there, stop and escalate instead.
- **INV-2 — Frame numbers are passed through (`result.frame_idx`) or computed as `floor(fps · t + offset)`.** Never derived from a filename, never snapped to a keyframe.
- **INV-3 — Nothing important lives only in the browser.** Answers, claims and ordering go to the server before they count.
- **INV-4 — Organizer query text is stored and displayed verbatim, never translated.**
- **INV-5 — Contention is resolved in SQL** (conditional `UPDATE`), never `SELECT`-then-`IF`.
- **INV-6 — No secrets in source.**
- **Language:** all code, comments, UI labels, docs and commit messages in English. The only Vietnamese in the product is organizer query text and user-typed search queries.
- **Python interpreter:** `backend/venv/Scripts/python.exe` (Python 3.13). Backend commands run **from the `backend/` directory** because `pytest.ini` sets `testpaths = tests` and `pythonpath = .`.
  - Bash: `cd backend && ./venv/Scripts/python.exe -m pytest -v`
  - PowerShell: `cd backend; .\venv\Scripts\python.exe -m pytest -v`
- **Frontend commands** run from `frontend/`: `npm run test`, `npm run build`, `npm run lint`.
- **Already installed in the venv:** `pytest`, `argon2-cffi`, `httpx`, `Pillow`, `faiss`, `torch`. **Missing:** `python-multipart`.
- **Settings defaults that differ from `dev`:** `export.filename_pattern` is `query-{phase}-{code}-{type}.csv` (not `query-{id}-{type}.csv`).
- **Porting convention:** when a step says *port from dev*, the file is taken verbatim with `git show dev:<path> > <path>` and then edited only where the step lists an edit. Do not "improve" a ported file — the diff must stay reviewable.
- **Commit style:** the message explains *why*, not just *what*. End every commit body with:
  `Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>`

---

## File Structure

### Backend — created

| File | Responsibility |
| --- | --- |
| `backend/app/config.py` | The only module that reads `os.environ`. Owns `DEMO_MODE = False` and `indexes_present()`. |
| `backend/app/guard.py` | Reasons production must refuse to start. |
| `backend/app/db/connection.py` | One connection helper; WAL, busy timeout, foreign keys, `utcnow_iso()`. |
| `backend/app/db/migrate.py` | Applies `schema.sql` on every startup. Idempotent. |
| `backend/app/db/schema.sql` | The tables of spec §8. |
| `backend/app/auth/passwords.py` | argon2id hash/verify, generated passwords. |
| `backend/app/auth/sessions.py` | Token create/resolve/delete. |
| `backend/app/auth/deps.py` | FastAPI dependencies: `active_user`, `require_admin`. |
| `backend/app/auth/bootstrap.py` | Creates the first admin. |
| `backend/app/settings_store.py` | The settings keys, their types, their defaults. |
| `backend/app/packs_store.py` | **New.** Parses the real organizer pack (spec §5.2). |
| `backend/app/answers_store.py` | **New.** Sort keys, rank derivation, version-checked writes. |
| `backend/app/export_store.py` | **New.** Builds submission rows and bytes (spec §5.3). |
| `backend/app/search_core.py` | **New.** The only caller of `preprocess.py`, plus the last-search cache. |
| `backend/app/routers/schemas.py` | Shared request/response models. `UserOut` is the leak guard. |
| `backend/app/routers/auth.py` | login · change-password · me |
| `backend/app/routers/admin_users.py` | bulk create · reset · patch · list |
| `backend/app/routers/admin_settings.py` | read/write settings |
| `backend/app/routers/admin_packs.py` | pack preview · commit |
| `backend/app/routers/board.py` | board · claim · release · force-release · presence |
| `backend/app/routers/search.py` | `POST /api/search` |
| `backend/app/routers/answers.py` | answers CRUD · autofill · reorder · dedupe |
| `backend/app/routers/export.py` | validate · preview · zip |

### Backend — modified

| File | Change |
| --- | --- |
| `backend/app/main.py` | Add `lifespan` → `migrate()` → guard; include routers; CORS from settings. The five existing search endpoints are untouched. |
| `backend/requirements.txt` | Add `argon2-cffi`, `python-multipart`. |
| `backend/.env.example` | Add `AIC_ENV`, `AIC_DB_PATH`, `AIC_CORS_ORIGINS`. |

### Frontend — created

| File | Responsibility |
| --- | --- |
| `frontend/src/api/base.ts` | `apiFetch`, `ApiRequestError` (keeps the whole 409 body), 401 → clear session. |
| `frontend/src/api/{auth,admin,packs,board,search,answers,export}.ts` | One module per endpoint family. |
| `frontend/src/store/authStore.ts` | Token + user, persisted to `localStorage`. |
| `frontend/src/store/workspaceStore.ts` | Selected task, last search results, selected tile. |
| `frontend/src/hooks/useBoard.ts` | The **only** place board data is fetched. 3 s poll. |
| `frontend/src/hooks/useAnswers.ts` | The only place answer data is fetched. |
| `frontend/src/helpers/{credentialsCsv,frameMath,frameTimestamp}.ts` | Pure helpers, unit tested. |
| `frontend/src/pages/{Login,ChangePassword,AdminMembers,AdminPacks,AdminSettings,Board,Workspace,Export}.tsx` | One screen each. |
| `frontend/src/components/workspace/{TaskRail,ResultGrid,PinFrame,AnswerBasket}.tsx` | The three columns of spec §9.2. |
| `frontend/src/types/{prototype,collab}.ts` | Types for the collaboration layer. |

### Frontend — modified

| File | Change |
| --- | --- |
| `frontend/src/App.tsx` | Becomes a screen switch. The current body moves verbatim to `pages/Search.tsx`. |
| `frontend/src/components/FrameDisplay/index.tsx` | Colour from `routes`; drop the distance gradient. |
| `frontend/src/components/QueryInput/index.tsx` | Delete the dead controls. |
| `frontend/src/types/api.ts` | Add collaboration types; keep the existing search client working. |

### Deleted

`frontend/src/components/SubmitForm/` (Google Sheets path and three leaked credentials) · `frontend/src/store/submitStore.ts` · dependencies `gapi-script`, `firebase`, `react-csv`.

---

# Slice S0 — Baseline and guardrail

**Nothing may be ported until the guardrail exists.** A snapshot taken after the first port is a snapshot of possibly-broken behaviour.

---

### Task 1: Test harness and dependency manifests

**Files:**
- Create: `backend/pytest.ini`
- Create: `backend/requirements-dev.txt`
- Create: `backend/tests/__init__.py`
- Create: `backend/tests/test_harness.py`
- Modify: `backend/requirements.txt`
- Modify: `frontend/package.json`
- Create: `frontend/vitest.config.ts`

**Interfaces:**
- Consumes: nothing.
- Produces: a working `pytest` run from `backend/`, and `npm run test` from `frontend/`.

- [ ] **Step 1: Commit the inherited work-tree changes as the baseline**

The branch carries uncommitted work (`has_image`, `.env` loading, `AIC_MODELS`, requirements). It must be the recorded starting point, because Task 2 snapshots its behaviour.

```bash
git add backend/.env.example backend/app/__init__.py backend/app/main.py \
        backend/app/preprocess.py backend/requirements.txt \
        frontend/src/App.tsx frontend/src/components/FrameDisplay/index.tsx \
        frontend/src/types/api.ts
git commit -m "Baseline: has_image, .env loading and the AIC_MODELS gate

Records the working ensemble-search state as the starting point for staging.
The golden snapshot in the next commit is taken against exactly this code, so
it has to be committed before the snapshot rather than after.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

- [ ] **Step 2: Write the harness test**

Create `backend/tests/__init__.py` as an empty file, then `backend/tests/test_harness.py`:

```python
"""Proves the test runner can import the application at all.

Importing app.main pulls torch and faiss, which is why the first test in a run
is slow and the rest are not. It does NOT load the FAISS indexes: preprocess.py
loads those lazily on the first search.
"""
from __future__ import annotations


def test_app_imports():
    from app.main import app

    assert app.title.startswith("AI Challenge")


def test_search_endpoints_are_still_registered():
    """The five endpoints this branch competes with. If a port deletes one of
    these, this test is the alarm."""
    from app.main import app

    paths = {route.path for route in app.routes}
    for path in ("/ensemble-search", "/single-search", "/temporal-search",
                 "/status", "/health"):
        assert path in paths, f"{path} disappeared from main.py"
```

- [ ] **Step 3: Create the runner configuration**

`backend/pytest.ini`:

```ini
[pytest]
testpaths = tests
pythonpath = .
markers =
    slow: needs the real FAISS indexes and loads a model (minutes, not seconds)
```

`backend/requirements-dev.txt`:

```
# Test-only dependencies, deliberately separate from requirements.txt so a
# runtime image does not carry a test runner.
#
#   venv/Scripts/python.exe -m pip install -r requirements.txt -r requirements-dev.txt
#
# httpx is what starlette's TestClient runs on — without it, importing
# fastapi.testclient raises RuntimeError at import time.
pytest==8.3.4
httpx==0.28.1
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
cd backend && ./venv/Scripts/python.exe -m pytest -v
```

Expected: 2 passed. If `test_app_imports` fails, stop — something is wrong with the baseline, not with this plan.

- [ ] **Step 5: Add the runtime dependencies this plan needs**

Append to `backend/requirements.txt`:

```
# ─── Collaboration layer ─────────────────────────────────────────────────────
# argon2id password hashing. The winner of the Password Hashing Competition and
# the default recommendation for new systems; bcrypt's 72-byte input truncation
# is a footgun we do not need to own.
argon2-cffi==25.1.0

# FastAPI needs this to parse multipart/form-data, which is how the organizer's
# query ZIP is uploaded. Without it, the upload endpoint raises at import time.
python-multipart==0.0.20
```

Install:

```bash
cd backend && ./venv/Scripts/python.exe -m pip install -r requirements.txt -r requirements-dev.txt
```

- [ ] **Step 6: Add the frontend test runner**

In `frontend/package.json`, add `"test": "vitest run"` to `scripts` and `"vitest": "^2.1.9"` to `devDependencies`. Create `frontend/vitest.config.ts`:

```ts
import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    environment: "node",
    include: ["src/**/*.test.ts"],
  },
});
```

Then:

```bash
cd frontend && npm install && npm run test
```

Expected: vitest reports "No test files found" and exits 0. That is the correct result — the first test arrives in Task 2's frontend counterpart.

- [ ] **Step 7: Commit**

```bash
git add backend/pytest.ini backend/requirements.txt backend/requirements-dev.txt \
        backend/tests frontend/package.json frontend/package-lock.json \
        frontend/vitest.config.ts
git commit -m "Add the test harness both halves of this plan need

pytest with pythonpath=. so tests import app.* the way the application does,
and a marker for the slow tests that load a real model. The two harness tests
assert the five search endpoints are still registered, because every remaining
task in this plan adds routers around them and deleting one by accident would
otherwise surface only in a browser.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: TST-1 — the golden search snapshot

This is the task that makes INV-1 enforceable. Everything after it is safe to port; nothing before it is.

**Files:**
- Create: `backend/tests/golden/__init__.py`
- Create: `backend/tests/golden/record.py`
- Create: `backend/tests/golden/ensemble_top20.json` (generated, committed)
- Create: `backend/tests/test_search_frozen.py`

**Interfaces:**
- Consumes: `app.preprocess.ensemble_search`, `app.preprocess.ACTIVE_MODELS`.
- Produces: `compare_snapshot(actual: list[dict], expected: list[dict]) -> list[str]` — returns a list of human-readable differences, empty when identical. Task 14 re-uses nothing from here; this task exists purely as a guard.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_search_frozen.py`:

```python
"""INV-1: the retrieval core does not change.

This is a characterization test, not a correctness test. It does not claim the
results are good — it claims they are the SAME. That is the property at risk:
this branch is about to absorb a large amount of code from `dev`, whose own
preprocess.py generates fake results when indexes are missing. If that path
ever wins a merge, every screen still works and every number is invented. This
test is the only thing that would notice.

Marked slow: it loads BEiT3 (~1.3 GB) and queries two FAISS indexes.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

SNAPSHOT = Path(__file__).parent / "golden" / "ensemble_top20.json"

#: Fixed and never edited. Changing a query invalidates the snapshot, which is
#: the same as deleting the guard.
QUERIES = [
    "bốn phi hành gia mặc áo đen trong phần giới thiệu phóng tàu vũ trụ tư nhân",
    "đàn hổ quý hiếm được nuôi tại một địa phương miền Nam",
    "hai người phụ nữ đang cho dê ăn trong trại",
    "tác phẩm điêu khắc cát tại lễ hội điêu khắc trên cát",
    "mâm bánh xèo tại gian hàng bánh dân gian miền Tây",
]

TOP_N = 20


def compare_snapshot(actual: list[dict], expected: list[dict]) -> list[str]:
    """Human-readable differences between two recorded runs. Empty == identical."""
    problems: list[str] = []

    if actual == expected:
        return problems

    if len(actual) != len(expected):
        problems.append(f"query count changed: {len(expected)} -> {len(actual)}")
        return problems

    for got, want in zip(actual, expected):
        label = want["query"][:40]
        if got["query"] != want["query"]:
            problems.append(f"query text changed: {want['query']!r} -> {got['query']!r}")
            continue
        if len(got["rows"]) != len(want["rows"]):
            problems.append(
                f"[{label}] row count {len(want['rows'])} -> {len(got['rows'])}"
            )
            continue
        for rank, (a, b) in enumerate(zip(got["rows"], want["rows"]), start=1):
            if a != b:
                problems.append(f"[{label}] rank {rank}: {b} -> {a}")
    return problems


def _record() -> list[dict]:
    from tests.golden.record import record

    return record(QUERIES, TOP_N)


@pytest.mark.slow
def test_ensemble_search_output_is_unchanged():
    if not SNAPSHOT.exists():
        pytest.fail(
            "No golden snapshot. Record one against known-good code with:\n"
            "  cd backend && ./venv/Scripts/python.exe -m tests.golden.record"
        )

    expected = json.loads(SNAPSHOT.read_text(encoding="utf-8"))

    from app.preprocess import ACTIVE_MODELS

    if list(ACTIVE_MODELS) != expected["active_models"]:
        pytest.skip(
            f"AIC_MODELS differs from the snapshot "
            f"({list(ACTIVE_MODELS)} vs {expected['active_models']}). "
            "The comparison would be meaningless — set AIC_MODELS to match, "
            "or re-record deliberately."
        )

    problems = compare_snapshot(_record(), expected["queries"])
    assert not problems, "Retrieval output changed:\n  " + "\n  ".join(problems)


def test_comparison_detects_a_single_changed_distance():
    """Proves the guard bites.

    A snapshot test that is never shown to fail is indistinguishable from a
    snapshot test that cannot fail. This mutates one distance by one hundredth
    and asserts the comparison reports it — without touching preprocess.py.
    """
    baseline = [
        {"query": "q", "rows": [["A-1.jpg", 10, 88.5, ["beit3", "clip"]]]},
    ]
    mutated = [
        {"query": "q", "rows": [["A-1.jpg", 10, 88.51, ["beit3", "clip"]]]},
    ]

    problems = compare_snapshot(mutated, baseline)

    assert len(problems) == 1
    assert "rank 1" in problems[0]
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd backend && ./venv/Scripts/python.exe -m pytest tests/test_search_frozen.py -v
```

Expected: `test_comparison_detects_a_single_changed_distance` FAILS with `ModuleNotFoundError: No module named 'tests.golden'`, because the package does not exist yet.

- [ ] **Step 3: Write the recorder**

Create `backend/tests/golden/__init__.py` (empty), then `backend/tests/golden/record.py`:

```python
"""Records what ensemble_search() returns today, so tomorrow can be compared.

Only four fields per row are recorded. They are the ones that change if any
part of the pipeline changes, and they are the ones a submission is built from:

  name       which keyframe   — changes if FAISS, the index, or the merge changes
  frame_idx  the submitted integer (INV-2)
  distance   the merged score — changes if weights or rerank change
  routes     which models found it, sorted — changes if a model is dropped

url and has_image are deliberately excluded: they depend on which ZIPs happen
to be unpacked on the machine, which is not a property of the pipeline.
"""
from __future__ import annotations

import json
from pathlib import Path

SNAPSHOT = Path(__file__).resolve().parent / "ensemble_top20.json"


def record(queries: list[str], top_n: int) -> list[dict]:
    from app.preprocess import ensemble_search

    recorded = []
    for query in queries:
        results = ensemble_search(query, top_k=top_n, top_m=50, use_rerank=True)
        rows = [
            [
                r["name"],
                r.get("frame_idx"),
                round(float(r["distance"]), 6),
                sorted((r.get("routes") or {}).keys()),
            ]
            for r in results[:top_n]
        ]
        recorded.append({"query": query, "rows": rows})
    return recorded


def main() -> int:
    from app.preprocess import ACTIVE_MODELS
    from tests.test_search_frozen import QUERIES, TOP_N

    payload = {
        "active_models": list(ACTIVE_MODELS),
        "top_n": TOP_N,
        "queries": record(QUERIES, TOP_N),
    }
    SNAPSHOT.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    total = sum(len(q["rows"]) for q in payload["queries"])
    print(f"wrote {SNAPSHOT} — {len(payload['queries'])} queries, {total} rows")
    print(f"active_models={payload['active_models']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run the test again to confirm the unit half passes**

```bash
cd backend && ./venv/Scripts/python.exe -m pytest tests/test_search_frozen.py -v
```

Expected: `test_comparison_detects_a_single_changed_distance` PASSES.
`test_ensemble_search_output_is_unchanged` FAILS with the "No golden snapshot" message. That is the next step's job.

- [ ] **Step 5: Record the snapshot against known-good code**

```bash
cd backend && ./venv/Scripts/python.exe -m tests.golden.record
```

Expected output names the file and prints `active_models=['beit3']` (or `['beit3', 'clip']` depending on `backend/.env`). This takes minutes — it loads BEiT3 once.

**If it errors because indexes are missing, stop and escalate.** A snapshot cannot be recorded on a machine without the real indexes, and recording an empty one would be worse than having none.

- [ ] **Step 6: Run the full guard and verify it passes**

```bash
cd backend && ./venv/Scripts/python.exe -m pytest tests/test_search_frozen.py -v
```

Expected: 2 passed.

- [ ] **Step 7: Commit**

```bash
git add backend/tests/golden backend/tests/test_search_frozen.py
git commit -m "Pin the retrieval core with a golden snapshot (TST-1, INV-1)

This branch is about to absorb the collaboration layer from dev, whose own
preprocess.py generates deterministic fake results when indexes are missing.
If that path ever wins, every screen still renders and every number is
invented - there is no error, no empty list, nothing that looks wrong. This
snapshot of five fixed queries is the only thing that would notice.

The second test mutates one distance by 0.01 and asserts the comparison
reports it, because a snapshot test never seen to fail is indistinguishable
from one that cannot fail.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Purge the leaked credentials and the dead submit path

**Files:**
- Delete: `frontend/src/components/SubmitForm/index.tsx`
- Delete: `frontend/src/components/SubmitForm/RangeForm.tsx`
- Delete: `frontend/src/store/submitStore.ts`
- Modify: `frontend/src/components/VideoPopUp/VideoDisplay.tsx`
- Modify: `frontend/package.json`
- Create: `backend/tests/test_no_secrets.py`

**Interfaces:**
- Consumes: nothing.
- Produces: nothing. This task only removes.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_no_secrets.py`:

```python
"""No credential-shaped string may re-enter the working tree.

Deleting these from the working tree does not delete them from git history —
they must also be revoked in Google Cloud Console. This test only stops the
same mistake from being made twice.
"""
from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

SEARCH_ROOTS = (REPO / "frontend" / "src", REPO / "backend" / "app")

PATTERNS = {
    "Google API key": re.compile(r"AIza[0-9A-Za-z_\-]{35}"),
    "Google OAuth client id": re.compile(r"[0-9]{10,}-[0-9a-z]{32}\.apps\.googleusercontent\.com"),
    "private key block": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
}

SKIP_DIRS = {"node_modules", "venv", "__pycache__", "unilm_beit3", "dist"}


def _source_files():
    for root in SEARCH_ROOTS:
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            if SKIP_DIRS & set(path.parts):
                continue
            if path.suffix.lower() in (".ts", ".tsx", ".js", ".jsx", ".py", ".json", ".env"):
                yield path


def test_no_credentials_in_source():
    findings = []
    for path in _source_files():
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for label, pattern in PATTERNS.items():
            if pattern.search(text):
                findings.append(f"{label} in {path.relative_to(REPO)}")

    assert not findings, "Credentials found in source:\n  " + "\n  ".join(findings)
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd backend && ./venv/Scripts/python.exe -m pytest tests/test_no_secrets.py -v
```

Expected: FAIL, listing `SubmitForm/index.tsx` and `VideoPopUp/VideoDisplay.tsx`.

- [ ] **Step 3: Delete the Google Sheets submit path**

```bash
git rm -r frontend/src/components/SubmitForm
git rm frontend/src/store/submitStore.ts
```

In `frontend/src/components/VideoPopUp/VideoDisplay.tsx`, remove the hardcoded default from the `apiKey` parameter so it has no default value at all, and remove any call site that relied on it. If `VideoDisplay` becomes unused as a result, leave the file in place — Task 29 replaces it.

In `frontend/package.json`, remove `"gapi-script"`, `"firebase"`, `"react-csv"` from `dependencies` and `"@types/react-csv"` from `devDependencies`.

If any surviving file imports `SubmitForm` or `submitStore`, delete that import and the JSX that used it. `frontend/src/App.tsx` is the likely one.

- [ ] **Step 4: Run the tests and the build to verify**

```bash
cd backend && ./venv/Scripts/python.exe -m pytest tests/test_no_secrets.py -v
cd ../frontend && npm install && npm run build
```

Expected: pytest 1 passed; `npm run build` succeeds with no unresolved imports.

- [ ] **Step 5: Commit**

```bash
git add -A frontend backend/tests/test_no_secrets.py
git commit -m "Remove the leaked Google credentials and the dead submit path

Three credentials were hardcoded in the front end - an OAuth client id and two
API keys - and all three are in git history, so they must be treated as leaked
and revoked in Google Cloud Console. Deleting them here only stops a fourth.

The Google Sheets path went with them: it was the only consumer, react-csv was
imported beside it and never rendered, and submitStore kept the round's work in
memory where F5 destroyed it. The server-side answer basket replaces all three.

ACTION REQUIRED: revoke the OAuth client id and both API keys in Google Cloud
Console. This commit does not and cannot do that.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: Commit the organizer pack as a test fixture

**Files:**
- Modify: `.gitignore`
- Add: `sample-data/query-p1-groupA.zip`
- Create: `backend/tests/test_fixture_present.py`

**Interfaces:**
- Produces: `backend/tests/fixtures.py` → `ORGANIZER_PACK: Path`, used by Tasks 11, 12 and 21.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/fixtures.py`:

```python
"""Paths to committed test fixtures."""
from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

#: The real organizer pack: AIC 2025 Round 1, group A, 24 .txt files.
#: This is the only evidence of the real format we have; every parser test
#: asserts against it rather than against a shape we invented.
ORGANIZER_PACK = REPO / "sample-data" / "query-p1-groupA.zip"
```

Create `backend/tests/test_fixture_present.py`:

```python
from __future__ import annotations

import zipfile

from tests.fixtures import ORGANIZER_PACK


def test_organizer_pack_is_committed():
    assert ORGANIZER_PACK.is_file(), (
        f"{ORGANIZER_PACK} is missing. Every import test depends on it."
    )


def test_organizer_pack_has_the_expected_shape():
    with zipfile.ZipFile(ORGANIZER_PACK) as archive:
        names = sorted(n for n in archive.namelist() if n.endswith(".txt"))

    assert len(names) == 24
    assert all(n.startswith("query-p1-") for n in names)
    # There is no file 3. Gaps in the numbering are normal and the importer
    # must not assume a contiguous range.
    assert not any(n.startswith("query-p1-3-") for n in names)
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd backend && ./venv/Scripts/python.exe -m pytest tests/test_fixture_present.py -v
```

Expected: FAIL — the file is present on disk but untracked, and `.gitignore` may exclude it. Confirm which by running `git check-ignore -v sample-data/query-p1-groupA.zip`.

- [ ] **Step 3: Track the fixture**

If `.gitignore` excludes it, add an explicit exception:

```gitignore
# The organizer's real query pack. Committed on purpose: it is the only
# evidence of the real file format, and every import test asserts against it.
!sample-data/query-p1-groupA.zip
```

Then:

```bash
git add -f sample-data/query-p1-groupA.zip
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
cd backend && ./venv/Scripts/python.exe -m pytest tests/ -v -m "not slow"
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add .gitignore sample-data/query-p1-groupA.zip backend/tests/fixtures.py \
        backend/tests/test_fixture_present.py
git commit -m "Commit the organizer's query pack as a test fixture

dev's importer was written against a format we invented, and it is wrong in
five ways. This file is the only evidence of the real one, so every parser test
asserts against it rather than against a shape of our own. Four megabytes is a
cheap price for not guessing twice.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

# Slice S1 — Foundation: configuration, database, accounts

Every task in this slice ports a file from `dev` verbatim and then makes a small, listed
edit. The value is in the edits — read them carefully, and resist improving anything else.

---

### Task 5: Configuration and the production guard

The one design decision in this slice. `dev`'s modules import `DEMO_MODE` from
`preprocess.py`; this branch deleted demo mode deliberately (INV-1 forbids adding it back).
`config.py` takes ownership of the concept instead.

**Files:**
- Create: `backend/app/config.py`
- Create: `backend/app/guard.py`
- Create: `backend/tests/conftest.py`
- Create: `backend/tests/test_config.py`
- Modify: `backend/.env.example`

**Interfaces:**
- Produces:
  - `app.config.load_settings(env_file: Path | None = None) -> Settings`
  - `app.config.settings` — module `__getattr__`, resolved lazily per access
  - `app.config.DEMO_MODE: bool` — always `False` on this branch
  - `app.config.indexes_present() -> bool`
  - `app.config.ConfigError`
  - `Settings` fields: `env`, `demo_forced`, `db_path`, `index_dir`, `images_dir`, `image_base_url`, `video_dir`, `cors_origins`, `cache_limit_bytes`, `seed_allowed`, `session_ttl_days`, and properties `is_prod`, `is_dev`
  - `app.guard.enforce_production_safety(settings: Settings, demo_resolved: bool, conn: sqlite3.Connection | None = None) -> list[str]`

- [ ] **Step 1: Port both files from dev**

```bash
git show dev:backend/app/config.py > backend/app/config.py
git show dev:backend/app/guard.py > backend/app/guard.py
```

- [ ] **Step 2: Write the failing test**

Create `backend/tests/test_config.py`:

```python
"""AIC_ENV is mandatory, and demo mode does not exist on this branch."""
from __future__ import annotations

import pytest

from app.config import ConfigError, load_settings


def test_env_is_mandatory(monkeypatch, tmp_path):
    """A production host that forgot the variable must not come up in dev mode."""
    monkeypatch.delenv("AIC_ENV", raising=False)

    with pytest.raises(ConfigError) as exc:
        load_settings(env_file=tmp_path / "absent.env")

    assert "AIC_ENV" in str(exc.value)


def test_prod_refuses_a_wildcard_origin(monkeypatch, tmp_path):
    monkeypatch.setenv("AIC_ENV", "prod")
    monkeypatch.setenv("AIC_CORS_ORIGINS", "*")

    from app.guard import enforce_production_safety

    settings = load_settings(env_file=tmp_path / "absent.env")
    violations = enforce_production_safety(settings, demo_resolved=False)

    assert any("*" in v for v in violations)


def test_demo_mode_is_false_on_this_branch():
    """INV-1: preprocess.py has no demo mode and none is being added back.

    guard.py still needs a resolved value; config.py owns it so that no module
    has a reason to reach into preprocess.py for one.
    """
    from app.config import DEMO_MODE

    assert DEMO_MODE is False


def test_indexes_present_reports_the_real_question(monkeypatch, tmp_path):
    """What the guard was really asking was 'did the volume mount'."""
    monkeypatch.setenv("AIC_ENV", "dev")
    monkeypatch.setenv("AIC_INDEX_DIR", str(tmp_path))

    from app.config import indexes_present

    assert indexes_present() is False

    (tmp_path / "beit3.index").write_bytes(b"x")
    (tmp_path / "keyframe_metadata.json").write_text("{}", encoding="utf-8")

    assert indexes_present() is True
```

- [ ] **Step 3: Run the test to verify it fails**

```bash
cd backend && ./venv/Scripts/python.exe -m pytest tests/test_config.py -v
```

Expected: the last two tests FAIL with `ImportError: cannot import name 'DEMO_MODE'`.

- [ ] **Step 4: Add the seam to `config.py`**

Append to `backend/app/config.py`, immediately after the `GIB = 1024**3` line:

```python
#: This branch has no demo mode. `dev`'s preprocess.py generates deterministic
#: fake results when index files are missing so its UI could be built before any
#: index existed; ensemble-search deleted that path once the indexes were real,
#: and INV-1 forbids adding it back.
#:
#: guard.py still needs a resolved demo value, and several ported modules import
#: one. They import it from here, so nothing has a reason to reach into
#: preprocess.py — which is the module this whole plan exists to leave alone.
DEMO_MODE = False


def indexes_present() -> bool:
    """Whether the FAISS indexes this process would search are actually there.

    This is the question guard.py's `demo_resolved` argument was really asking.
    On `dev` a missing index silently turned on generated results; here it means
    search will fail loudly, and in production it means the volume did not mount.
    Two files are enough to tell: the index itself and the metadata that maps its
    vectors back to keyframes.
    """
    index_dir = load_settings().index_dir
    return all(
        (index_dir / name).exists()
        for name in ("beit3.index", "keyframe_metadata.json")
    )
```

- [ ] **Step 5: Write the shared test fixtures**

Port `dev`'s conftest and remove the demo-mode line:

```bash
git show dev:backend/tests/conftest.py > backend/tests/conftest.py
```

Then edit the `client` fixture: delete the line `monkeypatch.setenv("AIC_DEMO", "1")` and replace its docstring paragraph about demo mode with:

```python
    """A TestClient on a fresh database.

    Entered with `with`, because that is what runs the lifespan handler, and the
    lifespan handler is what runs migrate(). Without the `with`, every test hits
    an empty file.

    Importing app.main pulls torch and faiss - which is why the first test in a
    run is slow and the rest are not - but it does not load the FAISS indexes.
    preprocess.py loads those lazily on the first search, and no test here
    searches.
    """
```

- [ ] **Step 6: Run the tests to verify they pass**

```bash
cd backend && ./venv/Scripts/python.exe -m pytest tests/test_config.py -v
```

Expected: 4 passed.

- [ ] **Step 7: Document the new variables**

Append to `backend/.env.example`:

```
# ─── Collaboration layer ─────────────────────────────────────────────────────
# Mandatory, no default: a production host that forgot this would otherwise come
# up in development mode with CORS wide open.
AIC_ENV=dev

# SQLite file. Default: backend/app/data/app.db
# AIC_DB_PATH=

# Comma-separated. In prod a wildcard is refused by the guard.
# AIC_CORS_ORIGINS=http://localhost:5173
```

- [ ] **Step 8: Commit**

```bash
git add backend/app/config.py backend/app/guard.py backend/.env.example \
        backend/tests/conftest.py backend/tests/test_config.py
git commit -m "Configuration, the production guard, and the demo-mode seam

Ports dev's config and guard, then resolves the one incompatibility between the
two branches: dev's modules import DEMO_MODE from preprocess.py, and this branch
deleted demo mode when the indexes became real. Re-adding it would violate INV-1
and would reintroduce the exact failure the golden test exists to catch.

config.py owns the constant instead, and indexes_present() answers what the
guard was really asking - whether the volume mounted. preprocess.py stays shut.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: Database layer and schema

**Files:**
- Create: `backend/app/db/__init__.py`, `connection.py`, `migrate.py`, `schema.sql`
- Create: `backend/tests/test_migrate.py`

**Interfaces:**
- Produces:
  - `app.db.connection.get_conn() -> sqlite3.Connection` (WAL, `busy_timeout=5000`, `foreign_keys=ON`, `row_factory=Row`, autocommit)
  - `app.db.connection.get_db() -> Iterator[sqlite3.Connection]` — the FastAPI dependency
  - `app.db.connection.db_path() -> Path`
  - `app.db.connection.utcnow_iso() -> str` — the single timestamp format, `2026-08-16T14:30:00Z`
  - `app.db.migrate.migrate(conn: sqlite3.Connection | None = None) -> list[str]`

- [ ] **Step 1: Port the database layer**

```bash
mkdir -p backend/app/db
git show dev:backend/app/db/__init__.py   > backend/app/db/__init__.py
git show dev:backend/app/db/connection.py > backend/app/db/connection.py
git show dev:backend/app/db/migrate.py    > backend/app/db/migrate.py
git show dev:backend/app/db/schema.sql    > backend/app/db/schema.sql
```

- [ ] **Step 2: Write the failing test**

Create `backend/tests/test_migrate.py`:

```python
"""The schema applies cleanly, twice, and carries the two staging additions."""
from __future__ import annotations

from app.db.migrate import TABLES, migrate


def test_migrate_creates_every_table(db):
    names = migrate(db)

    for table in TABLES:
        assert table in names


def test_migrate_is_idempotent(db):
    """It runs on every startup. A second run must never lose data."""
    db.execute(
        "INSERT INTO settings (key, value) VALUES ('edit_mode', 'request')"
    )

    migrate(db)

    row = db.execute("SELECT value FROM settings WHERE key='edit_mode'").fetchone()
    assert row["value"] == "request"


def test_packs_carries_the_phase_from_the_filename(db):
    """The real pack names files query-p1-15-qa.txt. The submission filename has
    to reproduce that p1, so it has to be stored."""
    columns = {r["name"] for r in db.execute("PRAGMA table_info(packs)")}

    assert "phase" in columns


def test_tasks_can_carry_import_warnings(db):
    """A TRAKE file with non-sequential E numbers imports with a warning. The
    warning has to survive from the preview screen to the board, not vanish at
    commit time."""
    columns = {r["name"] for r in db.execute("PRAGMA table_info(tasks)")}

    assert "import_warnings" in columns
```

- [ ] **Step 3: Run the test to verify it fails**

```bash
cd backend && ./venv/Scripts/python.exe -m pytest tests/test_migrate.py -v
```

Expected: the last two FAIL — `phase` and `import_warnings` do not exist yet.

- [ ] **Step 4: Add the two columns to the schema**

In `backend/app/db/schema.sql`, inside `CREATE TABLE IF NOT EXISTS packs`, add after
`round_label`:

```sql
  phase            TEXT,               -- 'p1' from query-p1-15-qa.txt; reproduced on export
```

Inside `CREATE TABLE IF NOT EXISTS tasks`, add after `event_labels`:

```sql
  import_warnings  TEXT,               -- JSON ["event numbers are not sequential …"]
```

- [ ] **Step 5: Delete the stale development database**

`backend/app/data/app.db` is a leftover from work on `dev`. It is gitignored, holds nothing
worth keeping, and — because every statement in `schema.sql` is `IF NOT EXISTS` — it would
**not** receive the two new columns. Leaving it in place produces a confusing
`no such column: phase` at run time.

```bash
rm -f backend/app/data/app.db backend/app/data/app.db-shm \
      backend/app/data/app.db-wal backend/app/data/app.db.bak
rm -rf backend/app/data/packs
```

- [ ] **Step 6: Run the tests to verify they pass**

```bash
cd backend && ./venv/Scripts/python.exe -m pytest tests/test_migrate.py -v
```

Expected: 4 passed.

- [ ] **Step 7: Commit**

```bash
git add backend/app/db backend/tests/test_migrate.py
git commit -m "SQLite schema and connection helper

Ports dev's schema with two additions the real organizer files forced. packs.phase
stores the p1 in query-p1-15-qa.txt so the submission filename can reproduce it,
and tasks.import_warnings carries a parse anomaly from the preview screen through
to the board - one file in the real pack has two E2 labels and no E3, and that has
to stay visible rather than being absorbed at commit time.

Schema statements are all IF NOT EXISTS, so the stale dev database on this machine
would never have received the new columns. Removed it.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 7: Authentication — TST-2, TST-3

**Files:**
- Create: `backend/app/auth/__init__.py`, `passwords.py`, `sessions.py`, `deps.py`, `bootstrap.py`
- Create: `backend/app/routers/__init__.py`, `schemas.py`, `auth.py`
- Create: `backend/tests/test_auth.py`

**Interfaces:**
- Consumes: `app.db.connection.get_conn`, `get_db`, `utcnow_iso`; `app.config.load_settings`.
- Produces:
  - `app.auth.passwords.hash_password(plaintext: str) -> str`
  - `app.auth.passwords.verify_password(password_hash: str, plaintext: str) -> bool`
  - `app.auth.passwords.burn_time() -> None`
  - `app.auth.passwords.generate_password(groups: int = 3, size: int = 4) -> str`
  - `app.auth.sessions.create_session(conn, user_id: int) -> str`
  - `app.auth.sessions.resolve_session(conn, token: str) -> sqlite3.Row | None`
  - `app.auth.sessions.delete_session(conn, token: str) -> None`
  - `app.auth.deps.active_user` / `app.auth.deps.require_admin` — FastAPI dependencies returning `sqlite3.Row`
  - `app.auth.bootstrap.create_admin(username: str, display_name: str) -> str` (returns the plaintext once)
  - `app.routers.schemas.UserOut` with `.from_row(row)`
  - Routes: `POST /api/auth/login`, `POST /api/auth/change-password`, `GET /api/me`

- [ ] **Step 1: Port the auth package and the auth router**

```bash
mkdir -p backend/app/auth backend/app/routers
for f in __init__ passwords sessions deps bootstrap; do
  git show dev:backend/app/auth/$f.py > backend/app/auth/$f.py
done
git show dev:backend/app/routers/__init__.py > backend/app/routers/__init__.py
git show dev:backend/app/routers/schemas.py  > backend/app/routers/schemas.py
git show dev:backend/app/routers/auth.py     > backend/app/routers/auth.py
```

- [ ] **Step 2: Write the failing test**

Create `backend/tests/test_auth.py`:

```python
"""TST-2 and TST-3: the login form is not a username oracle, and the forced
password change actually blocks."""
from __future__ import annotations

from tests.conftest import auth_headers


def test_wrong_user_and_wrong_password_are_indistinguishable(client, admin):
    """TST-2. Naming which half failed turns the form into a username directory."""
    no_such_user = client.post(
        "/api/auth/login", json={"username": "nobody", "password": "whatever"}
    )
    wrong_password = client.post(
        "/api/auth/login", json={"username": "admin", "password": "wrong-password"}
    )

    assert no_such_user.status_code == 401
    assert wrong_password.status_code == 401
    assert no_such_user.json() == wrong_password.json()


def test_forced_change_blocks_everything_except_me(client, member):
    """TST-3. The member fixture has NOT changed their password yet."""
    headers = auth_headers(member["token"])

    me = client.get("/api/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["user"]["must_change_password"] is True

    blocked = client.get("/api/admin/users", headers=headers)
    assert blocked.status_code == 403


def test_changing_the_password_clears_the_flag(client, member):
    headers = auth_headers(member["token"])

    response = client.post(
        "/api/auth/change-password",
        json={"current_password": member["password"], "new_password": "chosen-pw-7k"},
        headers=headers,
    )
    assert response.status_code == 200

    # Re-read from the server rather than assuming: the client must never
    # disagree with the server about what is allowed.
    me = client.get("/api/me", headers=headers).json()
    assert me["user"]["must_change_password"] is False


def test_a_dead_token_is_rejected(client, admin):
    response = client.get("/api/me", headers=auth_headers("not-a-real-token"))

    assert response.status_code == 401
```

- [ ] **Step 3: Run the test to verify it fails**

```bash
cd backend && ./venv/Scripts/python.exe -m pytest tests/test_auth.py -v
```

Expected: every test ERRORs — `app.main` does not include the auth router yet, so
`/api/auth/login` is a 404 and the `admin` fixture's assertion fires.

- [ ] **Step 4: Wire the router into the application**

In `backend/app/main.py`, add these imports beside the existing ones:

```python
import sys
from contextlib import asynccontextmanager

from app.config import DEMO_MODE, indexes_present, settings
from app.db.connection import get_conn
from app.db.migrate import migrate
from app.guard import enforce_production_safety
from app.routers import auth as auth_router
```

Add the lifespan handler above `app = FastAPI(...)`:

```python
@asynccontextmanager
async def lifespan(_: FastAPI):
    # Every statement in schema.sql is IF NOT EXISTS, so this is safe on every
    # boot and a fresh deploy needs no separate migration step.
    migrate()

    conn = get_conn()
    try:
        # The guard's question is "would this process serve results that are not
        # real search results". On this branch that reduces to whether the
        # indexes are actually there — see config.indexes_present().
        violations = enforce_production_safety(settings, not indexes_present(), conn)
    finally:
        conn.close()
    if violations:
        for violation in violations:
            print(f"REFUSING TO START: {violation}", file=sys.stderr)
        raise SystemExit(1)

    yield
```

Pass it to the constructor — `app = FastAPI(..., lifespan=lifespan)` — replace the
hardcoded CORS list with `allow_origins=list(settings.cors_origins)`, and add below the
middleware:

```python
app.include_router(auth_router.router)
```

**Do not touch the five search endpoints or `_make_response`.**

- [ ] **Step 5: Run the tests to verify they pass**

```bash
cd backend && ./venv/Scripts/python.exe -m pytest tests/test_auth.py tests/test_harness.py -v
```

Expected: 4 passed in `test_auth.py`, 2 passed in `test_harness.py` — the second file
proves the five search routes survived the edit.

- [ ] **Step 6: Commit**

```bash
git add backend/app/auth backend/app/routers backend/app/main.py backend/tests/test_auth.py
git commit -m "Login, sessions and the forced password change

argon2id, one-shot plaintext, and a login form that returns the same body for a
wrong username as for a wrong password - naming which half failed would turn it
into a username directory.

main.py grows a lifespan that migrates and then asks the guard whether this
process should serve traffic at all. The five search endpoints are untouched;
test_harness.py asserts that on every run.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 8: Admin — members

**Files:**
- Create: `backend/app/routers/admin_users.py`
- Create: `backend/tests/test_admin_users.py`
- Modify: `backend/app/main.py`

**Interfaces:**
- Consumes: `require_admin`, `hash_password`, `generate_password`, `UserOut`.
- Produces: `POST /api/admin/users/bulk` · `POST /api/admin/users/{id}/reset-password` ·
  `PATCH /api/admin/users/{id}` · `GET /api/admin/users`.
  The bulk response shape is `{"created": [{"username", "display_name", "password"}]}`.

- [ ] **Step 1: Port the router**

```bash
git show dev:backend/app/routers/admin_users.py > backend/app/routers/admin_users.py
```

- [ ] **Step 2: Write the failing test**

Create `backend/tests/test_admin_users.py`:

```python
from __future__ import annotations

from tests.conftest import auth_headers


def test_bulk_create_returns_plaintext_exactly_once(client, admin):
    response = client.post(
        "/api/admin/users/bulk",
        json={"members": [
            {"username": "lan", "display_name": "Lan"},
            {"username": "huy", "display_name": "Huy"},
        ]},
        headers=auth_headers(admin["token"]),
    )
    assert response.status_code == 201

    created = response.json()["created"]
    assert len(created) == 2
    assert all(row["password"] for row in created)

    # There is no endpoint that returns it again. If one existed, the server
    # would have to be keeping the plaintext.
    listed = client.get("/api/admin/users", headers=auth_headers(admin["token"]))
    assert listed.status_code == 200
    assert all("password" not in row for row in listed.json()["users"])


def test_created_members_can_log_in(client, admin):
    response = client.post(
        "/api/admin/users/bulk",
        json={"members": [{"username": "trang", "display_name": "Trang"}]},
        headers=auth_headers(admin["token"]),
    )
    created = response.json()["created"][0]

    login = client.post(
        "/api/auth/login",
        json={"username": "trang", "password": created["password"]},
    )

    assert login.status_code == 200
    assert login.json()["user"]["must_change_password"] is True


def test_a_member_cannot_create_members(client, admin, member):
    """A member who has changed their password is still not an admin."""
    client.post(
        "/api/auth/change-password",
        json={"current_password": member["password"], "new_password": "chosen-pw-7k"},
        headers=auth_headers(member["token"]),
    )

    response = client.post(
        "/api/admin/users/bulk",
        json={"members": [{"username": "x", "display_name": "X"}]},
        headers=auth_headers(member["token"]),
    )

    assert response.status_code == 403


def test_password_hash_never_leaves_the_process(client, admin):
    response = client.get("/api/admin/users", headers=auth_headers(admin["token"]))

    assert "password_hash" not in response.text
```

- [ ] **Step 3: Run the test to verify it fails**

```bash
cd backend && ./venv/Scripts/python.exe -m pytest tests/test_admin_users.py -v
```

Expected: FAIL with 404 — the router is not included.

- [ ] **Step 4: Include the router**

In `backend/app/main.py`, add `from app.routers import admin_users as admin_users_router`
and `app.include_router(admin_users_router.router)` beside the auth router.

- [ ] **Step 5: Run the tests to verify they pass**

```bash
cd backend && ./venv/Scripts/python.exe -m pytest tests/test_admin_users.py -v
```

Expected: 4 passed.

- [ ] **Step 6: Commit**

```bash
git add backend/app/routers/admin_users.py backend/app/main.py backend/tests/test_admin_users.py
git commit -m "Admin: bulk-create members, reset, disable

Plaintext passwords appear in exactly one response and are never retrievable
again - an endpoint that could return them would mean the server was keeping
them. The credential CSV is therefore built client-side from that one response.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 9: Settings

**Files:**
- Create: `backend/app/settings_store.py`
- Create: `backend/app/routers/admin_settings.py`
- Create: `backend/tests/test_settings.py`
- Modify: `backend/app/main.py`

**Interfaces:**
- Produces:
  - `app.settings_store.DEFAULTS: dict[str, tuple[Any, type]]`
  - `app.settings_store.all_settings(conn) -> dict[str, Any]`
  - `app.settings_store.public_settings(conn) -> dict[str, Any]`
  - `app.settings_store.set_many(conn, updates: dict[str, Any]) -> dict[str, Any]`
  - `app.settings_store.UnknownSettingError`, `InvalidSettingError`
  - `GET /api/settings` · `PUT /api/admin/settings`

- [ ] **Step 1: Port both files**

```bash
git show dev:backend/app/settings_store.py    > backend/app/settings_store.py
git show dev:backend/app/routers/settings.py  > backend/app/routers/admin_settings.py
```

- [ ] **Step 2: Write the failing test**

Create `backend/tests/test_settings.py`:

```python
from __future__ import annotations

from tests.conftest import auth_headers


def test_export_filename_pattern_carries_the_phase(db):
    """The real pack names files query-p1-15-qa.txt. dev's default pattern had
    no phase placeholder, so every exported filename would have lost the p1."""
    from app.settings_store import DEFAULTS

    default, kind = DEFAULTS["export.filename_pattern"]

    assert kind is str
    assert "{phase}" in default
    assert "{code}" in default
    assert "{type}" in default


def test_export_defaults_match_the_spec(db):
    from app.settings_store import all_settings

    values = all_settings(db)

    assert values["export.delimiter"] == ","
    assert values["export.header"] is False
    assert values["export.line_ending"] == "LF"
    assert values["export.encoding"] == "utf-8"   # no BOM
    assert values["export.rows_per_query"] == 100


def test_an_unknown_key_is_rejected(db):
    """A typo'd key that persists quietly is a setting the admin believes they
    changed and did not."""
    import pytest

    from app.settings_store import UnknownSettingError, set_many

    with pytest.raises(UnknownSettingError):
        set_many(db, {"export.delimeter": ";"})


def test_the_export_keys_are_readable_by_a_member(client, admin, member):
    """The Export screen needs them and members open it."""
    client.post(
        "/api/auth/change-password",
        json={"current_password": member["password"], "new_password": "chosen-pw-7k"},
        headers=auth_headers(member["token"]),
    )

    response = client.get("/api/settings", headers=auth_headers(member["token"]))

    assert response.status_code == 200
    assert "export.rows_per_query" in response.json()
```

- [ ] **Step 3: Run the test to verify it fails**

```bash
cd backend && ./venv/Scripts/python.exe -m pytest tests/test_settings.py -v
```

Expected: the first test FAILS — the ported default is `query-{id}-{type}.csv`.

- [ ] **Step 4: Correct the default and include the router**

In `backend/app/settings_store.py`, change the `DEFAULTS` entry:

```python
    # The real pack names its files query-p1-15-qa.txt: a phase, an unpadded
    # code, and a type. The submission filename reuses that stem so a reviewer
    # can line the two up, which means the pattern needs all three placeholders.
    "export.filename_pattern": ("query-{phase}-{code}-{type}.csv", str),
```

In `backend/app/main.py`, add
`from app.routers import admin_settings as admin_settings_router` and
`app.include_router(admin_settings_router.router)`.

- [ ] **Step 5: Run the tests to verify they pass**

```bash
cd backend && ./venv/Scripts/python.exe -m pytest tests/test_settings.py -v
```

Expected: 4 passed.

- [ ] **Step 6: Commit**

```bash
git add backend/app/settings_store.py backend/app/routers/admin_settings.py \
        backend/app/main.py backend/tests/test_settings.py
git commit -m "Settings, with the export filename pattern corrected

Every byte of the submission file is a setting, so a late format change from the
organizer is a form field rather than a rebuild. dev's default filename pattern
was query-{id}-{type}.csv, which has nowhere to put the p1 that the real pack
carries; the pattern now takes phase, code and type.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 10: Front end — session, login, and the screen switch

**Files:**
- Create: `frontend/src/api/base.ts`, `frontend/src/api/auth.ts`
- Create: `frontend/src/store/authStore.ts`
- Create: `frontend/src/pages/Login.tsx`, `frontend/src/pages/ChangePassword.tsx`
- Create: `frontend/src/pages/Search.tsx`
- Create: `frontend/src/api/auth.test.ts`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/types/api.ts`

**Interfaces:**
- Produces:
  - `apiFetch<T>(path: string, init?: RequestInit): Promise<T>` — adds the bearer token, 401 clears the store
  - `ApiRequestError` with `.status` and `.body` (the **whole** parsed body, not just `detail`)
  - `API_BASE_URL`
  - `useAuthStore` → `{ token, user, setSession, setUser, clear }`
  - `login(username, password)`, `changePassword(current, next)`, `me()`
  - `AuthUser = { id, username, display_name, role: "admin" | "member", must_change_password }`

- [ ] **Step 1: Port the client layer**

```bash
mkdir -p frontend/src/api frontend/src/pages
git show dev:frontend/src/api/base.ts        > frontend/src/api/base.ts
git show dev:frontend/src/api/auth.ts        > frontend/src/api/auth.ts
git show dev:frontend/src/api/auth.test.ts   > frontend/src/api/auth.test.ts
git show dev:frontend/src/store/authStore.ts > frontend/src/store/authStore.ts
git show dev:frontend/src/pages/Login.tsx    > frontend/src/pages/Login.tsx
git show dev:frontend/src/pages/ChangePassword.tsx > frontend/src/pages/ChangePassword.tsx
```

In `frontend/src/api/base.ts`, delete the two comment paragraphs that mention
`harness_check.py` — that checker is not on this branch and the comment would send a
reader looking for a file that does not exist. Keep the code exactly as it is.

- [ ] **Step 2: Add the auth types**

Append to `frontend/src/types/api.ts` (do **not** modify anything already in the file — the
existing search client must keep working):

```ts
// ─────────────────────────────────────────────────────────────────────────────
//  Collaboration layer — added on staging. The search types above are unchanged
//  and the existing VideoSearchApi still talks to the same five endpoints.
// ─────────────────────────────────────────────────────────────────────────────

export interface AuthUser {
  id: number;
  username: string;
  display_name: string;
  role: "admin" | "member";
  must_change_password: boolean;
  disabled?: boolean;
}

export interface LoginResponse {
  token: string;
  user: AuthUser;
}

export interface MeResponse {
  user: AuthUser;
  settings: Record<string, unknown>;
  server_time: string;
}

export type SearchMode = "ensemble" | "beit3" | "clip";
```

- [ ] **Step 3: Move the current search screen out of `App.tsx`, verbatim**

Create `frontend/src/pages/Search.tsx` containing the **entire current body** of
`App.tsx`, renamed:

```ts
// The pre-redesign search screen, moved here unchanged so App.tsx can become a
// screen switch. Slice S3 replaces it with the three-column Workspace; until
// then it stays reachable and working, because it is the only screen that can
// currently run a search.
export default function Search() {
  /* … the exact contents of the old App() … */
}
```

Delete the `SubmitForm` import and its JSX if Task 3 left one behind.

- [ ] **Step 4: Write the failing test**

Create `frontend/src/App.test.tsx`… **no.** `App.tsx` needs a DOM and this project's
vitest runs in `node`. Instead assert the routing rule as a pure function. Create
`frontend/src/pages/screenFor.ts`:

```ts
import type { AuthUser } from "../types/api";

export type Screen =
  | "login"
  | "change-password"
  | "board"
  | "workspace"
  | "export"
  | "members"
  | "packs"
  | "settings";

/**
 * Which screen a session is entitled to see, as a pure function so it can be
 * tested without a DOM.
 *
 * The order matters: an unauthenticated user is never anything else, and a user
 * who must change their password sees nothing else — the backend answers 403 to
 * every other route anyway, so rendering one would only show an error.
 */
export function screenFor(
  user: AuthUser | null,
  token: string | null,
  requested: Screen
): Screen {
  if (!token || !user) return "login";
  if (user.must_change_password) return "change-password";
  if (user.role !== "admin" && ["members", "packs", "settings"].includes(requested)) {
    return "board";
  }
  return requested;
}
```

Create `frontend/src/pages/screenFor.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { screenFor } from "./screenFor";
import type { AuthUser } from "../types/api";

const member: AuthUser = {
  id: 2, username: "nam", display_name: "Nam",
  role: "member", must_change_password: false,
};
const admin: AuthUser = { ...member, id: 1, username: "admin", role: "admin" };

describe("screenFor", () => {
  it("sends a session with no token to login", () => {
    expect(screenFor(null, null, "board")).toBe("login");
    expect(screenFor(member, null, "board")).toBe("login");
  });

  it("pins a user who must change their password to that screen", () => {
    const forced = { ...member, must_change_password: true };
    expect(screenFor(forced, "t", "board")).toBe("change-password");
    expect(screenFor(forced, "t", "workspace")).toBe("change-password");
  });

  it("keeps a member out of the admin screens", () => {
    expect(screenFor(member, "t", "members")).toBe("board");
    expect(screenFor(member, "t", "packs")).toBe("board");
  });

  it("lets an admin through", () => {
    expect(screenFor(admin, "t", "packs")).toBe("packs");
  });

  it("passes any other request through untouched", () => {
    expect(screenFor(member, "t", "workspace")).toBe("workspace");
  });
});
```

- [ ] **Step 5: Run the test to verify it fails**

```bash
cd frontend && npm run test
```

Expected: FAIL — `screenFor.ts` does not exist yet if you wrote the test first; otherwise
the tests pass immediately, in which case delete `screenFor.ts`, re-run to see red, and
restore it. A test never seen red is not a test.

- [ ] **Step 6: Rewrite `App.tsx` as the screen switch**

```tsx
import { useEffect, useState } from "react";

import { me } from "./api/auth";
import ChangePassword from "./pages/ChangePassword";
import Login from "./pages/Login";
import Search from "./pages/Search";
import { screenFor, type Screen } from "./pages/screenFor";
import { useAuthStore } from "./store/authStore";

/**
 * The whole of routing. A router library buys nothing while there are no URLs
 * worth sharing; slices S3 and S5 add the Board, Workspace and Export screens
 * to this switch.
 *
 * Every hook runs before the first return, because the number of hooks a
 * component calls may not change between renders.
 */
export default function App() {
  const token = useAuthStore((state) => state.token);
  const user = useAuthStore((state) => state.user);
  const setUser = useAuthStore((state) => state.setUser);
  const [requested, setRequested] = useState<Screen>("board");

  useEffect(() => {
    if (!token) return;
    // A token restored from localStorage may already be dead, and only the
    // server knows. apiFetch clears the store on 401, so this both refreshes
    // the user and evicts a stale session on reload.
    void me().then((response) => setUser(response.user)).catch(() => undefined);
  }, [token, setUser]);

  const screen = screenFor(user, token, requested);

  if (screen === "login") return <Login />;
  if (screen === "change-password") return <ChangePassword />;

  // S1 has no Board yet. The pre-redesign search screen stands in so the branch
  // is never in a state where nobody can search. S3 replaces this line.
  return <Search onNavigate={setRequested} />;
}
```

Give `Search` an optional `onNavigate` prop it ignores for now, so the signature does not
change again in S3.

- [ ] **Step 7: Run the tests and the build to verify**

```bash
cd frontend && npm run test && npm run build
```

Expected: vitest green, build succeeds.

- [ ] **Step 8: Commit**

```bash
git add frontend/src frontend/package.json
git commit -m "Front end: session, login, and App.tsx as a screen switch

The pre-redesign search screen moves to pages/Search.tsx unchanged and stays
reachable, so the branch is never in a state where nobody can run a search. S3
replaces it with the three-column workspace.

Routing is a pure function, screenFor(), so the two rules that matter - no token
means login, an unchanged password means nothing but the change screen - are
tested without standing up a DOM.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 11: Front end — admin screens

**Files:**
- Create: `frontend/src/api/admin.ts`
- Create: `frontend/src/helpers/credentialsCsv.ts`, `credentialsCsv.test.ts`
- Create: `frontend/src/components/AdminNav.tsx`
- Create: `frontend/src/pages/AdminMembers.tsx`, `AdminSettings.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/App.css`

**Interfaces:**
- Consumes: `apiFetch`, `useAuthStore`, `screenFor`.
- Produces: `credentialsCsv(rows: {username: string; display_name: string; password: string}[]) -> string` — BOM-prefixed, CRLF, quoted.

- [ ] **Step 1: Port the screens and helpers**

```bash
mkdir -p frontend/src/helpers frontend/src/components
git show dev:frontend/src/api/admin.ts                  > frontend/src/api/admin.ts
git show dev:frontend/src/helpers/credentialsCsv.ts     > frontend/src/helpers/credentialsCsv.ts
git show dev:frontend/src/helpers/credentialsCsv.test.ts > frontend/src/helpers/credentialsCsv.test.ts
git show dev:frontend/src/components/AdminNav.tsx       > frontend/src/components/AdminNav.tsx
git show dev:frontend/src/pages/AdminMembers.tsx        > frontend/src/pages/AdminMembers.tsx
git show dev:frontend/src/pages/AdminSettings.tsx       > frontend/src/pages/AdminSettings.tsx
git show dev:frontend/src/App.css                       > frontend/src/App.css
```

`AdminNav.tsx` exports its own `Screen` type on `dev`. Delete that export and have it
import `Screen` from `../pages/screenFor` instead, so there is one definition.

- [ ] **Step 2: Run the ported test to verify it passes**

```bash
cd frontend && npm run test
```

Expected: `credentialsCsv.test.ts` passes. It asserts the BOM — Excel needs it to render
Vietnamese display names, which is the one place in this system a BOM is wanted.

- [ ] **Step 3: Add a test for the case dev's tests do not cover**

Append to `frontend/src/helpers/credentialsCsv.test.ts`:

```ts
it("quotes a display name containing a comma", () => {
  const csv = credentialsCsv([
    { username: "nam", display_name: "Nguyễn, Nam", password: "abcd-efgh" },
  ]);

  expect(csv).toContain('"Nguyễn, Nam"');
});
```

- [ ] **Step 4: Run it to verify it passes**

```bash
cd frontend && npm run test
```

If it fails, fix `credentialsCsv.ts` to quote any field containing the delimiter, a quote,
or a newline, doubling embedded quotes.

- [ ] **Step 5: Add the admin screens to the switch**

In `App.tsx`, import the three screens and add before the final return:

```tsx
  if (screen === "members") return <AdminMembers onNavigate={setRequested} />;
  if (screen === "settings") return <AdminSettings onNavigate={setRequested} />;
```

Render an `Admin` button for `user.role === "admin"` that calls `setRequested("members")`.

- [ ] **Step 6: Verify end to end by hand**

```bash
cd backend && ./venv/Scripts/python.exe -m app.auth.bootstrap admin Admin
cd backend && ./venv/Scripts/python.exe -m uvicorn app.main:app --reload
# in another shell
cd frontend && npm run dev
```

Log in as `admin` with the printed password, change it when forced, open Admin → Members,
create two members, download the CSV, and confirm both can log in.

- [ ] **Step 7: Commit**

```bash
git add frontend/src
git commit -m "Front end: admin members and settings

The credential CSV is built in the browser from the one response that carries
plaintext, and carries a BOM so Excel renders Vietnamese display names - the only
place in this system where a BOM is wanted. The submission file must not have one.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

# Slice S2 — Query import

**Do not port `dev`'s importer.** It was written against a format we invented and is wrong
in five ways (spec §5.2). This slice writes the parser fresh against the committed real
pack.

---

### Task 12: The pack parser — TST-4, TST-5, TST-6

**Files:**
- Create: `backend/app/packs_store.py`
- Create: `backend/tests/test_packs_parse.py`

**Interfaces:**
- Consumes: `tests.fixtures.ORGANIZER_PACK`.
- Produces:
  - `app.packs_store.DEFAULT_PATTERN: str`
  - `app.packs_store.ParsedFile` — dataclass with `filename, matched, phase, code, type, query_text, question_text, n_events, event_labels, warnings, error`
  - `app.packs_store.parse_pack(data: bytes, filename_pattern: str = DEFAULT_PATTERN) -> list[ParsedFile]`
  - `app.packs_store.parse_task_text(task_type: str, raw: str) -> tuple[str, str | None, list[str], list[str]]` returning `(query_text, question_text, event_labels, warnings)`
  - `app.packs_store.PatternError`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_packs_parse.py`:

```python
"""TST-4, TST-5, TST-6 — parsing the REAL organizer pack.

Every assertion here is against sample-data/query-p1-groupA.zip, not against a
shape we invented. dev's importer was built on a guess and is wrong in five
ways; this file is what stops that happening a second time.
"""
from __future__ import annotations

import pytest

from app.packs_store import DEFAULT_PATTERN, parse_pack, parse_task_text
from tests.fixtures import ORGANIZER_PACK


@pytest.fixture(scope="module")
def parsed():
    return parse_pack(ORGANIZER_PACK.read_bytes(), DEFAULT_PATTERN)


def test_every_file_in_the_real_pack_matches(parsed):
    """TST-4. 24 files, all .txt, all matched."""
    assert len(parsed) == 24
    unmatched = [p.filename for p in parsed if not p.matched]
    assert unmatched == []


def test_codes_are_not_padded_and_may_have_gaps(parsed):
    """dev assumed 01..20 contiguous. The real pack has 1..25 with no 3."""
    codes = sorted(int(p.code) for p in parsed)

    assert codes[0] == 1
    assert 3 not in codes
    assert max(codes) == 25
    # Stored as written, not re-padded: the export filename has to reproduce it.
    assert all(not p.code.startswith("0") for p in parsed)


def test_the_phase_is_captured(parsed):
    assert {p.phase for p in parsed} == {"p1"}


def test_kis_query_is_the_whole_file_including_line_breaks(parsed):
    """7 of 24 files are multi-line. dev would have kept only the first line."""
    multi = [p for p in parsed if p.type == "kis" and "\n" in (p.query_text or "")]

    assert multi, "expected multi-line KIS files in the real pack"
    sample = next(p for p in parsed if p.code == "14")
    assert sample.query_text.count("\n") == 2
    assert sample.query_text.startswith("Đoạn clip bắt đầu với cảnh một tác phẩm")
    assert sample.query_text.rstrip().endswith("2 cột khói màu hồng")


def test_qa_question_is_inferred_from_the_trailing_sentence(parsed):
    """TST-6. The question is the last sentence of the paragraph, not its own
    line — including when a parenthetical follows the question mark."""
    q15 = next(p for p in parsed if p.code == "15")
    assert q15.type == "qa"
    assert q15.question_text == "Hỏi xã này có tên là gì? (tại thời điểm đó)"
    # The full paragraph stays as the query; the question is additional, not a
    # replacement. INV-4: organizer text is never rewritten.
    assert q15.query_text.startswith("Đoạn video về một chương trình từ thiện")

    q19 = next(p for p in parsed if p.code == "19")
    assert q19.question_text == "Hai câu thơ đó là gì?"


def test_trake_events_are_counted_by_position(parsed):
    q4 = next(p for p in parsed if p.code == "4")

    assert q4.type == "trake"
    assert q4.n_events == 4
    assert q4.event_labels[0].startswith("Khoảnh khắc đầu tiên bột được bỏ")
    # No context line before E1 in this file, so the query is the events' subject.
    assert q4.warnings == []


def test_trake_context_line_becomes_the_query(parsed):
    q16 = next(p for p in parsed if p.code == "16")

    assert q16.n_events == 4
    assert q16.query_text.startswith("Đoạn video múa lân")
    assert "E1:" not in q16.query_text


def test_non_sequential_event_numbers_warn_but_still_import(parsed):
    """TST-5. query-p1-18-trake.txt ships an organizer typo: E1, E2, E2, E4.

    Counting by position gives the right number of events. Trusting the numbers
    would mismatch every label after the duplicate, and a user would type frames
    for one moment into a slot labelled with another.
    """
    q18 = next(p for p in parsed if p.code == "18")

    assert q18.n_events == 4
    assert len(q18.event_labels) == 4
    assert any("not sequential" in w for w in q18.warnings)
    assert any("E1, E2, E2, E4" in w for w in q18.warnings)


def test_an_unmatched_file_is_reported_not_dropped():
    import io
    import zipfile

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("query-p1-1-kis.txt", "một câu truy vấn")
        archive.writestr("readme.txt", "ignore me")

    parsed = parse_pack(buffer.getvalue(), DEFAULT_PATTERN)

    assert len(parsed) == 2
    rejected = next(p for p in parsed if p.filename == "readme.txt")
    assert rejected.matched is False
    assert "does not match" in rejected.error


def test_a_bom_is_stripped_from_the_query():
    """Nothing in the real pack has one, but a re-saved file would."""
    query, question, events, warnings = parse_task_text("kis", "﻿câu truy vấn")

    assert query == "câu truy vấn"
    assert question is None
    assert events == []


def test_an_empty_file_warns():
    query, _question, _events, warnings = parse_task_text("kis", "   \n  ")

    assert query == ""
    assert any("empty" in w for w in warnings)
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd backend && ./venv/Scripts/python.exe -m pytest tests/test_packs_parse.py -v
```

Expected: collection error — `No module named 'app.packs_store'`.

- [ ] **Step 3: Write the parser**

Create `backend/app/packs_store.py`:

```python
"""Reads the organizer's query pack.

Written against sample-data/query-p1-groupA.zip - a real pack, AIC 2025 Round 1 -
rather than against a template we invented. The previous design guessed, and
guessed wrong in five ways: the files are .txt not .csv, codes are unpadded and
have gaps, KIS/Q&A queries are the whole file rather than its first line, the
Q&A question is the trailing sentence of a paragraph rather than its own line,
and TRAKE events carry E1:..EN: prefixes.

Everything the admin can express lives in the filename regex. Everything they
cannot lives in parse_task_text(), deliberately one function, so that the day the
organizer publishes a different layout the change is small and obvious.
"""
from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass, field

#: Pre-filled in the Admin form. The named groups are the contract: whatever the
#: admin types must still produce `code` and `type`; `phase` is optional and is
#: reproduced in the export filename when present.
DEFAULT_PATTERN = r"query-(?P<phase>p\d+)-(?P<code>\d+)-(?P<type>kis|qa|trake)\.txt"

TASK_TYPES = ("kis", "qa", "trake")

#: "E1:", "E2 .", "e3:" — the number is captured but never used for counting.
_EVENT_LINE = re.compile(r"^\s*E\s*(\d+)\s*[:.]\s*(.*)$", re.IGNORECASE)

#: Where a sentence can begin, used to find the start of the trailing question.
_SENTENCE_END = (".", "!", "?", "\n")


class PatternError(ValueError):
    """The admin's regex cannot be used."""


@dataclass
class ParsedFile:
    filename: str
    matched: bool
    phase: str | None = None
    code: str | None = None
    type: str | None = None
    query_text: str | None = None
    question_text: str | None = None
    n_events: int | None = None
    event_labels: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    error: str | None = None


def compile_pattern(filename_pattern: str) -> re.Pattern[str]:
    """Accepts both .NET-style (?<name>…) and Python (?P<name>…) group syntax.

    The redesign spec wrote its example the .NET way and an admin copying it
    would otherwise get an unhelpful `unknown extension ?<` from `re`.
    """
    normalised = re.sub(r"\(\?<(?![=!])", "(?P<", filename_pattern)
    try:
        compiled = re.compile(normalised)
    except re.error as exc:
        raise PatternError(f"Not a valid regular expression: {exc}") from exc

    missing = {"code", "type"} - set(compiled.groupindex)
    if missing:
        raise PatternError(
            "The pattern must capture " + " and ".join(sorted(missing))
            + " as named groups, e.g. (?P<code>\\d+)"
        )
    return compiled


def _infer_question(text: str) -> str | None:
    """The Q&A question: the last sentence of the paragraph.

    Real examples this has to satisfy:

      "…tại một xã thuộc tỉnh Khánh Hòa. Hỏi xã này có tên là gì? (tại thời điểm đó)"
        -> "Hỏi xã này có tên là gì? (tại thời điểm đó)"

    So the rule cannot be "cut at the question mark": a parenthetical qualifier
    after it changes the answer. Take from the start of the sentence containing
    the LAST question mark, through to the end of the text.
    """
    last_q = text.rfind("?")
    if last_q == -1:
        return None

    start = max((text.rfind(ch, 0, last_q) for ch in _SENTENCE_END), default=-1) + 1
    return text[start:].strip() or None


def _parse_trake(raw: str) -> tuple[str, list[str], list[str]]:
    """Returns (query_text, event_labels, warnings).

    Events are the E-prefixed lines IN FILE ORDER. The number after the E is
    read only to check it, never to index: query-p1-18-trake.txt in the real
    pack is E1, E2, E2, E4. Trusting those numbers there would leave every label
    after the duplicate attached to the wrong moment, and TRAKE scores per
    moment - a mislabelled slot is a wrong frame submitted with confidence.
    """
    context: list[str] = []
    labels: list[str] = []
    numbers: list[str] = []

    for line in raw.splitlines():
        match = _EVENT_LINE.match(line)
        if match:
            numbers.append(match.group(1))
            labels.append(match.group(2).strip())
        elif not labels:
            context.append(line)
        elif line.strip():
            # Continuation of the previous event label, wrapped onto a new line.
            labels[-1] = f"{labels[-1]} {line.strip()}".strip()

    warnings: list[str] = []
    expected = [str(i) for i in range(1, len(numbers) + 1)]
    if numbers and numbers != expected:
        warnings.append(
            "event numbers are not sequential (E"
            + ", E".join(numbers)
            + f") - {len(numbers)} events were taken from line order instead, "
            "so check the labels against the source file"
        )
    if not labels:
        warnings.append("no E-prefixed event lines found in a TRAKE file")

    return "\n".join(context).strip(), labels, warnings


def parse_task_text(task_type: str, raw: str) -> tuple[str, str | None, list[str], list[str]]:
    """Turn one file's text into (query_text, question_text, event_labels, warnings).

    This is the one function that encodes assumptions the admin's regex cannot
    express. When the organizer publishes a different layout, it is the only
    function that has to change.
    """
    text = raw.lstrip("﻿").replace("\r\n", "\n").replace("\r", "\n").strip()

    warnings: list[str] = []
    if not text:
        warnings.append("file is empty")
        return "", None, [], warnings

    if task_type == "trake":
        query, labels, trake_warnings = _parse_trake(text)
        if not query:
            # Some TRAKE files start straight at E1: with no framing sentence.
            # The events are then the whole description, which is legitimate.
            query = text
        return query, None, labels, warnings + trake_warnings

    if task_type == "qa":
        question = _infer_question(text)
        if question is None:
            warnings.append(
                "no question mark found - set the question by hand before committing"
            )
        return text, question, [], warnings

    return text, None, [], warnings


def parse_pack(data: bytes, filename_pattern: str = DEFAULT_PATTERN) -> list[ParsedFile]:
    """Parse every entry of the uploaded archive. Never raises on one bad file."""
    pattern = compile_pattern(filename_pattern)
    parsed: list[ParsedFile] = []

    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise PatternError(f"Not a readable ZIP archive: {exc}") from exc

    with archive:
        for info in sorted(archive.infolist(), key=lambda i: i.filename):
            if info.is_dir():
                continue
            # Nested layouts are legal; the rule applies to the base name.
            name = info.filename.rsplit("/", 1)[-1]
            if not name or name.startswith("."):
                continue

            match = pattern.fullmatch(name) or pattern.search(name)
            if not match:
                parsed.append(ParsedFile(
                    filename=name, matched=False,
                    error="filename does not match the pattern",
                ))
                continue

            groups = match.groupdict()
            task_type = (groups.get("type") or "").lower()
            if task_type not in TASK_TYPES:
                parsed.append(ParsedFile(
                    filename=name, matched=False,
                    error=f"unknown task type {task_type!r}; expected one of "
                          + ", ".join(TASK_TYPES),
                ))
                continue

            raw = archive.read(info).decode("utf-8", errors="replace")
            query, question, labels, warnings = parse_task_text(task_type, raw)

            parsed.append(ParsedFile(
                filename=name,
                matched=True,
                phase=groups.get("phase"),
                code=groups.get("code"),
                type=task_type,
                query_text=query,
                question_text=question,
                n_events=len(labels) if task_type == "trake" else None,
                event_labels=labels,
                warnings=warnings,
            ))

    return parsed
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
cd backend && ./venv/Scripts/python.exe -m pytest tests/test_packs_parse.py -v
```

Expected: 11 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/packs_store.py backend/tests/test_packs_parse.py
git commit -m "Parse the organizer's real query pack

Written against sample-data/query-p1-groupA.zip rather than against the template
the previous design guessed at, which was wrong in five ways. The two that would
have cost the most: KIS and Q&A queries are the whole file, so keeping only the
first line would have thrown away two thirds of the hardest questions; and TRAKE
events carry E1:..EN: prefixes, which the previous parser would not have seen at
all.

Event counting is by line position, never by the E number. One real file is
E1, E2, E2, E4 - an organizer typo. Counting by number gives the right total by
luck and the wrong labels for certain, and a mislabelled slot means a frame typed
for the wrong moment. The anomaly is reported as a warning instead; the software
does not quietly repair the organizer's data.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 13: Pack preview and commit endpoints

**Files:**
- Create: `backend/app/routers/admin_packs.py`
- Create: `backend/tests/test_admin_packs.py`
- Modify: `backend/app/main.py`

**Interfaces:**
- Consumes: `parse_pack`, `ParsedFile`, `require_admin`, `get_db`, `utcnow_iso`.
- Produces:
  - `POST /api/admin/packs/preview` (multipart: `file`, `filename_pattern`) → `{preview_token, source_filename, files: [...]}`
  - `POST /api/admin/packs/commit` → `201 {pack_id, tasks_created, skipped}`
  - Commit body: `{preview_token, round_label, deadline_minutes, overrides: {filename: {question_text}}}`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_admin_packs.py`:

```python
from __future__ import annotations

import json

from tests.conftest import auth_headers
from tests.fixtures import ORGANIZER_PACK


def _preview(client, admin):
    return client.post(
        "/api/admin/packs/preview",
        files={"file": ("query-p1-groupA.zip", ORGANIZER_PACK.read_bytes(),
                        "application/zip")},
        headers=auth_headers(admin["token"]),
    )


def test_preview_reports_every_file_without_writing_anything(client, admin, db):
    response = _preview(client, admin)

    assert response.status_code == 200
    body = response.json()
    assert len(body["files"]) == 24
    assert body["preview_token"]

    # Nothing is written until commit.
    assert client.get("/api/board", headers=auth_headers(admin["token"])).json()["tasks"] == []


def test_commit_creates_one_task_per_matched_file(client, admin):
    token = _preview(client, admin).json()["preview_token"]

    response = client.post(
        "/api/admin/packs/commit",
        json={"preview_token": token, "round_label": "Round 1",
              "deadline_minutes": None},
        headers=auth_headers(admin["token"]),
    )

    assert response.status_code == 201
    assert response.json()["tasks_created"] == 24
    assert response.json()["skipped"] == 0


def test_the_warning_survives_the_commit(client, admin):
    """The E1,E2,E2,E4 anomaly must reach the board, not stop at the preview."""
    token = _preview(client, admin).json()["preview_token"]
    client.post(
        "/api/admin/packs/commit",
        json={"preview_token": token, "round_label": "Round 1",
              "deadline_minutes": None},
        headers=auth_headers(admin["token"]),
    )

    tasks = client.get("/api/board", headers=auth_headers(admin["token"])).json()["tasks"]
    task18 = next(t for t in tasks if t["code"] == "18")

    assert task18["n_events"] == 4
    assert any("not sequential" in w for w in task18["import_warnings"])


def test_an_override_replaces_the_inferred_question(client, admin):
    token = _preview(client, admin).json()["preview_token"]

    client.post(
        "/api/admin/packs/commit",
        json={
            "preview_token": token,
            "round_label": "Round 1",
            "deadline_minutes": None,
            "overrides": {"query-p1-15-qa.txt": {"question_text": "Tên xã là gì?"}},
        },
        headers=auth_headers(admin["token"]),
    )

    tasks = client.get("/api/board", headers=auth_headers(admin["token"])).json()["tasks"]
    task15 = next(t for t in tasks if t["code"] == "15")

    assert task15["question_text"] == "Tên xã là gì?"
    # INV-4: the override changes the inferred question only. The organizer's
    # own text is untouched.
    assert task15["query_text"].startswith("Đoạn video về một chương trình từ thiện")


def test_reimporting_the_same_pack_creates_no_duplicates(client, admin):
    for _ in range(2):
        token = _preview(client, admin).json()["preview_token"]
        client.post(
            "/api/admin/packs/commit",
            json={"preview_token": token, "round_label": "Round 1",
                  "deadline_minutes": None},
            headers=auth_headers(admin["token"]),
        )

    tasks = client.get("/api/board", headers=auth_headers(admin["token"])).json()["tasks"]
    codes = [t["code"] for t in tasks]

    assert len(codes) == len(set(codes)) == 24


def test_a_member_cannot_import(client, admin, member):
    client.post(
        "/api/auth/change-password",
        json={"current_password": member["password"], "new_password": "chosen-pw-7k"},
        headers=auth_headers(member["token"]),
    )

    response = client.post(
        "/api/admin/packs/preview",
        files={"file": ("p.zip", ORGANIZER_PACK.read_bytes(), "application/zip")},
        headers=auth_headers(member["token"]),
    )

    assert response.status_code == 403
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd backend && ./venv/Scripts/python.exe -m pytest tests/test_admin_packs.py -v
```

Expected: 404s throughout — neither `/api/admin/packs/*` nor `/api/board` exists.

- [ ] **Step 3: Write the router**

Create `backend/app/routers/admin_packs.py`:

```python
"""Import the organizer's query pack: preview, then commit.

Preview never writes. The uploaded bytes are held in process memory under a
token so that commit operates on exactly what was previewed - re-uploading
between the two steps would mean the admin approved one file and committed
another.
"""
from __future__ import annotations

import json
import sqlite3
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from app.auth.deps import require_admin
from app.db.connection import get_db, utcnow_iso
from app.packs_store import DEFAULT_PATTERN, ParsedFile, PatternError, parse_pack

router = APIRouter(prefix="/api", tags=["packs"])

#: token -> (expires_at_monotonic, source_filename, pattern, parsed files)
_PREVIEWS: dict[str, tuple[float, str, str, list[ParsedFile]]] = {}

PREVIEW_TTL_SECONDS = 30 * 60


def _sweep() -> None:
    now = time.monotonic()
    for token in [t for t, (expiry, *_rest) in _PREVIEWS.items() if expiry < now]:
        _PREVIEWS.pop(token, None)


class QuestionOverride(BaseModel):
    question_text: str | None = None


class CommitRequest(BaseModel):
    preview_token: str
    round_label: str
    deadline_minutes: int | None = None
    overrides: dict[str, QuestionOverride] = {}


def _as_dict(parsed: ParsedFile) -> dict[str, Any]:
    return {
        "filename": parsed.filename,
        "matched": parsed.matched,
        "phase": parsed.phase,
        "code": parsed.code,
        "type": parsed.type,
        "query_text": parsed.query_text,
        "question_text": parsed.question_text,
        "n_events": parsed.n_events,
        "event_labels": parsed.event_labels,
        "warnings": parsed.warnings,
        "error": parsed.error,
    }


@router.post("/admin/packs/preview")
async def preview_pack(
    _admin: Annotated[sqlite3.Row, Depends(require_admin)],
    file: Annotated[UploadFile, File()],
    filename_pattern: Annotated[str, Form()] = DEFAULT_PATTERN,
) -> dict[str, Any]:
    data = await file.read()
    try:
        parsed = parse_pack(data, filename_pattern)
    except PatternError as exc:
        raise HTTPException(400, str(exc)) from exc

    _sweep()
    token = uuid.uuid4().hex
    _PREVIEWS[token] = (
        time.monotonic() + PREVIEW_TTL_SECONDS,
        file.filename or "pack.zip",
        filename_pattern,
        parsed,
    )

    return {
        "preview_token": token,
        "source_filename": file.filename,
        "filename_pattern": filename_pattern,
        "files": [_as_dict(p) for p in parsed],
    }


@router.post("/admin/packs/commit", status_code=201)
def commit_pack(
    body: CommitRequest,
    admin: Annotated[sqlite3.Row, Depends(require_admin)],
    conn: Annotated[sqlite3.Connection, Depends(get_db)],
) -> dict[str, Any]:
    _sweep()
    held = _PREVIEWS.get(body.preview_token)
    if held is None:
        raise HTTPException(
            409, "That preview has expired. Upload the pack again."
        )
    _expiry, source_filename, pattern, parsed = held

    matched = [p for p in parsed if p.matched]
    if not matched:
        raise HTTPException(400, "No file in the archive matched the pattern.")

    phase = next((p.phase for p in matched if p.phase), None)
    deadline = None
    if body.deadline_minutes:
        deadline = (
            datetime.now(timezone.utc) + timedelta(minutes=body.deadline_minutes)
        ).strftime("%Y-%m-%dT%H:%M:%SZ")

    now = utcnow_iso()
    conn.execute("BEGIN IMMEDIATE")
    try:
        cursor = conn.execute(
            """INSERT INTO packs (round_label, phase, source_filename,
                                  filename_pattern, imported_by, imported_at,
                                  deadline_at, active)
               VALUES (?, ?, ?, ?, ?, ?, ?, 1)""",
            (body.round_label, phase, source_filename, pattern,
             admin["id"], now, deadline),
        )
        pack_id = cursor.lastrowid

        created = 0
        skipped = 0
        for item in matched:
            override = body.overrides.get(item.filename)
            question = (
                override.question_text if override is not None else item.question_text
            )
            result = conn.execute(
                """INSERT OR IGNORE INTO tasks
                       (pack_id, code, type, query_text, question_text,
                        n_events, event_labels, import_warnings)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    pack_id, item.code, item.type, item.query_text, question,
                    item.n_events,
                    json.dumps(item.event_labels, ensure_ascii=False),
                    json.dumps(item.warnings, ensure_ascii=False),
                ),
            )
            if result.rowcount:
                created += 1
            else:
                skipped += 1
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise

    _PREVIEWS.pop(body.preview_token, None)
    return {"pack_id": pack_id, "tasks_created": created,
            "skipped": skipped + len(parsed) - len(matched)}
```

**Note on re-import:** `UNIQUE (pack_id, code)` only deduplicates within one pack, and each
commit creates a new pack row. `test_reimporting_the_same_pack_creates_no_duplicates`
therefore requires that the board lists tasks of the **active** pack only. Implement that
in the next step by deactivating previous packs:

Add immediately before the `INSERT INTO packs`:

```python
        # One active pack at a time. Re-importing the same round is a correction,
        # not a second round: without this, the board would show every task twice
        # and the export would produce two files per query.
        conn.execute("UPDATE packs SET active = 0 WHERE active = 1")
```

- [ ] **Step 4: Add the read-only board endpoint**

The Workspace needs a task list before the collaboration slice exists. Create
`backend/app/routers/board.py` with the read half only — S5 fills in `owner`, `viewers` and
the claim routes without changing this contract:

```python
"""The task board.

S2 needs the read half so the workspace has something to select. Claim, release
and presence arrive in S5 and fill in `owner` and `viewers`; the response shape
does not change when they do, so no client code has to.
"""
from __future__ import annotations

import json
import sqlite3
from typing import Annotated, Any

from fastapi import APIRouter, Depends

from app.auth.deps import active_user
from app.db.connection import get_db
from app.settings_store import all_settings

router = APIRouter(prefix="/api", tags=["board"])


def _task_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "pack_id": row["pack_id"],
        "code": row["code"],
        "type": row["type"],
        "query_text": row["query_text"],
        "question_text": row["question_text"],
        "n_events": row["n_events"],
        "event_labels": json.loads(row["event_labels"] or "[]"),
        "import_warnings": json.loads(row["import_warnings"] or "[]"),
        "owner": None,
        "viewers": [],
        "answer_count": row["answer_count"],
        "verified_count": row["verified_count"],
        "version": row["version"],
    }


@router.get("/board")
def board(
    _user: Annotated[sqlite3.Row, Depends(active_user)],
    conn: Annotated[sqlite3.Connection, Depends(get_db)],
    pack_id: int | None = None,
) -> dict[str, Any]:
    pack = conn.execute(
        "SELECT * FROM packs WHERE id = ?" if pack_id else
        "SELECT * FROM packs WHERE active = 1 ORDER BY id DESC LIMIT 1",
        (pack_id,) if pack_id else (),
    ).fetchone()

    if pack is None:
        return {"round": None, "tasks": [], "rows_per_query":
                all_settings(conn)["export.rows_per_query"]}

    rows = conn.execute(
        """SELECT t.*,
                  (SELECT COUNT(*) FROM answers a WHERE a.task_id = t.id)
                      AS answer_count,
                  (SELECT COUNT(*) FROM answers a WHERE a.task_id = t.id
                     AND a.origin = 'manual') AS verified_count
             FROM tasks t
            WHERE t.pack_id = ?
            ORDER BY CAST(t.code AS INTEGER)""",
        (pack["id"],),
    ).fetchall()

    return {
        "round": {
            "id": pack["id"],
            "label": pack["round_label"],
            "phase": pack["phase"],
            "source_filename": pack["source_filename"],
            "deadline_at": pack["deadline_at"],
        },
        "rows_per_query": all_settings(conn)["export.rows_per_query"],
        "tasks": [_task_row(r) for r in rows],
    }
```

In `backend/app/main.py`, include both routers:

```python
from app.routers import admin_packs as admin_packs_router
from app.routers import board as board_router
...
app.include_router(admin_packs_router.router)
app.include_router(board_router.router)
```

- [ ] **Step 5: Run the tests to verify they pass**

```bash
cd backend && ./venv/Scripts/python.exe -m pytest tests/test_admin_packs.py -v
```

Expected: 6 passed.

- [ ] **Step 6: Commit**

```bash
git add backend/app/routers/admin_packs.py backend/app/routers/board.py \
        backend/app/main.py backend/tests/test_admin_packs.py
git commit -m "Import the organizer pack: preview, then commit

Preview writes nothing and holds the uploaded bytes under a token, so commit
operates on exactly the file the admin approved rather than on a second upload.
Parse warnings are stored on the task, so the E1,E2,E2,E4 anomaly is still
visible on the board rather than stopping at the screen where it was noticed.

Re-importing deactivates the previous pack instead of adding a second one: a
re-import is a correction, and without this the board would show every task twice
and the export would produce two files per query.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 14: Front end — the import screen

**Files:**
- Create: `frontend/src/api/packs.ts`
- Create: `frontend/src/types/collab.ts`
- Create: `frontend/src/pages/AdminPacks.tsx`
- Modify: `frontend/src/App.tsx`

**Interfaces:**
- Produces: `previewPack(file: File, pattern: string): Promise<PackPreviewResponse>` ·
  `commitPack(body): Promise<PackCommitResponse>` · the `PackPreviewFile`, `BoardTask`,
  `TaskType` types used by every later frontend task.

- [ ] **Step 1: Write the types**

Create `frontend/src/types/collab.ts`:

```ts
import type { AuthUser } from "./api";

export type TaskType = "kis" | "qa" | "trake";

export interface PackPreviewFile {
  filename: string;
  matched: boolean;
  phase: string | null;
  code: string | null;
  type: TaskType | null;
  query_text: string | null;
  question_text: string | null;
  n_events: number | null;
  event_labels: string[];
  warnings: string[];
  error: string | null;
}

export interface PackPreviewResponse {
  preview_token: string;
  source_filename: string;
  filename_pattern: string;
  files: PackPreviewFile[];
}

export interface PackCommitResponse {
  pack_id: number;
  tasks_created: number;
  skipped: number;
}

export interface BoardTask {
  id: number;
  pack_id: number;
  code: string;
  type: TaskType;
  query_text: string;
  question_text: string | null;
  n_events: number | null;
  event_labels: string[];
  import_warnings: string[];
  owner: AuthUser | null;
  viewers: AuthUser[];
  answer_count: number;
  verified_count: number;
  version: number;
}

export interface RoundInfo {
  id: number;
  label: string;
  phase: string | null;
  source_filename: string;
  deadline_at: string | null;
}

export interface BoardResponse {
  round: RoundInfo | null;
  rows_per_query: number;
  tasks: BoardTask[];
}
```

- [ ] **Step 2: Write the client**

Create `frontend/src/api/packs.ts`:

```ts
import { API_BASE_URL, readResponse } from "./base";
import { useAuthStore } from "../store/authStore";
import type { PackCommitResponse, PackPreviewResponse } from "../types/collab";

/**
 * Multipart, so it cannot go through apiFetch: setting Content-Type by hand
 * would omit the boundary the browser generates, and the server would reject
 * the body.
 */
export async function previewPack(
  file: File,
  filenamePattern: string
): Promise<PackPreviewResponse> {
  const form = new FormData();
  form.append("file", file);
  form.append("filename_pattern", filenamePattern);

  const { token } = useAuthStore.getState();
  const response = await fetch(`${API_BASE_URL}/api/admin/packs/preview`, {
    method: "POST",
    headers: token ? { Authorization: `Bearer ${token}` } : undefined,
    body: form,
  });
  return readResponse<PackPreviewResponse>(response);
}

export async function commitPack(body: {
  preview_token: string;
  round_label: string;
  deadline_minutes: number | null;
  overrides?: Record<string, { question_text: string | null }>;
}): Promise<PackCommitResponse> {
  const { apiFetch } = await import("./base");
  return apiFetch<PackCommitResponse>("/api/admin/packs/commit", {
    method: "POST",
    body: JSON.stringify({ overrides: {}, ...body }),
  });
}
```

- [ ] **Step 3: Write the screen**

Create `frontend/src/pages/AdminPacks.tsx`. Required behaviour, all of it visible without
scrolling past the table:

1. A file input accepting `.zip`, and a text input pre-filled with the default pattern
   `query-(?P<phase>p\d+)-(?P<code>\d+)-(?P<type>kis|qa|trake)\.txt`.
2. `Preview` calls `previewPack`. On `PatternError` the message is shown next to the
   pattern field, not as a toast — the field is what has to change.
3. A table, one row per file: filename · matched · code · type · a two-line clamp of
   `query_text` · `n_events`.
4. **Unmatched rows are rendered, greyed, with their `error`.** Never filtered out.
5. **A row with `warnings.length > 0` shows an amber marker and the warning text.**
6. For `type === "qa"`, `question_text` renders in an editable `<input>`; edits collect
   into an `overrides` map keyed by filename.
7. `Round label` and optional `Deadline (minutes)` inputs, then `Import`, which calls
   `commitPack` and reports `tasks_created` and `skipped`.

- [ ] **Step 4: Add it to the switch**

In `App.tsx`, `if (screen === "packs") return <AdminPacks onNavigate={setRequested} />;`
and add a `Query packs` entry to `AdminNav`.

- [ ] **Step 5: Verify end to end by hand**

With both servers running, log in as admin → Admin → Query packs → choose
`sample-data/query-p1-groupA.zip` → Preview.

Confirm on screen:
- 24 rows, all matched;
- `query-p1-18-trake.txt` shows `4` events **and** the non-sequential warning;
- `query-p1-15-qa.txt` shows the inferred question in an editable field;
- `query-p1-14-kis.txt` shows a query with visible line breaks.

Then Import and confirm `tasks_created: 24`.

- [ ] **Step 6: Commit**

```bash
git add frontend/src
git commit -m "Front end: import the organizer pack with a reviewed preview

Unmatched files are rendered greyed rather than filtered out - an import that
silently drops a file is discovered at export time, which is the worst possible
moment. Parse warnings are amber next to the row that caused them, and the
inferred Q&A question is editable, because inference from punctuation is right
most of the time and the person who can tell is already looking at it.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

# Slice S3 — Workspace: search into a task, and the answer basket

---

### Task 15: `search_core` and `POST /api/search` — TST-7

**Files:**
- Create: `backend/app/search_core.py`
- Create: `backend/app/routers/search.py`
- Create: `backend/tests/test_search_api.py`
- Modify: `backend/tests/conftest.py`
- Modify: `backend/app/main.py`

**Interfaces:**
- Consumes: `app.preprocess.ensemble_search`, `single_model_search`, `MODEL_NAMES` — **read only, never edited.**
- Produces:
  - `app.search_core.run_search(query: str, mode: str, limit: int, top_m: int, use_rerank: bool) -> list[dict]`
  - `app.search_core.remember(user_id: int, task_id: int, results: list[dict]) -> None`
  - `app.search_core.recall(user_id: int, task_id: int) -> list[dict] | None`
  - `POST /api/search` → `{count, took_ms, results: [...]}`
  - conftest fixture `seeded_tasks(client, admin) -> list[dict]` — the 24 imported tasks

- [ ] **Step 1: Add the task fixture**

Append to `backend/tests/conftest.py`:

```python
@pytest.fixture()
def seeded_tasks(client, admin):
    """The real organizer pack, imported. Returns the board's task rows."""
    from tests.fixtures import ORGANIZER_PACK

    preview = client.post(
        "/api/admin/packs/preview",
        files={"file": ("query-p1-groupA.zip", ORGANIZER_PACK.read_bytes(),
                        "application/zip")},
        headers=auth_headers(admin["token"]),
    )
    assert preview.status_code == 200, preview.text

    commit = client.post(
        "/api/admin/packs/commit",
        json={"preview_token": preview.json()["preview_token"],
              "round_label": "Round 1", "deadline_minutes": None},
        headers=auth_headers(admin["token"]),
    )
    assert commit.status_code == 201, commit.text

    return client.get(
        "/api/board", headers=auth_headers(admin["token"])
    ).json()["tasks"]
```

- [ ] **Step 2: Write the failing test**

Create `backend/tests/test_search_api.py`:

```python
"""TST-7: the search endpoint is a pass-through.

The router must not rank, filter, round or rename anything. frame_idx is the
integer that gets submitted to the organizer (INV-2) and routes is what colours
the grid; if either is altered in transit, the UI lies about what the pipeline
found.

preprocess.ensemble_search is monkeypatched so these tests run in milliseconds
and assert the plumbing. TST-1 is what asserts the pipeline itself.
"""
from __future__ import annotations

from tests.conftest import auth_headers

FAKE_RESULT = {
    "name": "L21_V015-0042-025605.jpg",
    "frame": "L21_V015-0042-025605.jpg",
    "url": "http://localhost:8000/static/images/L21_V015-0042-025605.jpg",
    "distance": 88.53125,
    "video": "L21_V015",
    "frame_idx": 25605,
    "timestamp": "17:04",
    "routes": {"beit3": {"rank": 1, "score": 0.41},
               "clip": {"rank": 3, "score": 0.38}},
    "has_image": True,
}


def _patch(monkeypatch, results):
    from app import preprocess

    monkeypatch.setattr(preprocess, "ensemble_search",
                        lambda *args, **kwargs: list(results))


def test_frame_idx_and_routes_survive_the_round_trip(
    client, admin, seeded_tasks, monkeypatch
):
    _patch(monkeypatch, [FAKE_RESULT])
    task_id = seeded_tasks[0]["id"]

    response = client.post(
        "/api/search",
        json={"task_id": task_id, "query": "bốn phi hành gia", "mode": "ensemble",
              "limit": 100, "top_m": 50, "use_rerank": True},
        headers=auth_headers(admin["token"]),
    )

    assert response.status_code == 200
    row = response.json()["results"][0]

    assert row["frame_idx"] == 25605
    assert row["distance"] == 88.53125
    assert row["routes"] == FAKE_RESULT["routes"]
    assert row["name"] == FAKE_RESULT["name"]


def test_result_order_is_not_touched(client, admin, seeded_tasks, monkeypatch):
    """The pipeline already ranked these. Re-sorting would silently discard
    the rerank and the ensemble weighting."""
    ordered = [
        {**FAKE_RESULT, "name": f"L21_V015-{i}.jpg", "frame_idx": i, "distance": 50 + i}
        for i in (3, 1, 2)
    ]
    _patch(monkeypatch, ordered)

    response = client.post(
        "/api/search",
        json={"task_id": seeded_tasks[0]["id"], "query": "x", "mode": "ensemble",
              "limit": 100},
        headers=auth_headers(admin["token"]),
    )

    assert [r["frame_idx"] for r in response.json()["results"]] == [3, 1, 2]


def test_search_requires_a_task(client, admin, monkeypatch):
    _patch(monkeypatch, [FAKE_RESULT])

    response = client.post(
        "/api/search",
        json={"task_id": 9999, "query": "x", "mode": "ensemble", "limit": 10},
        headers=auth_headers(admin["token"]),
    )

    assert response.status_code == 404


def test_the_last_search_is_remembered_per_user_and_task(
    client, admin, seeded_tasks, monkeypatch
):
    _patch(monkeypatch, [FAKE_RESULT])
    task_id = seeded_tasks[0]["id"]

    client.post(
        "/api/search",
        json={"task_id": task_id, "query": "x", "mode": "ensemble", "limit": 10},
        headers=auth_headers(admin["token"]),
    )

    from app.search_core import recall

    remembered = recall(admin["id"], task_id)
    assert remembered is not None
    assert remembered[0]["frame_idx"] == 25605
    assert recall(admin["id"], task_id + 1) is None
```

- [ ] **Step 3: Run the test to verify it fails**

```bash
cd backend && ./venv/Scripts/python.exe -m pytest tests/test_search_api.py -v
```

Expected: `ModuleNotFoundError: No module named 'app.search_core'`.

- [ ] **Step 4: Write `search_core.py`**

```python
"""The only module that calls preprocess.py.

INV-1 freezes preprocess.py, and the way a freeze survives contact with a growing
application is by having exactly one door. Everything the collaboration layer
knows about retrieval, it learns here.

`preprocess` is imported as a module rather than by name so that a test can
replace `preprocess.ensemble_search` and exercise the plumbing without loading
1.3 GB of weights. That is also why nothing here rewrites a result field: the
router is a pipe, and TST-7 asserts it.
"""
from __future__ import annotations

import time

from app import preprocess

MODES = ("ensemble", "beit3", "clip")

#: (user_id, task_id) -> (recorded_at_monotonic, results)
#: Process memory on purpose: losing it costs one re-search, and a database
#: table would have to be cleaned up by something.
_LAST_SEARCH: dict[tuple[int, int], tuple[float, list[dict]]] = {}

LAST_SEARCH_TTL_SECONDS = 30 * 60


def run_search(
    query: str,
    mode: str = "ensemble",
    limit: int = 100,
    top_m: int = 50,
    use_rerank: bool = True,
) -> list[dict]:
    """Delegate to the frozen core. No ranking, filtering or field rewriting."""
    if mode == "ensemble":
        return preprocess.ensemble_search(
            query, top_k=limit, top_m=top_m, use_rerank=use_rerank
        )
    if mode not in preprocess.MODEL_NAMES:
        raise ValueError(f"mode must be one of {MODES}")
    return preprocess.single_model_search(
        query, mode, top_k=limit, top_m=top_m, use_rerank=use_rerank
    )


def remember(user_id: int, task_id: int, results: list[dict]) -> None:
    _sweep()
    _LAST_SEARCH[(user_id, task_id)] = (time.monotonic(), list(results))


def recall(user_id: int, task_id: int) -> list[dict] | None:
    _sweep()
    held = _LAST_SEARCH.get((user_id, task_id))
    return None if held is None else held[1]


def _sweep() -> None:
    cutoff = time.monotonic() - LAST_SEARCH_TTL_SECONDS
    for key in [k for k, (at, _r) in _LAST_SEARCH.items() if at < cutoff]:
        _LAST_SEARCH.pop(key, None)
```

- [ ] **Step 5: Write the router**

Create `backend/app/routers/search.py`:

```python
"""POST /api/search — the search the workspace runs, bound to a task.

The five original search endpoints stay exactly where they are, unauthenticated
and unchanged, because they are how the pipeline is exercised and compared. This
one adds the two things the workspace needs and nothing else: a task to attach
the results to, and a memory of them so autofill has something to fill from.
"""
from __future__ import annotations

import sqlite3
import time
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app import search_core
from app.auth.deps import active_user
from app.db.connection import get_db

router = APIRouter(prefix="/api", tags=["search"])


class SearchRequest(BaseModel):
    task_id: int
    query: str = Field(min_length=1)
    mode: str = "ensemble"
    limit: int = Field(100, ge=1, le=500)
    top_m: int = Field(50, ge=1, le=200)
    use_rerank: bool = True


@router.post("/search")
def search(
    body: SearchRequest,
    user: Annotated[sqlite3.Row, Depends(active_user)],
    conn: Annotated[sqlite3.Connection, Depends(get_db)],
) -> dict[str, Any]:
    task = conn.execute(
        "SELECT id FROM tasks WHERE id = ?", (body.task_id,)
    ).fetchone()
    if task is None:
        raise HTTPException(404, "No such task")

    started = time.perf_counter()
    try:
        results = search_core.run_search(
            body.query, body.mode, body.limit, body.top_m, body.use_rerank
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:  # a missing index, an OOM, a corrupt mapping
        raise HTTPException(500, f"Search failed: {exc}") from exc

    search_core.remember(user["id"], body.task_id, results)

    return {
        "count": len(results),
        "took_ms": round((time.perf_counter() - started) * 1000, 1),
        "results": results,
    }
```

In `backend/app/main.py`, add `from app.routers import search as search_router` and
`app.include_router(search_router.router)`.

- [ ] **Step 6: Run the tests to verify they pass**

```bash
cd backend && ./venv/Scripts/python.exe -m pytest tests/test_search_api.py tests/test_harness.py -v
```

Expected: 4 passed + 2 passed. The harness test confirms `/ensemble-search` and friends
are still registered.

- [ ] **Step 7: Commit**

```bash
git add backend/app/search_core.py backend/app/routers/search.py \
        backend/app/main.py backend/tests/conftest.py backend/tests/test_search_api.py
git commit -m "POST /api/search: one door to the frozen retrieval core

search_core is the only module that calls preprocess.py, because the way a freeze
survives contact with a growing application is by having exactly one door. The
router adds a task to attach results to and a 30-minute memory for autofill, and
does nothing else - it does not re-sort, because the pipeline already ranked
these and re-sorting would silently discard the rerank and the ensemble weights.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 16: The answer store — TST-9, TST-10

**Files:**
- Create: `backend/app/answers_store.py`
- Create: `backend/tests/test_answers_store.py`

**Interfaces:**
- Produces:
  - `list_answers(conn, task_id) -> list[dict]` — each row carries a derived `rank`
  - `insert_answer(conn, task_id, *, video_id, frames, answer_text, origin, created_by, position) -> dict`
  - `patch_answer(conn, answer_id, *, version, updated_by, **fields) -> dict | None` (`None` = version conflict)
  - `reorder(conn, task_id, answer_id, *, before_id=None, after_id=None) -> list[dict]`
  - `delete_answer(conn, answer_id) -> bool`
  - `dedupe(conn, task_id) -> int`
  - `MIN_GAP = 1e-9`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_answers_store.py`:

```python
"""TST-9 and TST-10 — ordering is one UPDATE, and a stale write is refused."""
from __future__ import annotations

import pytest

from app.answers_store import (
    delete_answer,
    dedupe,
    insert_answer,
    list_answers,
    patch_answer,
    reorder,
)


@pytest.fixture()
def task(db):
    db.execute(
        """INSERT INTO users (id, username, display_name, role, password_hash,
                              must_change_password, disabled, created_at)
           VALUES (1, 'nam', 'Nam', 'member', 'x', 0, 0, '2026-08-16T00:00:00Z')"""
    )
    db.execute(
        """INSERT INTO packs (id, round_label, phase, source_filename,
                              filename_pattern, imported_by, imported_at, active)
           VALUES (1, 'R1', 'p1', 'p.zip', 'x', 1, '2026-08-16T00:00:00Z', 1)"""
    )
    db.execute(
        """INSERT INTO tasks (id, pack_id, code, type, query_text)
           VALUES (7, 1, '7', 'kis', 'truy vấn')"""
    )
    return 7


def _add(db, task, frame, origin="auto", position="end"):
    return insert_answer(
        db, task, video_id="L21_V015", frames=[frame], answer_text=None,
        origin=origin, created_by=1, position=position,
    )


def test_rank_is_derived_from_sort_key(db, task):
    _add(db, task, 100)
    _add(db, task, 200)
    _add(db, task, 300)

    rows = list_answers(db, task)

    assert [r["rank"] for r in rows] == [1, 2, 3]
    assert [r["frames"][0] for r in rows] == [100, 200, 300]


def test_position_top_puts_a_row_first(db, task):
    _add(db, task, 100)
    _add(db, task, 200)

    _add(db, task, 999, position="top")

    assert [r["frames"][0] for r in list_answers(db, task)] == [999, 100, 200]


def test_reorder_touches_exactly_one_row(db, task):
    """TST-10. Dragging rank 40 to rank 1 must not renumber 40 rows mid-round."""
    created = [_add(db, task, n)["id"] for n in range(1, 11)]
    before = {
        r["id"]: r["sort_key"]
        for r in db.execute("SELECT id, sort_key FROM answers WHERE task_id = ?", (task,))
    }

    reorder(db, task, created[-1], before_id=created[0])

    after = {
        r["id"]: r["sort_key"]
        for r in db.execute("SELECT id, sort_key FROM answers WHERE task_id = ?", (task,))
    }
    changed = [i for i in before if before[i] != after[i]]

    assert changed == [created[-1]]
    assert [r["id"] for r in list_answers(db, task)][0] == created[-1]


def test_a_stale_version_is_refused(db, task):
    """TST-9. Two people editing row 1 must not silently overwrite each other."""
    row = _add(db, task, 100)

    first = patch_answer(db, row["id"], version=row["version"], updated_by=1,
                         frames=[111])
    assert first is not None
    assert first["frames"] == [111]
    assert first["version"] == row["version"] + 1

    # The second writer still holds the version they read before the first wrote.
    second = patch_answer(db, row["id"], version=row["version"], updated_by=1,
                          frames=[222])

    assert second is None
    current = list_answers(db, task)[0]
    assert current["frames"] == [111]


def test_patching_marks_the_row_manual(db, task):
    """A row a human touched is no longer a machine's guess, and replace_auto
    must not overwrite it."""
    row = _add(db, task, 100, origin="auto")

    updated = patch_answer(db, row["id"], version=row["version"], updated_by=1,
                           frames=[101])

    assert updated["origin"] == "manual"


def test_dedupe_keeps_the_highest_ranked_copy(db, task):
    _add(db, task, 100)
    _add(db, task, 200)
    _add(db, task, 100)

    removed = dedupe(db, task)

    assert removed == 1
    assert [r["frames"][0] for r in list_answers(db, task)] == [100, 200]


def test_delete_removes_the_row(db, task):
    row = _add(db, task, 100)

    assert delete_answer(db, row["id"]) is True
    assert list_answers(db, task) == []
    assert delete_answer(db, row["id"]) is False
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd backend && ./venv/Scripts/python.exe -m pytest tests/test_answers_store.py -v
```

Expected: `ModuleNotFoundError: No module named 'app.answers_store'`.

- [ ] **Step 3: Write the store**

Create `backend/app/answers_store.py`:

```python
"""The answer basket: ordering, ranks, and writes that refuse to clobber.

Row order IS the score - R@k reads the first k rows - so ordering is not a
display concern here, it is the product. Two consequences shape this module.

sort_key is REAL. Moving a row from rank 40 to rank 1 with an integer rank column
means renumbering 40 rows inside a transaction; with a float it is the midpoint
of two neighbours and one UPDATE. Rank is derived at read time.

Every write carries the version the client last read. Five people work one round
at once and two of them will edit the same row; the loser is told, and chooses.
Nothing is merged automatically and nothing is overwritten in silence.
"""
from __future__ import annotations

import json
import sqlite3
from typing import Any

from app.db.connection import utcnow_iso

#: Below this the float keys have run out of room between two neighbours and the
#: task is renumbered. Rare, and cheap when it happens.
MIN_GAP = 1e-9

_SELECT = """
SELECT a.*,
       ROW_NUMBER() OVER (ORDER BY a.sort_key) AS rank,
       cu.display_name AS created_by_name,
       uu.display_name AS updated_by_name
  FROM answers a
  LEFT JOIN users cu ON cu.id = a.created_by
  LEFT JOIN users uu ON uu.id = a.updated_by
 WHERE a.task_id = ?
 ORDER BY a.sort_key
"""


def _row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "task_id": row["task_id"],
        "rank": row["rank"],
        "sort_key": row["sort_key"],
        "video_id": row["video_id"],
        "frames": json.loads(row["frames"]),
        "answer_text": row["answer_text"],
        "origin": row["origin"],
        "created_by": {"id": row["created_by"], "display_name": row["created_by_name"]},
        "updated_by": (
            {"id": row["updated_by"], "display_name": row["updated_by_name"]}
            if row["updated_by"] else None
        ),
        "updated_at": row["updated_at"],
        "version": row["version"],
    }


def list_answers(conn: sqlite3.Connection, task_id: int) -> list[dict[str, Any]]:
    return [_row(r) for r in conn.execute(_SELECT, (task_id,)).fetchall()]


def _bounds(conn: sqlite3.Connection, task_id: int) -> tuple[float, float]:
    row = conn.execute(
        "SELECT MIN(sort_key) AS lo, MAX(sort_key) AS hi FROM answers WHERE task_id = ?",
        (task_id,),
    ).fetchone()
    return (row["lo"] if row["lo"] is not None else 0.0,
            row["hi"] if row["hi"] is not None else 0.0)


def _key_for(conn: sqlite3.Connection, task_id: int, position: Any) -> float:
    lo, hi = _bounds(conn, task_id)

    if position == "top":
        return lo - 1.0
    if isinstance(position, dict) and "after_id" in position:
        return _after(conn, task_id, int(position["after_id"]))
    return hi + 1.0


def _neighbour_keys(
    conn: sqlite3.Connection, task_id: int, anchor_id: int
) -> tuple[float | None, float, float | None]:
    """(key below the anchor, the anchor's key, key above the anchor)."""
    anchor = conn.execute(
        "SELECT sort_key FROM answers WHERE id = ? AND task_id = ?",
        (anchor_id, task_id),
    ).fetchone()
    if anchor is None:
        raise KeyError(anchor_id)
    key = anchor["sort_key"]

    below = conn.execute(
        "SELECT MAX(sort_key) AS k FROM answers WHERE task_id = ? AND sort_key < ?",
        (task_id, key),
    ).fetchone()["k"]
    above = conn.execute(
        "SELECT MIN(sort_key) AS k FROM answers WHERE task_id = ? AND sort_key > ?",
        (task_id, key),
    ).fetchone()["k"]
    return below, key, above


def _after(conn: sqlite3.Connection, task_id: int, after_id: int) -> float:
    _below, key, above = _neighbour_keys(conn, task_id, after_id)
    return key + 1.0 if above is None else (key + above) / 2.0


def _before(conn: sqlite3.Connection, task_id: int, before_id: int) -> float:
    below, key, _above = _neighbour_keys(conn, task_id, before_id)
    return key - 1.0 if below is None else (below + key) / 2.0


def renumber(conn: sqlite3.Connection, task_id: int) -> None:
    """Space the keys out again. Called only when two neighbours have collided."""
    rows = conn.execute(
        "SELECT id FROM answers WHERE task_id = ? ORDER BY sort_key", (task_id,)
    ).fetchall()
    for index, row in enumerate(rows, start=1):
        conn.execute(
            "UPDATE answers SET sort_key = ? WHERE id = ?", (float(index), row["id"])
        )


def insert_answer(
    conn: sqlite3.Connection,
    task_id: int,
    *,
    video_id: str,
    frames: list[int],
    answer_text: str | None,
    origin: str,
    created_by: int,
    position: Any = "end",
) -> dict[str, Any]:
    now = utcnow_iso()
    cursor = conn.execute(
        """INSERT INTO answers (task_id, sort_key, video_id, frames, answer_text,
                                origin, created_by, updated_by, updated_at, version)
           VALUES (?, ?, ?, ?, ?, ?, ?, NULL, ?, 1)""",
        (task_id, _key_for(conn, task_id, position), video_id,
         json.dumps(frames), answer_text, origin, created_by, now),
    )
    return next(r for r in list_answers(conn, task_id) if r["id"] == cursor.lastrowid)


def patch_answer(
    conn: sqlite3.Connection,
    answer_id: int,
    *,
    version: int,
    updated_by: int,
    **fields: Any,
) -> dict[str, Any] | None:
    """Returns the new row, or None when the client's version was stale.

    A row a human edited stops being a machine's guess, so origin becomes
    'manual' - that is what protects it from autofill's replace_auto mode.
    """
    allowed = {"video_id", "frames", "answer_text"}
    updates = {k: v for k, v in fields.items() if k in allowed and v is not None}

    sets = []
    values: list[Any] = []
    for key, value in updates.items():
        sets.append(f"{key} = ?")
        values.append(json.dumps(value) if key == "frames" else value)

    sets += ["origin = 'manual'", "updated_by = ?", "updated_at = ?",
             "version = version + 1"]
    values += [updated_by, utcnow_iso(), answer_id, version]

    result = conn.execute(
        f"UPDATE answers SET {', '.join(sets)} WHERE id = ? AND version = ?",
        values,
    )
    if result.rowcount == 0:
        return None

    row = conn.execute("SELECT task_id FROM answers WHERE id = ?", (answer_id,)).fetchone()
    return next(r for r in list_answers(conn, row["task_id"]) if r["id"] == answer_id)


def reorder(
    conn: sqlite3.Connection,
    task_id: int,
    answer_id: int,
    *,
    before_id: int | None = None,
    after_id: int | None = None,
) -> list[dict[str, Any]]:
    if before_id is None and after_id is None:
        raise ValueError("reorder needs before_id or after_id")

    key = (_before(conn, task_id, before_id) if before_id is not None
           else _after(conn, task_id, after_id))

    conn.execute(
        "UPDATE answers SET sort_key = ? WHERE id = ? AND task_id = ?",
        (key, answer_id, task_id),
    )

    below, current, above = _neighbour_keys(conn, task_id, answer_id)
    if (below is not None and abs(current - below) < MIN_GAP) or (
        above is not None and abs(above - current) < MIN_GAP
    ):
        renumber(conn, task_id)

    return list_answers(conn, task_id)


def delete_answer(conn: sqlite3.Connection, answer_id: int) -> bool:
    return conn.execute("DELETE FROM answers WHERE id = ?", (answer_id,)).rowcount > 0


def dedupe(conn: sqlite3.Connection, task_id: int) -> int:
    """Drop later rows that repeat an earlier (video_id, frames) pair.

    Keeps the highest-ranked copy: a duplicate lower down is a wasted slot, and
    with R@k a wasted slot is a discarded chance rather than a neutral one.
    """
    seen: set[tuple[str, str]] = set()
    doomed: list[int] = []
    for row in conn.execute(
        "SELECT id, video_id, frames FROM answers WHERE task_id = ? ORDER BY sort_key",
        (task_id,),
    ):
        key = (row["video_id"], row["frames"])
        if key in seen:
            doomed.append(row["id"])
        else:
            seen.add(key)

    for answer_id in doomed:
        conn.execute("DELETE FROM answers WHERE id = ?", (answer_id,))
    return len(doomed)
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
cd backend && ./venv/Scripts/python.exe -m pytest tests/test_answers_store.py -v
```

Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/answers_store.py backend/tests/test_answers_store.py
git commit -m "The answer basket: float sort keys and version-checked writes

Row order is the score - R@k reads the first k rows - so ordering is the product
here, not a display concern. A float sort key makes moving rank 40 to rank 1 one
UPDATE instead of renumbering forty rows inside a transaction while four other
people are working, and rank is derived at read time so the two can never drift.

Every write carries the version the client last read. Two people will edit the
same row; the loser is told and chooses. Nothing merges automatically.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 17: Answer endpoints and autofill — TST-8

**Files:**
- Create: `backend/app/routers/answers.py`
- Create: `backend/tests/test_answers_api.py`
- Modify: `backend/app/main.py`

**Interfaces:**
- Consumes: `answers_store.*`, `search_core.recall`, `settings_store.all_settings`.
- Produces: `GET|POST /api/tasks/{id}/answers` · `POST /api/tasks/{id}/answers/autofill` ·
  `PATCH|DELETE /api/answers/{id}` · `POST /api/tasks/{id}/answers/reorder` ·
  `POST /api/tasks/{id}/answers/dedupe` · `PUT /api/tasks/{id}/answer-text`.
  `frames_for_task(task, result) -> list[int]` lives here and is reused by nothing else.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_answers_api.py`:

```python
from __future__ import annotations

from tests.conftest import auth_headers
from tests.test_search_api import FAKE_RESULT, _patch


def _search(client, admin, task_id, monkeypatch, rows):
    _patch(monkeypatch, rows)
    return client.post(
        "/api/search",
        json={"task_id": task_id, "query": "x", "mode": "ensemble", "limit": 100},
        headers=auth_headers(admin["token"]),
    )


def _rows(n):
    return [
        {**FAKE_RESULT, "name": f"L21_V015-{i:05d}.jpg", "frame_idx": 1000 + i,
         "distance": 90 - i}
        for i in range(n)
    ]


def test_autofill_fills_to_the_configured_limit(
    client, admin, seeded_tasks, monkeypatch
):
    task_id = next(t["id"] for t in seeded_tasks if t["type"] == "kis")
    _search(client, admin, task_id, monkeypatch, _rows(120))

    response = client.post(
        f"/api/tasks/{task_id}/answers/autofill",
        json={"source": "last_search", "limit": 100, "mode": "append"},
        headers=auth_headers(admin["token"]),
    )

    assert response.status_code == 200
    assert response.json()["total"] == 100


def test_autofill_append_leaves_manual_rows_untouched(
    client, admin, seeded_tasks, monkeypatch
):
    """TST-8. A row a human verified must survive the machine filling around it."""
    task_id = next(t["id"] for t in seeded_tasks if t["type"] == "kis")

    created = client.post(
        f"/api/tasks/{task_id}/answers",
        json={"video_id": "L99_V001", "frames": [42], "position": "top"},
        headers=auth_headers(admin["token"]),
    ).json()["answer"]
    client.patch(
        f"/api/answers/{created['id']}",
        json={"frames": [43], "version": created["version"]},
        headers=auth_headers(admin["token"]),
    )

    _search(client, admin, task_id, monkeypatch, _rows(50))
    client.post(
        f"/api/tasks/{task_id}/answers/autofill",
        json={"source": "last_search", "limit": 100, "mode": "append"},
        headers=auth_headers(admin["token"]),
    )

    rows = client.get(
        f"/api/tasks/{task_id}/answers", headers=auth_headers(admin["token"])
    ).json()["answers"]

    assert rows[0]["video_id"] == "L99_V001"
    assert rows[0]["frames"] == [43]
    assert rows[0]["origin"] == "manual"


def test_autofill_without_a_recent_search_is_a_409(client, admin, seeded_tasks):
    task_id = seeded_tasks[0]["id"]

    response = client.post(
        f"/api/tasks/{task_id}/answers/autofill",
        json={"source": "last_search", "limit": 100, "mode": "append"},
        headers=auth_headers(admin["token"]),
    )

    assert response.status_code == 409
    assert "No recent search" in response.json()["detail"]


def test_trake_autofill_creates_one_slot_per_event(
    client, admin, seeded_tasks, monkeypatch
):
    """A TRAKE row is video_id plus N frames. Filling one frame would produce a
    row that scores zero for the missing moments and cannot be fixed by sorting."""
    task = next(t for t in seeded_tasks if t["type"] == "trake")
    _search(client, admin, task["id"], monkeypatch, _rows(10))

    client.post(
        f"/api/tasks/{task['id']}/answers/autofill",
        json={"source": "last_search", "limit": 10, "mode": "append"},
        headers=auth_headers(admin["token"]),
    )

    rows = client.get(
        f"/api/tasks/{task['id']}/answers", headers=auth_headers(admin["token"])
    ).json()["answers"]

    assert all(len(r["frames"]) == task["n_events"] for r in rows)


def test_a_stale_patch_returns_409_with_the_current_row(
    client, admin, seeded_tasks
):
    task_id = seeded_tasks[0]["id"]
    created = client.post(
        f"/api/tasks/{task_id}/answers",
        json={"video_id": "L21_V015", "frames": [100]},
        headers=auth_headers(admin["token"]),
    ).json()["answer"]

    client.patch(
        f"/api/answers/{created['id']}",
        json={"frames": [111], "version": created["version"]},
        headers=auth_headers(admin["token"]),
    )
    conflict = client.patch(
        f"/api/answers/{created['id']}",
        json={"frames": [222], "version": created["version"]},
        headers=auth_headers(admin["token"]),
    )

    assert conflict.status_code == 409
    assert conflict.json()["current"]["frames"] == [111]


def test_qa_answer_text_can_be_applied_to_every_row(
    client, admin, seeded_tasks, monkeypatch
):
    task = next(t for t in seeded_tasks if t["type"] == "qa")
    _search(client, admin, task["id"], monkeypatch, _rows(5))
    client.post(
        f"/api/tasks/{task['id']}/answers/autofill",
        json={"source": "last_search", "limit": 5, "mode": "append"},
        headers=auth_headers(admin["token"]),
    )

    response = client.put(
        f"/api/tasks/{task['id']}/answer-text",
        json={"answer_text": "Xã Giang Ly", "apply": "all"},
        headers=auth_headers(admin["token"]),
    )

    assert response.status_code == 200
    assert response.json()["updated"] == 5
    rows = client.get(
        f"/api/tasks/{task['id']}/answers", headers=auth_headers(admin["token"])
    ).json()["answers"]
    assert all(r["answer_text"] == "Xã Giang Ly" for r in rows)
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd backend && ./venv/Scripts/python.exe -m pytest tests/test_answers_api.py -v
```

Expected: 404s — the router does not exist.

- [ ] **Step 3: Write the router**

Create `backend/app/routers/answers.py`:

```python
"""Answer endpoints.

Autofill is the reason this file matters more than it looks. R@k is a max, so an
extra answer can never lower a score and an empty row 51-100 is a discarded
chance rather than a neutral one. Filling to the limit therefore has to be the
default the machine does, not a chore the user has to remember while the clock
runs.
"""
from __future__ import annotations

import sqlite3
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app import answers_store, search_core
from app.auth.deps import active_user
from app.db.connection import get_db
from app.settings_store import all_settings

router = APIRouter(prefix="/api", tags=["answers"])


class AnswerCreate(BaseModel):
    video_id: str
    frames: list[int]
    answer_text: str | None = None
    position: Any = "end"


class AutofillRequest(BaseModel):
    source: Literal["last_search"] = "last_search"
    limit: int | None = None
    mode: Literal["append", "replace_auto"] = "append"


class AnswerPatch(BaseModel):
    version: int
    video_id: str | None = None
    frames: list[int] | None = None
    answer_text: str | None = None


class ReorderRequest(BaseModel):
    answer_id: int
    before_id: int | None = None
    after_id: int | None = None


class AnswerTextRequest(BaseModel):
    answer_text: str
    apply: Literal["all", "empty_only"] = "all"


def _task(conn: sqlite3.Connection, task_id: int) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    if row is None:
        raise HTTPException(404, "No such task")
    return row


def frames_for_task(task: sqlite3.Row, result: dict[str, Any]) -> list[int]:
    """How many frames one auto-filled row needs.

    TRAKE submits video_id plus one frame per moment, and a row missing a moment
    scores zero for it. The search result gives one frame; the rest start as
    copies of it, so the row is complete and every slot is visibly a guess that
    a human can correct. Filling fewer would produce a row that cannot be fixed
    by reordering.
    """
    frame = int(result.get("frame_idx") or 0)
    if task["type"] == "trake":
        return [frame] * int(task["n_events"] or 1)
    return [frame]


@router.get("/tasks/{task_id}/answers")
def list_answers(
    task_id: int,
    _user: Annotated[sqlite3.Row, Depends(active_user)],
    conn: Annotated[sqlite3.Connection, Depends(get_db)],
) -> dict[str, Any]:
    _task(conn, task_id)
    return {"answers": answers_store.list_answers(conn, task_id)}


@router.post("/tasks/{task_id}/answers", status_code=201)
def create_answer(
    task_id: int,
    body: AnswerCreate,
    user: Annotated[sqlite3.Row, Depends(active_user)],
    conn: Annotated[sqlite3.Connection, Depends(get_db)],
) -> dict[str, Any]:
    _task(conn, task_id)
    answer = answers_store.insert_answer(
        conn, task_id, video_id=body.video_id, frames=body.frames,
        answer_text=body.answer_text, origin="manual",
        created_by=user["id"], position=body.position,
    )
    return {"answer": answer}


@router.post("/tasks/{task_id}/answers/autofill")
def autofill(
    task_id: int,
    body: AutofillRequest,
    user: Annotated[sqlite3.Row, Depends(active_user)],
    conn: Annotated[sqlite3.Connection, Depends(get_db)],
) -> dict[str, Any]:
    task = _task(conn, task_id)
    results = search_core.recall(user["id"], task_id)
    if not results:
        raise HTTPException(409, "No recent search for this task")

    limit = body.limit or int(all_settings(conn)["export.rows_per_query"])

    if body.mode == "replace_auto":
        conn.execute(
            "DELETE FROM answers WHERE task_id = ? AND origin = 'auto'", (task_id,)
        )

    existing = answers_store.list_answers(conn, task_id)
    seen = {(r["video_id"], tuple(r["frames"])) for r in existing}
    room = max(0, limit - len(existing))

    added = 0
    for result in results:
        if added >= room:
            break
        video_id = result.get("video") or ""
        frames = frames_for_task(task, result)
        if not video_id or (video_id, tuple(frames)) in seen:
            continue
        answers_store.insert_answer(
            conn, task_id, video_id=video_id, frames=frames, answer_text=None,
            origin="auto", created_by=user["id"], position="end",
        )
        seen.add((video_id, tuple(frames)))
        added += 1

    return {"added": added, "total": len(answers_store.list_answers(conn, task_id))}


@router.patch("/answers/{answer_id}")
def patch_answer(
    answer_id: int,
    body: AnswerPatch,
    user: Annotated[sqlite3.Row, Depends(active_user)],
    conn: Annotated[sqlite3.Connection, Depends(get_db)],
) -> dict[str, Any]:
    row = conn.execute(
        "SELECT task_id FROM answers WHERE id = ?", (answer_id,)
    ).fetchone()
    if row is None:
        raise HTTPException(404, "No such answer")

    updated = answers_store.patch_answer(
        conn, answer_id, version=body.version, updated_by=user["id"],
        video_id=body.video_id, frames=body.frames, answer_text=body.answer_text,
    )
    if updated is None:
        current = next(
            r for r in answers_store.list_answers(conn, row["task_id"])
            if r["id"] == answer_id
        )
        raise HTTPException(
            status_code=409,
            detail={"detail": "Modified by someone else", "current": current},
        )
    return {"answer": updated}


@router.delete("/answers/{answer_id}")
def delete_answer(
    answer_id: int,
    _user: Annotated[sqlite3.Row, Depends(active_user)],
    conn: Annotated[sqlite3.Connection, Depends(get_db)],
) -> dict[str, Any]:
    if not answers_store.delete_answer(conn, answer_id):
        raise HTTPException(404, "No such answer")
    return {"ok": True}


@router.post("/tasks/{task_id}/answers/reorder")
def reorder(
    task_id: int,
    body: ReorderRequest,
    _user: Annotated[sqlite3.Row, Depends(active_user)],
    conn: Annotated[sqlite3.Connection, Depends(get_db)],
) -> dict[str, Any]:
    _task(conn, task_id)
    try:
        rows = answers_store.reorder(
            conn, task_id, body.answer_id,
            before_id=body.before_id, after_id=body.after_id,
        )
    except (KeyError, ValueError) as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"answers": rows}


@router.post("/tasks/{task_id}/answers/dedupe")
def dedupe(
    task_id: int,
    _user: Annotated[sqlite3.Row, Depends(active_user)],
    conn: Annotated[sqlite3.Connection, Depends(get_db)],
) -> dict[str, Any]:
    _task(conn, task_id)
    return {"removed": answers_store.dedupe(conn, task_id)}


@router.put("/tasks/{task_id}/answer-text")
def set_answer_text(
    task_id: int,
    body: AnswerTextRequest,
    _user: Annotated[sqlite3.Row, Depends(active_user)],
    conn: Annotated[sqlite3.Connection, Depends(get_db)],
) -> dict[str, Any]:
    task = _task(conn, task_id)
    if task["type"] != "qa":
        raise HTTPException(400, "Only a Q&A task has an answer text")

    clause = "" if body.apply == "all" else \
        " AND (answer_text IS NULL OR answer_text = '')"
    result = conn.execute(
        f"UPDATE answers SET answer_text = ? WHERE task_id = ?{clause}",
        (body.answer_text, task_id),
    )
    return {"updated": result.rowcount}
```

In `backend/app/main.py`, add `from app.routers import answers as answers_router` and
`app.include_router(answers_router.router)`.

- [ ] **Step 4: Run the tests to verify they pass**

```bash
cd backend && ./venv/Scripts/python.exe -m pytest tests/test_answers_api.py -v
```

Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/routers/answers.py backend/app/main.py backend/tests/test_answers_api.py
git commit -m "Answer endpoints, autofill, reorder and the Q&A bulk answer

R@k is a max, so an extra answer can never lower a score - which makes an empty
row 51-100 a discarded chance rather than a neutral one. Filling to the limit is
therefore something the machine does by default, not something the user has to
remember with the clock running. append never touches a row a human edited,
because patching marks a row manual and only auto rows are replaceable.

TRAKE autofill creates one slot per moment rather than one frame. A row missing
a moment scores zero for it and no amount of reordering repairs that.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 18: Front end — the workspace data layer

**Files:**
- Create: `frontend/src/api/board.ts`, `frontend/src/api/search.ts`, `frontend/src/api/answers.ts`
- Create: `frontend/src/hooks/useBoard.ts`, `frontend/src/hooks/useAnswers.ts`
- Create: `frontend/src/store/workspaceStore.ts`
- Create: `frontend/src/types/answers.ts`

**Interfaces:**
- Produces:
  - `useBoard(): { board: BoardResponse | null; refresh: () => Promise<void>; error: string | null }` — **the only place board data is fetched**
  - `useAnswers(taskId: number | null): { answers: AnswerRow[]; refresh; add; patch; remove; move; autofill; conflict; resolveConflict }`
  - `searchInTask(taskId, query, mode, limit): Promise<SearchInTaskResponse>`
  - `AnswerRow = { id, task_id, rank, video_id, frames, answer_text, origin, created_by, updated_by, updated_at, version }`

- [ ] **Step 1: Write the types and the clients**

`frontend/src/types/answers.ts`:

```ts
import type { SearchResult } from "./api";

export interface MiniUser {
  id: number;
  display_name: string;
}

export interface AnswerRow {
  id: number;
  task_id: number;
  rank: number;
  video_id: string;
  frames: number[];
  answer_text: string | null;
  origin: "auto" | "manual";
  created_by: MiniUser | null;
  updated_by: MiniUser | null;
  updated_at: string;
  version: number;
}

export interface SearchInTaskResponse {
  count: number;
  took_ms: number;
  results: SearchResult[];
}
```

`frontend/src/api/board.ts`:

```ts
import { apiFetch } from "./base";
import type { BoardResponse } from "../types/collab";

export async function getBoard(packId?: number): Promise<BoardResponse> {
  const query = packId ? `?pack_id=${packId}` : "";
  return apiFetch<BoardResponse>(`/api/board${query}`);
}
```

`frontend/src/api/search.ts`:

```ts
import { apiFetch } from "./base";
import type { SearchMode } from "../types/api";
import type { SearchInTaskResponse } from "../types/answers";

export async function searchInTask(
  taskId: number,
  query: string,
  mode: SearchMode = "ensemble",
  limit = 100
): Promise<SearchInTaskResponse> {
  return apiFetch<SearchInTaskResponse>("/api/search", {
    method: "POST",
    body: JSON.stringify({
      task_id: taskId, query, mode, limit, top_m: 50, use_rerank: true,
    }),
  });
}
```

`frontend/src/api/answers.ts`:

```ts
import { apiFetch } from "./base";
import type { AnswerRow } from "../types/answers";

export async function getAnswers(taskId: number): Promise<{ answers: AnswerRow[] }> {
  return apiFetch(`/api/tasks/${taskId}/answers`);
}

export async function addAnswer(
  taskId: number,
  body: {
    video_id: string;
    frames: number[];
    answer_text?: string | null;
    position?: "top" | "end" | { after_id: number };
  }
): Promise<{ answer: AnswerRow }> {
  return apiFetch(`/api/tasks/${taskId}/answers`, {
    method: "POST",
    body: JSON.stringify({ position: "end", ...body }),
  });
}

export async function autofillAnswers(
  taskId: number,
  mode: "append" | "replace_auto" = "append",
  limit?: number
): Promise<{ added: number; total: number }> {
  return apiFetch(`/api/tasks/${taskId}/answers/autofill`, {
    method: "POST",
    body: JSON.stringify({ source: "last_search", mode, limit }),
  });
}

export async function patchAnswer(
  id: number,
  body: { version: number; video_id?: string; frames?: number[]; answer_text?: string | null }
): Promise<{ answer: AnswerRow }> {
  return apiFetch(`/api/answers/${id}`, { method: "PATCH", body: JSON.stringify(body) });
}

export async function deleteAnswer(id: number): Promise<{ ok: boolean }> {
  return apiFetch(`/api/answers/${id}`, { method: "DELETE" });
}

export async function reorderAnswer(
  taskId: number,
  body: { answer_id: number; before_id?: number; after_id?: number }
): Promise<{ answers: AnswerRow[] }> {
  return apiFetch(`/api/tasks/${taskId}/answers/reorder`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function setAnswerText(
  taskId: number,
  answerText: string,
  apply: "all" | "empty_only" = "all"
): Promise<{ updated: number }> {
  return apiFetch(`/api/tasks/${taskId}/answer-text`, {
    method: "PUT",
    body: JSON.stringify({ answer_text: answerText, apply }),
  });
}
```

- [ ] **Step 2: Write the hooks**

`frontend/src/hooks/useBoard.ts` — the whole point of this file is that it is the **only**
place board data is fetched, so swapping the 3 s poll for a WebSocket later touches one
file. S3 fetches once on mount and on demand; **S5 adds the interval**.

```ts
import { useCallback, useEffect, useState } from "react";

import { getBoard } from "../api/board";
import type { BoardResponse } from "../types/collab";

export function useBoard(packId?: number) {
  const [board, setBoard] = useState<BoardResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      setBoard(await getBoard(packId));
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load the board");
    }
  }, [packId]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  return { board, refresh, error };
}
```

`frontend/src/hooks/useAnswers.ts` — every mutation is optimistic and reconciles against
the server's reply. A `409` is surfaced as `conflict`, never merged.

```ts
import { useCallback, useEffect, useState } from "react";

import {
  addAnswer, autofillAnswers, deleteAnswer, getAnswers, patchAnswer, reorderAnswer,
} from "../api/answers";
import { ApiRequestError } from "../api/base";
import type { AnswerRow } from "../types/answers";

export interface AnswerConflict {
  mine: { id: number; frames: number[]; answer_text: string | null };
  theirs: AnswerRow;
}

export function useAnswers(taskId: number | null) {
  const [answers, setAnswers] = useState<AnswerRow[]>([]);
  const [conflict, setConflict] = useState<AnswerConflict | null>(null);

  const refresh = useCallback(async () => {
    if (taskId === null) {
      setAnswers([]);
      return;
    }
    setAnswers((await getAnswers(taskId)).answers);
  }, [taskId]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const patch = useCallback(
    async (row: AnswerRow, changes: { frames?: number[]; answer_text?: string | null;
                                      video_id?: string }) => {
      try {
        await patchAnswer(row.id, { version: row.version, ...changes });
      } catch (err) {
        // 409 carries the row as it now stands. The UI asks which to keep; it
        // never merges and never overwrites in silence.
        if (err instanceof ApiRequestError && err.status === 409) {
          const body = err.body as { detail?: { current?: AnswerRow } };
          const theirs = body?.detail?.current;
          if (theirs) {
            setConflict({
              mine: { id: row.id, frames: changes.frames ?? row.frames,
                      answer_text: changes.answer_text ?? row.answer_text },
              theirs,
            });
          }
        } else {
          throw err;
        }
      }
      await refresh();
    },
    [refresh]
  );

  const resolveConflict = useCallback(
    async (keep: "mine" | "theirs") => {
      if (conflict === null) return;
      if (keep === "mine") {
        await patchAnswer(conflict.mine.id, {
          version: conflict.theirs.version,
          frames: conflict.mine.frames,
          answer_text: conflict.mine.answer_text,
        });
      }
      setConflict(null);
      await refresh();
    },
    [conflict, refresh]
  );

  return {
    answers, conflict, refresh, patch, resolveConflict,
    add: async (body: Parameters<typeof addAnswer>[1]) => {
      if (taskId === null) return;
      await addAnswer(taskId, body);
      await refresh();
    },
    remove: async (id: number) => { await deleteAnswer(id); await refresh(); },
    move: async (body: Parameters<typeof reorderAnswer>[1]) => {
      if (taskId === null) return;
      await reorderAnswer(taskId, body);
      await refresh();
    },
    autofill: async (mode: "append" | "replace_auto" = "append") => {
      if (taskId === null) return { added: 0, total: 0 };
      const result = await autofillAnswers(taskId, mode);
      await refresh();
      return result;
    },
  };
}
```

- [ ] **Step 3: Write the workspace store**

`frontend/src/store/workspaceStore.ts`:

```ts
import { create } from "zustand";

import type { SearchResult } from "../types/api";

interface WorkspaceState {
  taskId: number | null;
  results: SearchResult[];
  tookMs: number;
  selectedIndex: number;
  mode: "grid" | "pin";
  setTask: (id: number | null) => void;
  setResults: (results: SearchResult[], tookMs: number) => void;
  select: (index: number) => void;
  setMode: (mode: "grid" | "pin") => void;
}

/**
 * View state only. Every answer, claim and ordering change lives on the server
 * (INV-3) - this store holds what the screen is currently looking at, and losing
 * it costs a re-search rather than a round's work.
 */
export const useWorkspaceStore = create<WorkspaceState>((set) => ({
  taskId: null,
  results: [],
  tookMs: 0,
  selectedIndex: 0,
  mode: "grid",
  setTask: (taskId) => set({ taskId, results: [], selectedIndex: 0, mode: "grid" }),
  setResults: (results, tookMs) => set({ results, tookMs, selectedIndex: 0 }),
  select: (selectedIndex) => set({ selectedIndex }),
  setMode: (mode) => set({ mode }),
}));
```

- [ ] **Step 4: Verify it compiles**

```bash
cd frontend && npm run build
```

Expected: success. There is nothing to test yet — every function here is a thin wrapper,
and the behaviour worth testing is in Tasks 19 and 20.

- [ ] **Step 5: Commit**

```bash
git add frontend/src
git commit -m "Front end: one hook per data family

useBoard is the only place board data is fetched, so replacing the poll with a
WebSocket later touches one file. useAnswers surfaces a 409 as a conflict the
user resolves rather than merging it: two people will edit row 1, and silently
picking a winner is how a verified answer disappears without anyone noticing.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 19: The results grid — colour by agreement, not by distance

**Files:**
- Create: `frontend/src/components/workspace/agreement.ts`, `agreement.test.ts`
- Create: `frontend/src/components/workspace/ResultGrid.tsx`
- Modify: `frontend/src/components/FrameDisplay/index.tsx`

**Interfaces:**
- Produces:
  - `agreementOf(result: SearchResult): "both" | "one" | "unknown"`
  - `frameOf(result: SearchResult): number | null` — **the only way the UI reads a frame number**
  - `AGREEMENT_CLASS: Record<Agreement, string>`

- [ ] **Step 1: Write the failing test**

`frontend/src/components/workspace/agreement.test.ts`:

```ts
import { describe, expect, it } from "vitest";

import { agreementOf, frameOf } from "./agreement";
import type { SearchResult } from "../../types/api";

const base: SearchResult = {
  frame: "L21_V015-0042-025605.jpg",
  name: "L21_V015-0042-025605.jpg",
  url: "/static/images/L21_V015-0042-025605.jpg",
  distance: 88.5,
};

describe("agreementOf", () => {
  it("reports both when two models found the frame", () => {
    expect(agreementOf({
      ...base,
      routes: { beit3: { rank: 1, score: 0.41 }, clip: { rank: 3, score: 0.38 } },
    })).toBe("both");
  });

  it("reports one when a single model found it", () => {
    expect(agreementOf({ ...base, routes: { beit3: { rank: 1, score: 0.41 } } }))
      .toBe("one");
  });

  it("reports unknown when routes is absent", () => {
    expect(agreementOf(base)).toBe("unknown");
    expect(agreementOf({ ...base, routes: {} })).toBe("unknown");
  });
});

describe("frameOf", () => {
  it("uses frame_idx and never the filename", () => {
    // The filename ends in 025605 and the backend says the frame is 25605.
    // Reading the filename as milliseconds is the bug this replaces: it made
    // frame 25605 seek to second 25.6 instead of second 1024.
    expect(frameOf({ ...base, frame_idx: 25605 })).toBe(25605);
  });

  it("returns null rather than guessing when frame_idx is missing", () => {
    expect(frameOf(base)).toBeNull();
  });

  it("accepts frame zero", () => {
    expect(frameOf({ ...base, frame_idx: 0 })).toBe(0);
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd frontend && npm run test
```

Expected: FAIL — `./agreement` does not exist.

- [ ] **Step 3: Write the module**

`frontend/src/components/workspace/agreement.ts`:

```ts
import type { SearchResult } from "../../types/api";

export type Agreement = "both" | "one" | "unknown";

/**
 * How many models found this frame.
 *
 * The old grid coloured tiles by `distance`, which made every tile green
 * because every distance is high - a gradient carrying no information. `routes`
 * has been in every response from the start and was read by nothing: it records
 * which model ranked this frame and where. Two independent models agreeing is a
 * far stronger signal than one model's confidence, and it costs no computation
 * because the backend already worked it out.
 */
export function agreementOf(result: SearchResult): Agreement {
  const count = Object.keys(result.routes ?? {}).length;
  if (count >= 2) return "both";
  if (count === 1) return "one";
  return "unknown";
}

/**
 * The frame number this result submits (INV-2).
 *
 * There is exactly one legal source: the backend's `frame_idx`, which comes
 * straight from keyframe_metadata.json. Deriving it from the filename - which
 * the pre-redesign screen did, reading the trailing digits as milliseconds -
 * was wrong by a factor of fps, 25 to 30 times. Returning null when it is
 * absent is deliberate: a missing frame number must look missing, not like a
 * plausible zero.
 */
export function frameOf(result: SearchResult): number | null {
  return typeof result.frame_idx === "number" ? result.frame_idx : null;
}

export const AGREEMENT_CLASS: Record<Agreement, string> = {
  both: "bg-emerald-500",
  one: "bg-amber-500",
  unknown: "bg-slate-400",
};

export const AGREEMENT_LABEL: Record<Agreement, string> = {
  both: "BEiT3 + CLIP",
  one: "one model",
  unknown: "no route data",
};
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
cd frontend && npm run test
```

Expected: 6 passed.

- [ ] **Step 5: Write the grid component**

`frontend/src/components/workspace/ResultGrid.tsx`. Required behaviour:

1. Props: `results: SearchResult[]`, `selectedIndex: number`, `basketByKey: Map<string, number>`
   (`"video:frame"` → rank), `onSelect(index)`, `onAdd(result)`.
2. Each tile: the image (or the existing `MissingFrame` placeholder when
   `has_image === false` — **a tile with no image is still a valid answer**, so `onAdd`
   stays enabled), `agreementOf` driving the border colour via `AGREEMENT_CLASS`,
   `AGREEMENT_LABEL` as the `title`, `frameOf(result)` shown as the frame number, and
   `result.timestamp` beside it.
3. When `basketByKey` has this tile, a `#n` badge showing its rank.
4. The selected tile has a visible ring; clicking selects, double-clicking calls `onAdd`.
5. **No distance gradient anywhere.** Show the raw score as text if you want it visible.

Then delete `calculateSimilarityScore` and `extractTimestamp` from
`frontend/src/components/FrameDisplay/index.tsx`, and have it re-export nothing the new
grid does not use. `pages/Search.tsx` may keep using `FrameDisplay` until Task 21 removes
that screen.

- [ ] **Step 6: Commit**

```bash
git add frontend/src
git commit -m "Colour result tiles by model agreement instead of by distance

routes has been in every search response from the beginning and was read by
nothing. It records which model ranked a frame and where, so two models agreeing
is visible for free - while the old distance gradient painted every tile green,
because every distance is high.

frameOf() is now the only way the UI reads a frame number, and it reads
frame_idx. The screen it replaces parsed the trailing digits of the filename as
milliseconds, which sent frame 25605 to second 25.6 instead of second 1024 - the
error factor was the video's fps.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 20: The answer basket

**Files:**
- Create: `frontend/src/components/workspace/rankBoundaries.ts`, `rankBoundaries.test.ts`
- Create: `frontend/src/components/workspace/AnswerBasket.tsx`

**Interfaces:**
- Produces:
  - `R_AT_K: readonly number[]` = `[1, 5, 20, 50, 100]`
  - `boundaryAfter(rank: number): number | null` — the `k` whose line is drawn **below** this row
  - `originStripe(row: AnswerRow, myUserId: number): "mine" | "teammate" | "auto"`

- [ ] **Step 1: Write the failing test**

`frontend/src/components/workspace/rankBoundaries.test.ts`:

```ts
import { describe, expect, it } from "vitest";

import { boundaryAfter, originStripe, R_AT_K } from "./rankBoundaries";
import type { AnswerRow } from "../../types/answers";

const row = (over: Partial<AnswerRow>): AnswerRow => ({
  id: 1, task_id: 7, rank: 1, video_id: "L21_V015", frames: [25605],
  answer_text: null, origin: "auto", created_by: null, updated_by: null,
  updated_at: "2026-08-16T00:00:00Z", version: 1, ...over,
});

describe("boundaryAfter", () => {
  it("draws a line under each scoring threshold", () => {
    for (const k of R_AT_K) {
      expect(boundaryAfter(k)).toBe(k);
    }
  });

  it("draws nothing between thresholds", () => {
    // Moving an answer from rank 7 to rank 6 gains nothing; from 6 to 5 gains
    // 20%. The lines exist so nobody has to hold that in their head.
    expect(boundaryAfter(2)).toBeNull();
    expect(boundaryAfter(6)).toBeNull();
    expect(boundaryAfter(99)).toBeNull();
  });

  it("draws nothing past the last threshold", () => {
    expect(boundaryAfter(101)).toBeNull();
  });
});

describe("originStripe", () => {
  it("marks a row I verified", () => {
    expect(originStripe(row({ origin: "manual", updated_by: { id: 2, display_name: "Nam" } }), 2))
      .toBe("mine");
  });

  it("marks a teammate's row", () => {
    expect(originStripe(row({ origin: "manual", updated_by: { id: 3, display_name: "Lan" } }), 2))
      .toBe("teammate");
  });

  it("falls back to the creator when nobody has edited it", () => {
    expect(originStripe(row({ origin: "manual", created_by: { id: 3, display_name: "Lan" } }), 2))
      .toBe("teammate");
  });

  it("leaves auto-filled rows unmarked", () => {
    expect(originStripe(row({ origin: "auto" }), 2)).toBe("auto");
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd frontend && npm run test
```

Expected: FAIL — the module does not exist.

- [ ] **Step 3: Write the module**

`frontend/src/components/workspace/rankBoundaries.ts`:

```ts
import type { AnswerRow } from "../../types/answers";

/**
 * The only ranks that change the score.
 *
 * Final = (R@1 + R@5 + R@20 + R@50 + R@100) / 5, and each R@k is the best
 * R-Score among the first k rows. So moving an answer from rank 7 to rank 6
 * gains exactly nothing, and moving it from 6 to 5 gains a fifth of the total.
 * Nobody computes that under a clock, so the basket draws the five lines and
 * the arithmetic stops being the user's problem.
 */
export const R_AT_K = [1, 5, 20, 50, 100] as const;

export function boundaryAfter(rank: number): number | null {
  return (R_AT_K as readonly number[]).includes(rank) ? rank : null;
}

export type Stripe = "mine" | "teammate" | "auto";

/** Who put this row here, so two people do not verify the same frame twice. */
export function originStripe(row: AnswerRow, myUserId: number): Stripe {
  if (row.origin !== "manual") return "auto";
  const owner = row.updated_by ?? row.created_by;
  if (owner === null) return "auto";
  return owner.id === myUserId ? "mine" : "teammate";
}

export const STRIPE_CLASS: Record<Stripe, string> = {
  mine: "border-l-4 border-emerald-500",
  teammate: "border-l-4 border-violet-500",
  auto: "border-l-4 border-transparent",
};
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
cd frontend && npm run test
```

Expected: 7 passed.

- [ ] **Step 5: Write the basket component**

`frontend/src/components/workspace/AnswerBasket.tsx`. Required behaviour:

1. Props: `task: BoardTask`, `answers: AnswerRow[]`, `rowsPerQuery: number`,
   `myUserId: number`, and the mutators from `useAnswers`.
2. A scrolling list of every row, each showing `rank`, the origin stripe from
   `STRIPE_CLASS`, `video_id`, and the frames.
3. **After any row whose rank `boundaryAfter` returns non-null, render a labelled
   divider** — `R@5` and so on.
4. Type variants:
   - **KIS** — one editable frame field.
   - **Q&A** — the frame field plus an `answer` field, and a header control that calls
     `setAnswerText(taskId, value, "all" | "empty_only")`.
   - **TRAKE** — `n_events` frame fields, each labelled with its `event_labels[i]`, and a
     **warning banner when `task.import_warnings` is non-empty** so the E-number anomaly
     stays visible where the frames are typed. A row with a blank frame is marked; a row
     whose `video_id` differs from row 1's shows the "wrong video scores zero" caution.
5. A header showing `answers.length / rowsPerQuery`, an `Autofill` button, and a
   `Deduplicate` button.
6. Every edit calls `patch(row, changes)` from `useAnswers`, so a `409` surfaces as the
   conflict dialog rather than a silent overwrite.

- [ ] **Step 6: Commit**

```bash
git add frontend/src
git commit -m "The answer basket, with the five scoring lines drawn in

Final score is the mean of R@1, R@5, R@20, R@50 and R@100, so rank 7 to rank 6
is worth nothing and 6 to 5 is worth a fifth of the total. Drawing the lines
means nobody has to hold that in their head while the clock runs.

Origin stripes exist for the same reason presence does: with five people on one
round, seeing that a teammate already verified a frame is what stops two people
verifying it twice.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 21: The Workspace screen

**Files:**
- Create: `frontend/src/components/workspace/TaskRail.tsx`
- Create: `frontend/src/pages/Workspace.tsx`
- Create: `frontend/src/pages/Board.tsx`
- Modify: `frontend/src/App.tsx`
- Delete: `frontend/src/pages/Search.tsx`

**Interfaces:**
- Consumes: `useBoard`, `useAnswers`, `useWorkspaceStore`, `searchInTask`, `ResultGrid`,
  `AnswerBasket`, `TaskRail`.
- Produces: the `board` and `workspace` screens of `screenFor`.

- [ ] **Step 1: Write `TaskRail.tsx`**

A vertical strip, one dot per task, no numbers:

```tsx
import type { BoardTask } from "../../types/collab";

/**
 * Task state as colour, because a rail of numbers is unreadable at a glance and
 * the only questions it has to answer are "which is done" and "which is free".
 */
export function dotClass(task: BoardTask, rowsPerQuery: number): string {
  if (task.answer_count >= rowsPerQuery) return "bg-emerald-500";
  if (task.answer_count > 0 || task.owner !== null) return "bg-amber-500";
  return "border border-slate-400 bg-transparent";
}

export default function TaskRail({
  tasks, rowsPerQuery, selectedId, onSelect,
}: {
  tasks: BoardTask[];
  rowsPerQuery: number;
  selectedId: number | null;
  onSelect: (id: number) => void;
}) {
  return (
    <nav className="flex w-14 flex-col items-center gap-2 overflow-y-auto p-2">
      {tasks.map((task) => (
        <button
          key={task.id}
          title={`${task.code} · ${task.type.toUpperCase()} · ${task.answer_count}/${rowsPerQuery}`}
          onClick={() => onSelect(task.id)}
          className={`h-6 w-6 rounded-full ${dotClass(task, rowsPerQuery)} ${
            task.id === selectedId ? "ring-2 ring-slate-900" : ""
          }`}
        />
      ))}
    </nav>
  );
}
```

- [ ] **Step 2: Write `Board.tsx`**

A table of the columns in spec §9.1 — code · type · query (Vietnamese, verbatim, clamped
to two lines) · owner (`—` until S5) · `answer_count / rows_per_query` · viewers (empty
until S5). Clicking a row calls `onOpenTask(task.id)`. Show `round.label` and, when
`import_warnings` is non-empty on a task, an amber marker on its row.

- [ ] **Step 3: Write `Workspace.tsx`**

Three columns exactly as spec §9.2 — switching mode changes only the middle one:

```tsx
<div className="flex h-screen">
  <TaskRail … />
  <main className="flex min-w-0 flex-1 flex-col">
    {/* query bar: input, mode select, Search */}
    {mode === "grid" ? <ResultGrid … /> : <PinFrame … />}   {/* PinFrame: S6 */}
  </main>
  <aside className="w-[420px] shrink-0 border-l">
    <AnswerBasket … />
  </aside>
</div>
```

Required behaviour:

1. The selected task's `query_text` is displayed **verbatim** above the query bar, with
   `question_text` beneath it for Q&A and the event labels listed for TRAKE (INV-4 — this
   is the organizer's text and nothing translates it).
2. The query input is **separate** from the task text: it is what the user types for the
   search, in whatever language they like.
3. `Search` calls `searchInTask(taskId, query, mode, limit)` and puts the results into
   `useWorkspaceStore`. `limit` reads `board.rows_per_query`, not a literal 100.
4. `basketByKey` is built from `answers` as `` `${video_id}:${frames[0]}` `` → `rank`, and
   passed to `ResultGrid` so tiles already in the basket show `#n`.
5. Until S6, `mode` stays `"grid"`; the `pin` branch renders a placeholder line saying the
   frame picker arrives in S6. **This is the only deliberately unfinished branch in the
   plan, and S6 Task 29 replaces it.**
6. Render the conflict dialog when `conflict !== null`: show both versions and two buttons,
   `Keep mine` and `Keep theirs`, wired to `resolveConflict`.

- [ ] **Step 4: Wire both screens into `App.tsx` and delete the old screen**

```tsx
  if (screen === "board") {
    return <Board onOpenTask={(id) => { setTaskId(id); setRequested("workspace"); }} />;
  }
  if (screen === "workspace") return <Workspace onNavigate={setRequested} />;
```

Then:

```bash
git rm frontend/src/pages/Search.tsx
```

Remove the `Search` import from `App.tsx`.

- [ ] **Step 5: Verify end to end by hand**

With both servers running and the pack imported: open the board, click a task, type a
query, search. Confirm that tiles are green or amber and not all green; that the frame
number shown matches `frame_idx` in the network response; that `Autofill` fills the basket
to 100; that the `R@5` line appears under row 5; and that reloading the page keeps every
row.

- [ ] **Step 6: Commit**

```bash
git add -A frontend/src
git commit -m "The three-column workspace replaces the single search screen

Task rail, results grid and the answer basket, with the middle column the only
one that changes when the mode does. The organizer's query is displayed above
the search box and is never what gets searched: it is Vietnamese, it is shown
verbatim, and the user types their own query in whatever language works.

The pre-redesign screen is deleted. Its dead controls sent nothing anywhere -
they were parameters of six endpoints removed months ago - and its submit path
kept the round's work in memory where a refresh destroyed it.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

# Slice S4 — Export · the competition-ready line

**After this slice the system can compete.** Everything later improves speed and accuracy;
nothing later adds capability.

---

### Task 22: The exporter — TST-11

**Files:**
- Create: `backend/app/export_store.py`
- Create: `backend/tests/test_export_store.py`

**Interfaces:**
- Produces:
  - `row_for(task, answer) -> list[str]`
  - `render_csv(task, answers, settings: dict) -> bytes`
  - `filename_for(task, pack, pattern: str) -> str`
  - `validate_pack(conn, pack_id) -> list[dict]` — `{task_code, severity, message}`
  - `build_zip(conn, pack_id) -> bytes`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_export_store.py`:

```python
"""TST-11 — byte-exact submission rows.

The expected bytes are taken from docs/Danh_gia_Query_AIC2025.md, which records
the answers actually submitted for the AIC 2025 queries - the same queries that
are in sample-data/query-p1-groupA.zip. These are not a shape we invented.
"""
from __future__ import annotations

import sqlite3

from app.export_store import filename_for, render_csv, row_for

SETTINGS = {
    "export.delimiter": ",",
    "export.header": False,
    "export.line_ending": "LF",
    "export.encoding": "utf-8",
    "export.rows_per_query": 100,
    "export.filename_pattern": "query-{phase}-{code}-{type}.csv",
}


def _task(**over) -> dict:
    return {"code": "1", "type": "kis", "n_events": None, **over}


def _answer(video_id, frames, answer_text=None) -> dict:
    return {"video_id": video_id, "frames": frames, "answer_text": answer_text}


def test_kis_row():
    assert row_for(_task(), _answer("L21_V015", [25605])) == ["L21_V015", "25605"]


def test_qa_row_carries_the_answer():
    row = row_for(_task(type="qa"), _answer("L30_V072", [1745], "Xã Giang Ly"))

    assert row == ["L30_V072", "1745", "Xã Giang Ly"]


def test_trake_row_is_video_then_one_frame_per_moment():
    row = row_for(
        _task(type="trake", n_events=4),
        _answer("L26_V194", [4707, 5100, 5425, 5850]),
    )

    assert row == ["L26_V194", "4707", "5100", "5425", "5850"]


def test_a_qa_answer_containing_a_comma_is_quoted():
    """The single most dangerous row in the format.

    This is a real 2025 answer. Joining fields with ',' - which is what a naive
    exporter does - turns one three-field row into a four-field row. The file
    stays valid CSV, nothing on our side looks wrong, and every answer after the
    comma lands in the wrong column.
    """
    answer = "Hoả hồng Nhật Tảo oanh thiên địa, Kiếm bạch Kiên Giang khấp quỷ thần."
    data = render_csv(
        _task(code="19", type="qa"),
        [_answer("L27_V010", [5550], answer)],
        SETTINGS,
    )

    assert data == (
        'L27_V010,5550,"Hoả hồng Nhật Tảo oanh thiên địa, '
        'Kiếm bạch Kiên Giang khấp quỷ thần."\n'
    ).encode("utf-8")


def test_no_byte_order_mark():
    """The riskiest default in the format.

    The credentials CSV carries a BOM so Excel renders Vietnamese. If the
    submission file carries one and the organizer's parser does not strip it,
    the first field of the first row is corrupt in every file - and nothing on
    our side looks wrong.
    """
    data = render_csv(_task(), [_answer("L21_V015", [25605])], SETTINGS)

    assert not data.startswith(b"\xef\xbb\xbf")
    assert data[:8] == b"L21_V015"


def test_row_order_is_preserved_because_row_order_is_the_score():
    data = render_csv(
        _task(),
        [_answer("L21_V015", [25605]), _answer("L21_V015", [25580]),
         _answer("L03_V008", [11402])],
        SETTINGS,
    )

    assert data.decode("utf-8").splitlines() == [
        "L21_V015,25605", "L21_V015,25580", "L03_V008,11402",
    ]


def test_rows_are_capped_at_the_configured_limit():
    answers = [_answer("L21_V015", [i]) for i in range(150)]

    data = render_csv(_task(), answers, {**SETTINGS, "export.rows_per_query": 100})

    assert len(data.decode("utf-8").splitlines()) == 100


def test_crlf_and_a_semicolon_are_settings_not_code():
    data = render_csv(
        _task(),
        [_answer("L21_V015", [25605])],
        {**SETTINGS, "export.line_ending": "CRLF", "export.delimiter": ";"},
    )

    assert data == b"L21_V015;25605\r\n"


def test_filename_reuses_the_input_stem():
    name = filename_for(
        _task(code="15", type="qa"), {"phase": "p1"},
        "query-{phase}-{code}-{type}.csv",
    )

    assert name == "query-p1-15-qa.csv"


def test_a_task_with_no_answers_still_renders_an_empty_file():
    """An empty file says 'we had nothing'. A missing file is indistinguishable
    from a packaging bug."""
    assert render_csv(_task(), [], SETTINGS) == b""
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd backend && ./venv/Scripts/python.exe -m pytest tests/test_export_store.py -v
```

Expected: `ModuleNotFoundError: No module named 'app.export_store'`.

- [ ] **Step 3: Write the exporter**

Create `backend/app/export_store.py`:

```python
"""Build the submission files.

Row shapes are confirmed against docs/Danh_gia_Query_AIC2025.md, which records
what was actually submitted for these queries last season:

    KIS     L21_V015,25605
    Q&A     L30_V072,1745,Xã Giang Ly
    Q&A     L27_V010,5550,"Hoả hồng Nhật Tảo oanh thiên địa, Kiếm bạch …"
    TRAKE   L26_V194,4707,5100,5425,5850

The quoted Q&A line is why this module uses the csv module rather than joining
strings. A real answer contains a comma; joining turns a three-field row into a
four-field one, the file stays syntactically valid, and nothing on our side
looks wrong.

Every byte below is a setting. When the organizer publishes their format, the
change is DEFAULTS and one admin screen - not this file.
"""
from __future__ import annotations

import csv
import io
import json
import sqlite3
import zipfile
from typing import Any

LINE_ENDINGS = {"LF": "\n", "CRLF": "\r\n"}


def _frames(answer: Any) -> list[int]:
    raw = answer["frames"]
    return json.loads(raw) if isinstance(raw, str) else list(raw)


def row_for(task: Any, answer: Any) -> list[str]:
    """One submission row. Field order is the organizer's, not ours."""
    frames = _frames(answer)
    video_id = answer["video_id"]

    if task["type"] == "trake":
        return [video_id, *[str(f) for f in frames]]

    head = [video_id, str(frames[0]) if frames else ""]
    if task["type"] == "qa":
        return [*head, answer["answer_text"] or ""]
    return head


def render_csv(task: Any, answers: list[Any], settings: dict[str, Any]) -> bytes:
    """The exact bytes of one task's file."""
    limit = int(settings["export.rows_per_query"])
    terminator = LINE_ENDINGS[str(settings["export.line_ending"])]

    buffer = io.StringIO()
    writer = csv.writer(
        buffer,
        delimiter=str(settings["export.delimiter"]),
        lineterminator=terminator,
        quoting=csv.QUOTE_MINIMAL,   # RFC 4180: quote only when a field needs it
    )

    if settings.get("export.header"):
        writer.writerow(_header_for(task))

    for answer in answers[:limit]:
        writer.writerow(row_for(task, answer))

    # utf-8 by default and deliberately not utf-8-sig: a BOM the organizer's
    # parser does not strip corrupts the first field of the first row in every
    # file. utf-8-sig remains a legal setting for the day they say otherwise.
    return buffer.getvalue().encode(str(settings["export.encoding"]))


def _header_for(task: Any) -> list[str]:
    if task["type"] == "trake":
        count = int(task["n_events"] or 1)
        return ["video_id", *[f"frame_{i}" for i in range(1, count + 1)]]
    if task["type"] == "qa":
        return ["video_id", "frame_id", "answer"]
    return ["video_id", "frame_id"]


def filename_for(task: Any, pack: Any, pattern: str) -> str:
    """Reuses the input stem so a reviewer can line the two files up."""
    phase = (pack["phase"] if pack is not None else None) or ""
    return (
        pattern.replace("{phase}", phase)
        .replace("{code}", str(task["code"]))
        .replace("{type}", str(task["type"]))
        .replace("{id}", str(task["code"]))     # tolerated legacy placeholder
    )


def _settings(conn: sqlite3.Connection) -> dict[str, Any]:
    from app.settings_store import all_settings

    return all_settings(conn)


def _tasks(conn: sqlite3.Connection, pack_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM tasks WHERE pack_id = ? ORDER BY CAST(code AS INTEGER)",
        (pack_id,),
    ).fetchall()


def _answers(conn: sqlite3.Connection, task_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM answers WHERE task_id = ? ORDER BY sort_key", (task_id,)
    ).fetchall()


def validate_pack(conn: sqlite3.Connection, pack_id: int) -> list[dict[str, Any]]:
    """Everything worth knowing before the file leaves the building.

    Nothing here blocks an export. A warning the user chose to accept is still a
    submission; a row silently dropped for being imperfect is a lost chance,
    because R@k only ever rewards having more answers.
    """
    issues: list[dict[str, Any]] = []
    limit = int(_settings(conn)["export.rows_per_query"])

    for task in _tasks(conn, pack_id):
        answers = _answers(conn, task["id"])
        code = task["code"]

        if not answers:
            issues.append({"task_code": code, "severity": "warning",
                           "message": "no answers - the file will be empty"})
            continue

        if len(answers) < limit:
            issues.append({
                "task_code": code, "severity": "info",
                "message": f"{len(answers)} of {limit} rows used - R@k is a max, "
                           "so the unused rows are free chances",
            })

        if task["type"] == "qa":
            empty = sum(1 for a in answers if not (a["answer_text"] or "").strip())
            if empty:
                issues.append({"task_code": code, "severity": "warning",
                               "message": f"{empty} rows have an empty answer"})

        if task["type"] == "trake":
            expected = int(task["n_events"] or 0)
            short = sum(1 for a in answers if len(_frames(a)) < expected)
            if short:
                issues.append({
                    "task_code": code, "severity": "warning",
                    "message": f"{short} rows have fewer than {expected} moments - "
                               "a missing moment scores zero for that moment",
                })
            videos = {a["video_id"] for a in answers}
            if len(videos) > 1:
                issues.append({
                    "task_code": code, "severity": "info",
                    "message": f"answers span {len(videos)} videos - a wrong video "
                               "scores zero for the whole row",
                })

        seen: set[tuple[str, str]] = set()
        duplicates = 0
        for answer in answers:
            key = (answer["video_id"], json.dumps(_frames(answer)))
            if key in seen:
                duplicates += 1
            seen.add(key)
        if duplicates:
            issues.append({"task_code": code, "severity": "info",
                           "message": f"{duplicates} duplicate rows - each one is a "
                                      "wasted slot"})

    return issues


def preview_task(conn: sqlite3.Connection, task_id: int) -> dict[str, Any]:
    task = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    if task is None:
        raise KeyError(task_id)
    pack = conn.execute(
        "SELECT * FROM packs WHERE id = ?", (task["pack_id"],)
    ).fetchone()

    settings = _settings(conn)
    data = render_csv(task, _answers(conn, task_id), settings)

    return {
        "filename": filename_for(task, pack, str(settings["export.filename_pattern"])),
        "rows": len(data.decode(str(settings["export.encoding"])).splitlines()),
        "bytes": len(data),
        "content": data.decode(str(settings["export.encoding"])),
    }


def build_zip(conn: sqlite3.Connection, pack_id: int) -> bytes:
    """A flat archive, one file per task - including tasks with no answers.

    An empty file says "we had nothing for this query". A missing file is
    indistinguishable from a packaging bug, and the difference is only
    discoverable after the deadline.
    """
    settings = _settings(conn)
    pattern = str(settings["export.filename_pattern"])
    pack = conn.execute("SELECT * FROM packs WHERE id = ?", (pack_id,)).fetchone()

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for task in _tasks(conn, pack_id):
            archive.writestr(
                filename_for(task, pack, pattern),
                render_csv(task, _answers(conn, task["id"]), settings),
            )
    return buffer.getvalue()
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
cd backend && ./venv/Scripts/python.exe -m pytest tests/test_export_store.py -v
```

Expected: 10 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/export_store.py backend/tests/test_export_store.py
git commit -m "Build the submission file, byte for byte

Row shapes come from docs/Danh_gia_Query_AIC2025.md - what was actually
submitted for these same queries last season - rather than from a guess. The
Q&A row that decided the implementation is real: its answer contains a comma,
so joining fields with ',' turns three fields into four. The file stays valid
CSV, nothing on our side looks wrong, and every field after the comma is in the
wrong column. csv.QUOTE_MINIMAL is what makes that impossible.

No BOM, and that is a decision rather than an accident: the credentials CSV
carries one so Excel renders Vietnamese, but if the organizer's parser does not
strip one here, the first field of the first row is corrupt in every file.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 23: Export endpoints — TST-12

**Files:**
- Create: `backend/app/routers/export.py`
- Create: `backend/tests/test_export_api.py`
- Modify: `backend/app/main.py`

**Interfaces:**
- Produces: `GET /api/export/validate?pack_id=` · `GET /api/export/preview?task_id=` ·
  `GET /api/export/zip?pack_id=` (`application/zip`, `Content-Disposition: attachment`).

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_export_api.py`:

```python
"""TST-12 — the archive is complete and carries no BOM."""
from __future__ import annotations

import io
import zipfile

from tests.conftest import auth_headers


def _seed_answers(client, admin, tasks):
    """Ground-truth answers for three real queries, one of each type."""
    truth = {
        "1": ("L21_V015", [25605], None),
        "19": ("L27_V010", [5550],
               "Hoả hồng Nhật Tảo oanh thiên địa, Kiếm bạch Kiên Giang khấp quỷ thần."),
        "4": ("L26_V194", [4707, 5100, 5425, 5850], None),
    }
    for task in tasks:
        if task["code"] not in truth:
            continue
        video_id, frames, answer_text = truth[task["code"]]
        client.post(
            f"/api/tasks/{task['id']}/answers",
            json={"video_id": video_id, "frames": frames, "answer_text": answer_text},
            headers=auth_headers(admin["token"]),
        )


def test_preview_returns_the_real_bytes(client, admin, seeded_tasks):
    _seed_answers(client, admin, seeded_tasks)
    task = next(t for t in seeded_tasks if t["code"] == "19")

    response = client.get(
        f"/api/export/preview?task_id={task['id']}",
        headers=auth_headers(admin["token"]),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["filename"] == "query-p1-19-qa.csv"
    assert body["content"] == (
        'L27_V010,5550,"Hoả hồng Nhật Tảo oanh thiên địa, '
        'Kiếm bạch Kiên Giang khấp quỷ thần."\n'
    )


def test_the_zip_has_one_file_per_task_including_empty_ones(
    client, admin, seeded_tasks
):
    _seed_answers(client, admin, seeded_tasks)
    pack_id = seeded_tasks[0]["pack_id"]

    response = client.get(
        f"/api/export/zip?pack_id={pack_id}", headers=auth_headers(admin["token"])
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"

    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        names = archive.namelist()
        assert len(names) == 24
        assert "query-p1-1-kis.csv" in names
        assert "query-p1-4-trake.csv" in names
        # A task nobody answered still gets a file: an empty file says "we had
        # nothing", a missing one is indistinguishable from a packaging bug.
        assert archive.read("query-p1-2-kis.csv") == b""
        assert archive.read("query-p1-1-kis.csv") == b"L21_V015,25605\n"
        assert archive.read("query-p1-4-trake.csv") == b"L26_V194,4707,5100,5425,5850\n"
        for name in names:
            assert not archive.read(name).startswith(b"\xef\xbb\xbf")


def test_validate_reports_empty_tasks_without_blocking(client, admin, seeded_tasks):
    _seed_answers(client, admin, seeded_tasks)
    pack_id = seeded_tasks[0]["pack_id"]

    response = client.get(
        f"/api/export/validate?pack_id={pack_id}", headers=auth_headers(admin["token"])
    )

    assert response.status_code == 200
    issues = response.json()["issues"]
    assert any(i["message"].startswith("no answers") for i in issues)
    # Nothing here is an error: a warning the user accepted is still a submission.
    assert all(i["severity"] in ("info", "warning") for i in issues)
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd backend && ./venv/Scripts/python.exe -m pytest tests/test_export_api.py -v
```

Expected: 404s.

- [ ] **Step 3: Write the router**

Create `backend/app/routers/export.py`:

```python
"""Export: validate, preview the exact bytes, then download the archive.

Preview returns `content` as text on purpose. A preview that renders a table
hides exactly the failure it exists to catch - a stray quote, a BOM, a field in
the wrong column.
"""
from __future__ import annotations

import sqlite3
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Response

from app import export_store
from app.auth.deps import active_user
from app.db.connection import get_db

router = APIRouter(prefix="/api/export", tags=["export"])


def _active_pack_id(conn: sqlite3.Connection, pack_id: int | None) -> int:
    if pack_id is not None:
        return pack_id
    row = conn.execute(
        "SELECT id FROM packs WHERE active = 1 ORDER BY id DESC LIMIT 1"
    ).fetchone()
    if row is None:
        raise HTTPException(404, "No pack has been imported")
    return row["id"]


@router.get("/validate")
def validate(
    _user: Annotated[sqlite3.Row, Depends(active_user)],
    conn: Annotated[sqlite3.Connection, Depends(get_db)],
    pack_id: int | None = None,
) -> dict[str, Any]:
    resolved = _active_pack_id(conn, pack_id)
    issues = export_store.validate_pack(conn, resolved)
    return {
        "pack_id": resolved,
        # `ready` is advice, never a gate. A warning the user has read and
        # accepted is still a submission, and a blocked export at 23:55 is worse
        # than an imperfect one.
        "ready": not any(i["severity"] == "warning" for i in issues),
        "issues": issues,
    }


@router.get("/preview")
def preview(
    task_id: int,
    _user: Annotated[sqlite3.Row, Depends(active_user)],
    conn: Annotated[sqlite3.Connection, Depends(get_db)],
) -> dict[str, Any]:
    try:
        return export_store.preview_task(conn, task_id)
    except KeyError as exc:
        raise HTTPException(404, "No such task") from exc


@router.get("/zip")
def download(
    _user: Annotated[sqlite3.Row, Depends(active_user)],
    conn: Annotated[sqlite3.Connection, Depends(get_db)],
    pack_id: int | None = None,
) -> Response:
    resolved = _active_pack_id(conn, pack_id)
    data = export_store.build_zip(conn, resolved)
    return Response(
        content=data,
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="submission.zip"'},
    )
```

In `backend/app/main.py`, add `from app.routers import export as export_router` and
`app.include_router(export_router.router)`.

- [ ] **Step 4: Run the tests to verify they pass**

```bash
cd backend && ./venv/Scripts/python.exe -m pytest tests/test_export_api.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Run the whole backend suite**

```bash
cd backend && ./venv/Scripts/python.exe -m pytest -v -m "not slow"
```

Expected: everything green. Then run the guard on its own:

```bash
cd backend && ./venv/Scripts/python.exe -m pytest -v -m slow
```

Expected: TST-1 still passes. **This is the checkpoint that proves the whole collaboration
layer landed without moving retrieval.**

- [ ] **Step 6: Commit**

```bash
git add backend/app/routers/export.py backend/app/main.py backend/tests/test_export_api.py
git commit -m "Export endpoints: validate, byte preview, archive

The competition-ready line. Preview returns the file as text rather than as a
rendered table, because a rendered table hides exactly what the preview exists
to catch. `ready` is advice and never a gate: a warning someone has read and
accepted is still a submission, and an export blocked at 23:55 is worse than an
imperfect one.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 24: Front end — the export screen

**Files:**
- Create: `frontend/src/api/export.ts`
- Create: `frontend/src/pages/Export.tsx`
- Modify: `frontend/src/App.tsx`

**Interfaces:**
- Produces: `validateExport(packId?)` · `previewExport(taskId)` · `downloadExportZip(packId?)`.

- [ ] **Step 1: Write the client**

`frontend/src/api/export.ts`:

```ts
import { API_BASE_URL, apiFetch, ApiRequestError } from "./base";
import { useAuthStore } from "../store/authStore";

export interface ExportIssue {
  task_code: string;
  severity: "info" | "warning" | "error";
  message: string;
}

export interface ExportPreview {
  filename: string;
  rows: number;
  bytes: number;
  content: string;
}

export async function validateExport(
  packId?: number
): Promise<{ pack_id: number; ready: boolean; issues: ExportIssue[] }> {
  return apiFetch(`/api/export/validate${packId ? `?pack_id=${packId}` : ""}`);
}

export async function previewExport(taskId: number): Promise<ExportPreview> {
  return apiFetch<ExportPreview>(`/api/export/preview?task_id=${taskId}`);
}

/** A Blob, not JSON — apiFetch parses every body as JSON, so this goes direct. */
export async function downloadExportZip(packId?: number): Promise<Blob> {
  const { token } = useAuthStore.getState();
  const response = await fetch(
    `${API_BASE_URL}/api/export/zip${packId ? `?pack_id=${packId}` : ""}`,
    { headers: token ? { Authorization: `Bearer ${token}` } : undefined }
  );
  if (!response.ok) {
    throw new ApiRequestError(response.status, `HTTP ${response.status}`);
  }
  return response.blob();
}
```

- [ ] **Step 2: Write the screen**

`frontend/src/pages/Export.tsx`. Required behaviour, in this order down the page:

1. `Validate` runs on mount. Issues render grouped by `task_code`, warnings amber, info
   grey. **Nothing disables the download button** — `ready` is shown as a summary line, not
   as a gate.
2. A task selector; choosing one calls `previewExport` and renders `content` inside a
   `<pre>` with the byte count and row count above it. **Never a table** — the point is to
   see the bytes.
3. `Download submission.zip` calls `downloadExportZip`, then
   `URL.createObjectURL(blob)` on a temporary `<a download="submission.zip">`, clicks it,
   and revokes the URL.
4. A one-line reminder under the button naming what is still assumed rather than confirmed:
   *"Filename pattern and one-file-per-query packaging are our defaults, not the
   organizer's published format. Row contents are confirmed."*

- [ ] **Step 3: Add it to the switch**

`if (screen === "export") return <Export onNavigate={setRequested} />;` and a link to it
from `Board.tsx`.

- [ ] **Step 4: Verify end to end by hand**

Import the pack, answer one KIS task, open Export, confirm the preview shows
`L21_V015,25605` exactly, download the zip, and open it — 24 files, one per task.

- [ ] **Step 5: Commit**

```bash
git add frontend/src
git commit -m "Front end: the export screen

The preview is a <pre> of the file's own text, never a table. A table would
render a stray quote, a misplaced delimiter and a BOM as if nothing were wrong,
which is precisely the class of failure this screen exists to catch.

Validation never blocks the download. R@k only rewards having more answers, so
an imperfect file beats no file, and the person exporting at the deadline is not
the person to argue with.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

# Slice S5 — Collaboration

---

### Task 25: Claim and release — TST-13

**Files:**
- Modify: `backend/app/routers/board.py`
- Create: `backend/tests/test_claim.py`

**Interfaces:**
- Produces: `POST /api/tasks/{id}/claim` → `200 {task}` | `409 {detail, owner}` ·
  `POST /api/tasks/{id}/release` · `POST /api/admin/tasks/{id}/force-release`.
  `board()` now fills `owner`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_claim.py`:

```python
"""TST-13 — two people claim one task at the same moment.

The requests are issued IN PARALLEL on purpose. A sequential version of this
test passes against a SELECT-then-IF implementation, which is the exact bug it
is supposed to catch: with a 3-second poll, two people genuinely do see the same
free task and genuinely do click at the same time.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from tests.conftest import auth_headers


def _settled_member(client, admin, username):
    created = client.post(
        "/api/admin/users/bulk",
        json={"members": [{"username": username, "display_name": username.title()}]},
        headers=auth_headers(admin["token"]),
    ).json()["created"][0]

    token = client.post(
        "/api/auth/login",
        json={"username": username, "password": created["password"]},
    ).json()["token"]

    client.post(
        "/api/auth/change-password",
        json={"current_password": created["password"], "new_password": f"{username}-pw-1"},
        headers=auth_headers(token),
    )
    return token


def test_exactly_one_of_two_parallel_claims_wins(client, admin, seeded_tasks):
    task_id = seeded_tasks[0]["id"]
    lan = _settled_member(client, admin, "lan")
    huy = _settled_member(client, admin, "huy")

    def claim(token):
        return client.post(
            f"/api/tasks/{task_id}/claim", headers=auth_headers(token)
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        first, second = [f.result() for f in
                         [pool.submit(claim, lan), pool.submit(claim, huy)]]

    codes = sorted([first.status_code, second.status_code])
    assert codes == [200, 409]

    loser = first if first.status_code == 409 else second
    # The 409 names the winner, so the UI can roll back with a useful message
    # rather than "something went wrong".
    assert loser.json()["detail"]["owner"]["display_name"] in ("Lan", "Huy")


def test_claiming_a_task_you_already_hold_succeeds(client, admin, seeded_tasks):
    """Re-claiming is idempotent: a double click must not lock you out of your
    own task."""
    task_id = seeded_tasks[0]["id"]

    first = client.post(f"/api/tasks/{task_id}/claim",
                        headers=auth_headers(admin["token"]))
    second = client.post(f"/api/tasks/{task_id}/claim",
                         headers=auth_headers(admin["token"]))

    assert first.status_code == 200
    assert second.status_code == 200


def test_release_frees_the_task(client, admin, seeded_tasks):
    task_id = seeded_tasks[0]["id"]
    client.post(f"/api/tasks/{task_id}/claim", headers=auth_headers(admin["token"]))

    response = client.post(f"/api/tasks/{task_id}/release",
                           headers=auth_headers(admin["token"]))

    assert response.status_code == 200
    assert response.json()["task"]["owner"] is None


def test_a_member_cannot_release_someone_elses_task(client, admin, seeded_tasks):
    task_id = seeded_tasks[0]["id"]
    lan = _settled_member(client, admin, "lan")
    client.post(f"/api/tasks/{task_id}/claim", headers=auth_headers(admin["token"]))

    response = client.post(f"/api/tasks/{task_id}/release", headers=auth_headers(lan))

    assert response.status_code == 403


def test_an_admin_can_force_release(client, admin, seeded_tasks):
    task_id = seeded_tasks[0]["id"]
    lan = _settled_member(client, admin, "lan")
    client.post(f"/api/tasks/{task_id}/claim", headers=auth_headers(lan))

    response = client.post(f"/api/admin/tasks/{task_id}/force-release",
                           headers=auth_headers(admin["token"]))

    assert response.status_code == 200
    assert response.json()["task"]["owner"] is None
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd backend && ./venv/Scripts/python.exe -m pytest tests/test_claim.py -v
```

Expected: 404s — the claim routes do not exist.

- [ ] **Step 3: Add claim, release and force-release to `board.py`**

```python
from app.auth.deps import require_admin
from app.db.connection import utcnow_iso
from fastapi import HTTPException


def _task_or_404(conn: sqlite3.Connection, task_id: int) -> sqlite3.Row:
    row = conn.execute(
        """SELECT t.*, u.display_name AS owner_name, u.username AS owner_username
             FROM tasks t LEFT JOIN users u ON u.id = t.owner_id
            WHERE t.id = ?""",
        (task_id,),
    ).fetchone()
    if row is None:
        raise HTTPException(404, "No such task")
    return row


def _single(conn: sqlite3.Connection, task_id: int) -> dict[str, Any]:
    row = _task_or_404(conn, task_id)
    payload = _task_row(row)
    payload["owner"] = (
        {"id": row["owner_id"], "display_name": row["owner_name"],
         "username": row["owner_username"]}
        if row["owner_id"] else None
    )
    return payload


@router.post("/tasks/{task_id}/claim")
def claim(
    task_id: int,
    user: Annotated[sqlite3.Row, Depends(active_user)],
    conn: Annotated[sqlite3.Connection, Depends(get_db)],
) -> dict[str, Any]:
    """One conditional UPDATE, never SELECT-then-IF.

    With a three-second poll, two people genuinely see the same free task and
    genuinely click at the same moment. Checking first and writing second leaves
    a window between the two in which both checks pass; putting the condition in
    the WHERE clause closes it, because SQLite resolves one writer at a time.
    """
    result = conn.execute(
        """UPDATE tasks
              SET owner_id = ?, claimed_at = ?, version = version + 1
            WHERE id = ? AND owner_id IS NULL""",
        (user["id"], utcnow_iso(), task_id),
    )

    if result.rowcount == 1:
        return {"task": _single(conn, task_id)}

    row = _task_or_404(conn, task_id)
    if row["owner_id"] == user["id"]:
        # Idempotent: a double click must not lock you out of your own task.
        return {"task": _single(conn, task_id)}

    raise HTTPException(
        status_code=409,
        detail={
            "detail": "Already claimed",
            "owner": {"id": row["owner_id"], "display_name": row["owner_name"]},
        },
    )


@router.post("/tasks/{task_id}/release")
def release(
    task_id: int,
    user: Annotated[sqlite3.Row, Depends(active_user)],
    conn: Annotated[sqlite3.Connection, Depends(get_db)],
) -> dict[str, Any]:
    row = _task_or_404(conn, task_id)
    if row["owner_id"] not in (None, user["id"]):
        raise HTTPException(403, "That task belongs to someone else")

    conn.execute(
        """UPDATE tasks SET owner_id = NULL, claimed_at = NULL,
                            version = version + 1
            WHERE id = ?""",
        (task_id,),
    )
    return {"task": _single(conn, task_id)}


@router.post("/admin/tasks/{task_id}/force-release")
def force_release(
    task_id: int,
    _admin: Annotated[sqlite3.Row, Depends(require_admin)],
    conn: Annotated[sqlite3.Connection, Depends(get_db)],
) -> dict[str, Any]:
    """An owner who lost their network keeps the task - they may be back in a
    minute, and stealing it would lose their place. This is the deliberate,
    human override for when they are not coming back."""
    _task_or_404(conn, task_id)
    conn.execute(
        """UPDATE tasks SET owner_id = NULL, claimed_at = NULL,
                            version = version + 1
            WHERE id = ?""",
        (task_id,),
    )
    return {"task": _single(conn, task_id)}
```

Also update the list query in `board()` to join `users` and fill `owner` per row, replacing
the hardcoded `None` in `_task_row`.

- [ ] **Step 4: Run the tests to verify they pass**

```bash
cd backend && ./venv/Scripts/python.exe -m pytest tests/test_claim.py -v
```

Expected: 5 passed. If `test_exactly_one_of_two_parallel_claims_wins` is flaky, the fault
is in the implementation, not the test — check that `PRAGMA busy_timeout` is set and that
nothing reads the row before writing it.

- [ ] **Step 5: Commit**

```bash
git add backend/app/routers/board.py backend/tests/test_claim.py
git commit -m "Claim and release, decided in one statement

With a three-second poll, two people genuinely see the same free task and click
at the same moment. Checking then writing leaves a window in which both checks
pass; the condition lives in the WHERE clause so SQLite resolves it. The 409
names the winner so the UI can roll back with something useful to say.

An offline owner keeps their task - they may be back in a minute, and taking it
would lose their place. Force-release is deliberate and human, not a timeout.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 26: Presence — TST-14

**Files:**
- Modify: `backend/app/routers/board.py`
- Create: `backend/tests/test_presence.py`

**Interfaces:**
- Produces: `POST /api/presence {task_id}` · `board()` fills `viewers`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_presence.py`:

```python
"""TST-14 — presence expires."""
from __future__ import annotations

from tests.conftest import auth_headers
from tests.test_claim import _settled_member


def _viewers(client, token, code):
    tasks = client.get("/api/board", headers=auth_headers(token)).json()["tasks"]
    return next(t for t in tasks if t["code"] == code)["viewers"]


def test_a_heartbeat_makes_you_a_viewer(client, admin, seeded_tasks):
    task = seeded_tasks[0]
    lan = _settled_member(client, admin, "lan")

    client.post("/api/presence", json={"task_id": task["id"]},
                headers=auth_headers(lan))

    names = [v["display_name"] for v in _viewers(client, admin["token"], task["code"])]
    assert "Lan" in names


def test_you_are_not_your_own_viewer(client, admin, seeded_tasks):
    task = seeded_tasks[0]

    client.post("/api/presence", json={"task_id": task["id"]},
                headers=auth_headers(admin["token"]))

    names = [v["display_name"] for v in _viewers(client, admin["token"], task["code"])]
    assert "Admin" not in names


def test_presence_expires_after_thirty_seconds(client, admin, seeded_tasks, db):
    task = seeded_tasks[0]
    lan = _settled_member(client, admin, "lan")
    client.post("/api/presence", json={"task_id": task["id"]},
                headers=auth_headers(lan))

    # Reach into the table rather than sleeping: a 30-second unit test is a test
    # nobody runs.
    from app.db.connection import get_conn

    conn = get_conn()
    conn.execute("UPDATE presence SET last_seen_at = '2020-01-01T00:00:00Z'")
    conn.close()

    assert _viewers(client, admin["token"], task["code"]) == []
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd backend && ./venv/Scripts/python.exe -m pytest tests/test_presence.py -v
```

Expected: 404 on `/api/presence`.

- [ ] **Step 3: Add presence to `board.py`**

```python
from datetime import datetime, timedelta, timezone

from pydantic import BaseModel

PRESENCE_TTL_SECONDS = 30


class PresenceRequest(BaseModel):
    task_id: int | None = None


def _presence_cutoff() -> str:
    return (
        datetime.now(timezone.utc) - timedelta(seconds=PRESENCE_TTL_SECONDS)
    ).strftime("%Y-%m-%dT%H:%M:%SZ")


@router.post("/presence")
def heartbeat(
    body: PresenceRequest,
    user: Annotated[sqlite3.Row, Depends(active_user)],
    conn: Annotated[sqlite3.Connection, Depends(get_db)],
) -> dict[str, bool]:
    """Called every 10 seconds; anyone silent for 30 is treated as gone.

    Three missed beats rather than one, because a single dropped request during
    a round should not make a teammate vanish from the screen.
    """
    conn.execute(
        """INSERT INTO presence (user_id, task_id, last_seen_at)
           VALUES (?, ?, ?)
           ON CONFLICT(user_id) DO UPDATE
              SET task_id = excluded.task_id, last_seen_at = excluded.last_seen_at""",
        (user["id"], body.task_id, utcnow_iso()),
    )
    return {"ok": True}


def _viewers_by_task(
    conn: sqlite3.Connection, me: int
) -> dict[int, list[dict[str, Any]]]:
    rows = conn.execute(
        """SELECT p.task_id, u.id, u.display_name
             FROM presence p JOIN users u ON u.id = p.user_id
            WHERE p.last_seen_at >= ? AND p.task_id IS NOT NULL AND u.id != ?""",
        (_presence_cutoff(), me),
    ).fetchall()

    grouped: dict[int, list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(row["task_id"], []).append(
            {"id": row["id"], "display_name": row["display_name"]}
        )
    return grouped
```

Call `_viewers_by_task(conn, user["id"])` once in `board()` and attach the list to each
task. `board()` now needs the calling user, so change its `_user` parameter to `user`.

- [ ] **Step 4: Run the tests to verify they pass**

```bash
cd backend && ./venv/Scripts/python.exe -m pytest tests/test_presence.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/routers/board.py backend/tests/test_presence.py
git commit -m "Presence: who is looking at what

Heartbeat every ten seconds, gone after thirty - three missed beats rather than
one, so a single dropped request does not make a teammate vanish mid-round. You
are never your own viewer; the list answers "who else", which is the only
question it is asked.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 27: Front end — the live board

**Files:**
- Modify: `frontend/src/hooks/useBoard.ts`
- Modify: `frontend/src/pages/Board.tsx`
- Create: `frontend/src/api/presence.ts`
- Create: `frontend/src/hooks/usePresence.ts`

**Interfaces:**
- Produces: `claimTask(id)` · `releaseTask(id)` · `usePresence(taskId)`.

- [ ] **Step 1: Add the 3-second poll**

In `useBoard.ts`, add below the mount effect:

```ts
  useEffect(() => {
    // Three seconds is for watching teammates. Your own actions render
    // immediately and reconcile against the server's reply, so the poll interval
    // is never the latency you feel.
    //
    // Deliberately not a WebSocket: a dead socket keeps showing the last frame
    // it received, so the screen looks correct and is stale. Mid-round, failing
    // silently is worse than being three seconds behind. This hook is the only
    // place board data is fetched, so that swap is one file when it is wanted.
    const timer = window.setInterval(() => void refresh(), 3000);
    return () => window.clearInterval(timer);
  }, [refresh]);
```

- [ ] **Step 2: Add the claim client and optimistic claim**

`frontend/src/api/presence.ts`:

```ts
import { apiFetch } from "./base";
import type { BoardTask } from "../types/collab";

export async function claimTask(id: number): Promise<{ task: BoardTask }> {
  return apiFetch(`/api/tasks/${id}/claim`, { method: "POST" });
}

export async function releaseTask(id: number): Promise<{ task: BoardTask }> {
  return apiFetch(`/api/tasks/${id}/release`, { method: "POST" });
}

export async function heartbeat(taskId: number | null): Promise<{ ok: boolean }> {
  return apiFetch("/api/presence", {
    method: "POST",
    body: JSON.stringify({ task_id: taskId }),
  });
}
```

`frontend/src/hooks/usePresence.ts`:

```ts
import { useEffect } from "react";

import { heartbeat } from "../api/presence";

/** Ten seconds, matching the server's thirty-second expiry. */
export function usePresence(taskId: number | null) {
  useEffect(() => {
    void heartbeat(taskId);
    const timer = window.setInterval(() => void heartbeat(taskId), 10_000);
    return () => window.clearInterval(timer);
  }, [taskId]);
}
```

- [ ] **Step 3: Wire the board**

In `Board.tsx`:

1. Render `owner.display_name` or a `Claim` button per row.
2. `Claim` updates local state **immediately** to show you as owner, then calls
   `claimTask`. On `409`, roll the row back and show
   `` `Task ${code} was just claimed by ${err.body.detail.owner.display_name}` ``.
3. Render `viewers` as initials beside the owner.
4. Show an amber warning on a row whose owner has not been seen recently —
   the server's `viewers` list is the only presence signal available, so treat an
   owner absent from every task's viewers as "may be offline", and offer the admin a
   `Force release` button there.

In `Workspace.tsx`, call `usePresence(taskId)`.

- [ ] **Step 4: Verify with two browsers**

Open the board in two browser profiles logged in as different members. Click `Claim` on the
same task within the same second in both. Exactly one shows itself as owner; the other
shows the toast naming the winner. Open a task in one and confirm the other's board shows
a viewer avatar within three seconds.

- [ ] **Step 5: Commit**

```bash
git add frontend/src
git commit -m "Front end: the live board, with optimistic claiming

Your own click renders instantly and reconciles against the server's reply; the
three-second poll is only ever for watching teammates, so the interval is never
the latency anyone feels. A lost race rolls back and names the winner, because
"something went wrong" is useless when what actually happened is that Lan got
there first.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

# Slice S6 — Frame precision and polish

---

### Task 28: Frame arithmetic — TST-15, TST-16

**Files:**
- Create: `frontend/src/helpers/frameMath.ts`, `frameMath.test.ts`
- Create: `frontend/src/helpers/frameTimestamp.ts`, `frameTimestamp.test.ts`

**Interfaces:**
- Produces:
  - `frameAtTime(t: number, fps: number, offset: number): number`
  - `timeForFrame(frame: number, fps: number, offset: number): number`
  - `fitCalibration(a: Landmark, b: Landmark): { fps: number; offset: number }` where
    `Landmark = { frame: number; observedTime: number }`
  - `driftFrames(frame: number, nominal: Calibration, fitted: Calibration): number`
  - `CalibrationError`

- [ ] **Step 1: Port the module and its tests**

```bash
git show dev:frontend/src/helpers/frameMath.ts           > frontend/src/helpers/frameMath.ts
git show dev:frontend/src/helpers/frameMath.test.ts      > frontend/src/helpers/frameMath.test.ts
git show dev:frontend/src/helpers/frameTimestamp.ts      > frontend/src/helpers/frameTimestamp.ts
git show dev:frontend/src/helpers/frameTimestamp.test.ts > frontend/src/helpers/frameTimestamp.test.ts
```

- [ ] **Step 2: Run the ported tests**

```bash
cd frontend && npm run test
```

Expected: green. If any fail, the port is incomplete — do not weaken a test to make it
pass; these encode INV-2.

- [ ] **Step 3: Add the two guard tests if the port lacks them**

Append to `frontend/src/helpers/frameMath.test.ts`:

```ts
describe("calibration guards", () => {
  it("refuses landmarks less than ten seconds apart", () => {
    // A one-frame sighting error over a short baseline swings the fitted fps
    // further than the drift it is meant to correct.
    expect(() =>
      fitCalibration(
        { frame: 100, observedTime: 4.0 },
        { frame: 200, observedTime: 8.0 }
      )
    ).toThrow(CalibrationError);
  });

  it("refuses a fit more than twenty percent from nominal", () => {
    expect(() =>
      fitCalibration(
        { frame: 0, observedTime: 0 },
        { frame: 100, observedTime: 60 },
        { nominalFps: 25 }
      )
    ).toThrow(CalibrationError);
  });

  it("round-trips at every fps in the data set", () => {
    for (const fps of [24, 25, 29.97, 30, 59.94]) {
      for (const frame of [0, 1, 25605, 999999]) {
        expect(frameAtTime(timeForFrame(frame, fps, 0), fps, 0)).toBe(frame);
      }
    }
  });
});
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
cd frontend && npm run test
```

Expected: green. The round-trip test is the one that matters: `timeForFrame` aims at the
frame **midpoint**, `(f + 0.5 − offset) / fps`, so a seek rounded either way still lands on
the frame that was asked for.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/helpers
git commit -m "Frame arithmetic and per-video calibration

frame(t) = floor(fps*t + offset), and seeks aim at the frame midpoint so a seek
rounded either direction still lands on the frame that was asked for. Round-trip
is asserted at 24, 25, 29.97, 30 and 59.94.

Calibration fits fps and offset through two keyframes a human confirms in the
player, which turns the open question about the fps table from something only
the organizer can answer into something measurable per video in about thirty
seconds. Both guards are kept: landmarks closer than ten seconds are refused
because a one-frame sighting error would swing the fit further than the drift it
corrects, and a fit more than twenty percent off nominal means a landmark was
misidentified and accepting it would poison every answer for that video.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 29: The pin-frame panel

**Files:**
- Create: `frontend/src/components/workspace/PinFrame.tsx`
- Modify: `frontend/src/pages/Workspace.tsx`

**Interfaces:**
- Consumes: `frameAtTime`, `timeForFrame`, `fitCalibration`, `driftFrames`, `frameOf`.
- Produces: the `pin` branch of the workspace's middle column, replacing the placeholder
  left by Task 21, Step 3, requirement 5.

- [ ] **Step 1: Build the panel**

Required behaviour, all of it from spec §9.2 and FR-7:

1. State is **one integer** `frameIdx`, plus the video's `fps` and `offset`.
2. A transport row: `−10 · −1 · [ 25605 ] · +1 · +10`. The number field is a text input;
   typing any integer is accepted and nothing snaps.
3. Beneath it, on one line: the timecode from `timeForFrame`, the `fps` in use, the
   `offset` in use, and whether the position has been confirmed against a keyframe
   thumbnail. **A number produced under a corrected fps must never look identical to one
   produced under the nominal table.**
4. A keyframe strip: the neighbouring keyframes of this video as thumbnails, each labelled
   with its exact index. Clicking one seeks to `timeForFrame(F)` — it sets position, never
   the submitted value.
5. `Calibrate` collects two landmarks (a keyframe the user confirms near the start and one
   near the end), calls `fitCalibration`, and displays `driftFrames` — how far the
   correction moved the answer — so a correction is never invisible.
6. `Add to basket` calls `add({ video_id, frames: [frameIdx] })` for KIS/Q&A, or writes the
   frame into the currently selected moment slot for TRAKE.

- [ ] **Step 2: Replace the placeholder in `Workspace.tsx`**

```tsx
{mode === "grid"
  ? <ResultGrid … />
  : <PinFrame
      videoId={selected.video ?? ""}
      initialFrame={frameOf(selected) ?? 0}
      task={task}
      onAdd={add}
      onBack={() => setMode("grid")}
    />}
```

- [ ] **Step 3: Verify by hand**

Select a tile, press `Enter`, step `+1` ten times, and confirm the frame number rises by
exactly ten and the timecode by exactly `10 / fps` seconds. Type `25605` directly and
confirm it is accepted unchanged.

- [ ] **Step 4: Commit**

```bash
git add frontend/src
git commit -m "Pin frame: one integer, and every term of it on screen

TRAKE windows are usually under ten frames - under 0.4 seconds at 25fps - so no
slider reaches them and stepping has to be integer arithmetic. The keyframe strip
is coarse navigation only: clicking a landmark sets position, never the submitted
value, because keyframes sit about 3.5 seconds apart and submitting the nearest
one is a confident answer that scores zero.

fps and offset are displayed beside the frame number because they are the terms
that produced it. A number computed under a corrected fps must not look identical
to one computed under the nominal table.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 30: Keyboard, dead weight, and the final sweep

**Files:**
- Create: `frontend/src/hooks/useWorkspaceKeys.ts`
- Modify: `frontend/src/pages/Workspace.tsx`
- Modify: `frontend/src/components/QueryInput/index.tsx`
- Modify: `frontend/package.json`
- Delete: `drive-video-proxy/` from the main flow
- Modify: `README.md`

- [ ] **Step 1: Add the keyboard map**

`frontend/src/hooks/useWorkspaceKeys.ts` binding spec §9.3: `←/→` select or step one frame,
`Shift+←/→` step ten, `Enter` open pin frame, `Esc` back to grid, `1` promote the selection
to rank 1, `A` append to basket, `X` discard, `/` focus the search box. Every handler
returns early when `document.activeElement` is an input or textarea, so typing a Vietnamese
query never triggers a shortcut.

- [ ] **Step 2: Delete the dead controls**

In `QueryInput/index.tsx`, remove `Rank`, `Unique Keywords`, `Filter` and the standalone
`Translate` panel — they were parameters of six endpoints deleted in `d09cf9b` and send
nothing anywhere. Keep the mode selector, `Top-M`, the rerank toggle, and the query box.
Change `Show Top` to read `board.rows_per_query` rather than a hardcoded list ending at
100.

- [ ] **Step 3: Remove the remaining dead weight**

```bash
cd frontend && npm uninstall gapi-script firebase react-csv @types/react-csv
```

In `README.md`, mark `drive-video-proxy/` as retired and not part of the running system,
and document the new startup: bootstrap an admin, run the API, run the front end, import
the pack.

- [ ] **Step 4: Full verification**

```bash
cd backend && ./venv/Scripts/python.exe -m pytest -v
cd ../frontend && npm run test && npm run lint && npm run build
```

Expected: **everything green, including the slow marker.** TST-1 passing here is the proof
that thirty tasks of collaboration layer landed without moving retrieval by one distance
value.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "Keyboard control, dead controls removed, dependencies pruned

Rank, Unique Keywords, Filter and the Translate panel are gone: they were
parameters of six endpoints deleted months ago and had been sending nothing
anywhere since. A control that does nothing is worse than a missing one, because
someone under time pressure will believe it worked.

Show Top now reads export.rows_per_query instead of a hardcoded list, so the
number on screen and the number in the exported file cannot disagree.

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

## Plan self-review

Checked after writing, against the spec.

**Spec coverage.** Every numbered requirement maps to a task:

| Spec | Tasks |
| --- | --- |
| INV-1 … INV-6 | 2 (INV-1), 19+28 (INV-2), 16+18 (INV-3), 13+21 (INV-4), 16+25 (INV-5), 3 (INV-6) |
| FR-1.1 … 1.6 | 7, 8, 9, 10, 11 |
| FR-2.1 … 2.7 | 12, 13, 14 |
| FR-3.1 … 3.5 | 15, 19, 21 |
| FR-4.1 … 4.9 | 16, 17, 20 |
| FR-5.1 … 5.5 | 25, 26, 27 |
| FR-6.1 … 6.6 | 22, 23, 24 |
| FR-7.1 … 7.4 | 28, 29 |
| §5.2 import format | 12 |
| §5.3 export format | 22 |
| §7 API contract | 7, 8, 9, 13, 15, 17, 23, 25, 26 |
| §8 data model + two additions | 6 |
| §9 UI | 14, 19, 20, 21, 24, 27, 29, 30 |
| TST-1 … TST-16 | 2, 7, 12, 15, 16, 17, 22, 23, 25, 26, 28 |

**Gaps found and closed while reviewing:**

1. `GET /api/board` was needed in S2 for the import test and in S3 for task selection, but
   the spec placed the board in S5. Task 13 now adds the read half with `owner: null` and
   `viewers: []`; Tasks 25 and 26 fill them in **without changing the response shape**, so
   no client code moves.
2. Re-import created a second pack, so `UNIQUE (pack_id, code)` did not prevent duplicate
   tasks on the board. Task 13 deactivates previous packs.
3. `dev`'s `conftest.py` sets `AIC_DEMO=1`; that variable means nothing here and would
   mislead. Task 5 removes it.
4. `dev`'s `schema.sql` is `IF NOT EXISTS` throughout, so the stale `app.db` on this
   machine would never receive `phase` or `import_warnings`. Task 6 deletes it.
5. The spec's §7.3 preview contract carried `query_source`; §5.2 dropped it. Task 13's
   endpoint omits it, matching the spec's own §5.2 note.

**Known deliberate placeholder.** Task 21, Step 3, requirement 5 leaves the `pin` branch as a
one-line stand-in, and Task 29 replaces it. It is called out in both places.

**Type consistency.** `frameOf`, `agreementOf`, `boundaryAfter`, `originStripe`,
`dotClass`, `screenFor` are each defined once and referenced by their defining name.
`AnswerRow`, `BoardTask`, `PackPreviewFile` are declared in Tasks 18, 14 and 14
respectively and used consistently thereafter. `answers_store.patch_answer` returns
`dict | None` in Task 16 and Task 17 treats `None` as the 409 path.

---

## Execution handoff

**Plan complete and saved to `docs/superpowers/plans/2026-08-16-staging-collab-import-export.md`.**

Order is strict: **Task 2 before any port.** A snapshot recorded after the first port is a
snapshot of possibly-broken behaviour, and the guard would then certify the bug.

If the clock runs out, stop after **Task 24**. That is the competition-ready line: the
system imports the organizer's pack, searches into a task, holds 100 ranked answers per
query, and exports a correct submission zip. Tasks 25–30 make it faster and more precise;
they do not make it more capable.
