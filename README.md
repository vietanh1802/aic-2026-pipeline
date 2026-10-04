# Bquerium — Interactive Video Moment Retrieval

Bquerium is an interactive system for finding specific moments in a large video
collection from a natural-language description (Vietnamese or English). It was
built for the **Ho Chi Minh City AI Challenge 2026** and supports the three task
types of the challenge:

| Task | Input | Output |
| --- | --- | --- |
| **KIS** (Known-Item Search) | a description of one moment | `video, frame` |
| **Q&A** | a description + a question | `video, frame, answer` |
| **TRAKE** | a sequence of *N* events | `video, frame_1, …, frame_N` in temporal order |

The machine proposes candidates; people pick the final answer. Several team
members work on the same system at the same time, sharing queries, candidate
lists and answers.

Dataset scale handled by the deployed system: **1,480 videos, 983,931 keyframes**
(news, traffic cameras, cycling races).

---

## System overview

```
            OFFLINE (Colab notebooks)                          ONLINE
 ┌────────────────────────────────────────────┐   ┌──────────────────────────────────┐
 │ video ─ TransNetV2 shots ─ keyframe sampling│   │  React frontend                  │
 │           │                                 │   │   query · browse · verify in     │
 │           ├─ BEiT-3 / CLIP ViT-bigG /       │   │   video · rank answers · submit  │
 │           │  SigLIP2 image embeddings       │   │            ▲  REST               │
 │           ├─ OCR (Vintern-1B-v3.5)          │──▶│  FastAPI backend                 │
 │           └─ ASR (NVIDIA Parakeet)          │   │   search · collaboration ·       │
 │                                             │   │   evaluation   (SQLite)          │
 │ ⇒ 3 FAISS indexes · OCR/ASR text · metadata │   │   indexes loaded in RAM, CPU only│
 └────────────────────────────────────────────┘   └──────────────────────────────────┘
```

### Offline indexing

1. **Shot detection** with TransNetV2.
2. **Keyframe sampling** proportional to shot length: 2 frames for shots up to
   1.67 s, then one more frame per extra 2 s, clamped to [2, 40].
   Keyframes are named `L26_V041-0047-3798.jpg` (`video-shot-frame`); this name is
   the join key between images, OCR, ASR and metadata. Frame indices follow the
   official fps table of the dataset, not `ffprobe`.
3. **Image embeddings** from three vision–language encoders, each in its own
   exact-search FAISS index (`IndexFlatIP`, cosine on L2-normalised vectors):
   BEiT-3 Large (1024-d), OpenCLIP ViT-bigG-14 (1280-d), SigLIP2-giant (1536-d).
4. **OCR** of on-screen text with Vintern-1B-v3.5 (Vietnamese VLM).
5. **ASR** with NVIDIA Parakeet, split into overlapping 60 s windows.

### Retrieval methods

**Query processing.** Text encoders read only 64–77 tokens, while descriptions are
often 100–150 words. An LLM translates the query to English and compresses it,
keeping visible details (objects, colours, actions, on-screen text).

**Semantic search.** For each encoder *m*: retrieve the top-*M* keyframes, then
re-score each frame *f* by its temporal neighbourhood, since a moment usually
spans several consecutive keyframes:

$$ s'_m(f) = \sum_{g \in \mathcal{N}(f)} \langle \mathbf{q}_m, \mathbf{v}_m(g) \rangle $$

Scores of different encoders live on different scales, so each is normalised by
its maximum before a weighted sum (equal weights by default):

$$ S(f) = \sum_m w_m \frac{s'_m(f)}{\max_g s'_m(g)}, \qquad \sum_m w_m = 1 $$

Re-ranking is done **per model, before** the ensemble, so each neighbourhood
score is computed with that model's own embeddings.

**TRAKE (event sequences).** Given events *e₁ … e_N*, choose frames
*f₁ < … < f_N* in one video that maximise Σ sim(eᵢ, fᵢ) subject to
*f₍ᵢ₊₁₎ − fᵢ ≤ Δ* (60 s). Solved by dynamic programming in O(N·F²). When the
video is unknown, videos are ranked by how many events have a matching frame and
the DP runs on the top candidates.

**Temporal pairs.** From an anchor frame, search left for the "before"
description and right for the "after" description, within 20 s.

**Text signals (OCR / ASR).** Accent-insensitive substring matching over OCR text
(several phrases at once); substring, regex or BM25 over ASR windows. Text hits
**annotate** the visual results ("matched here" / "matched elsewhere in this
video", with the snippet) instead of re-ranking them — the user decides.

---

## Repository layout

```
backend/            FastAPI service: search, collaboration, evaluation
  app/main.py         search endpoints (ensemble, single, temporal, TRAKE, OCR)
  app/preprocess.py   retrieval core: encoders, FAISS, re-rank, ensemble, temporal
  app/routers/        auth, board, answers, packs, rounds, search state, export, DRES, evaluation
  app/db/             SQLite schema + numbered migrations
  app/evaluation/     benchmark runner and scoring (Hit@k, MRR, R@k)
  tests/              pytest
frontend/           React 19 + TypeScript + Vite + Tailwind + Zustand
notebooks/          offline pipeline (keyframes, embeddings, OCR, ASR) — run on Colab
scripts/            helper scripts (frontend mappings, ASR text index, zip sync)
data_raw/           small reference data (official fps table)
deploy/             Caddy config and SSM deploy scripts for EC2
docs/               design notes and specs (docs/superpowers/specs/ is authoritative)
Dockerfile, docker-compose*.yml   container build for the backend + Caddy
VERSION             semver; CI refuses a push that does not bump it
```

Large artifacts (indexes, keyframes, model weights) are **not** in git; see
[Artifacts](#artifacts).

---

## Getting started

Requirements: Python 3.11, Node.js 20+, and the index artifacts below.

### Backend (port 8000)

```bash
cd backend
pip install -r requirements.txt
python -m scripts.seed_team          # create team accounts (idempotent)
uvicorn app.main:app --reload
```

Tests and lint:

```bash
cd backend
mkdir -p .tmp                                # pytest does not create the parent of --basetemp
python -m pytest -q --basetemp=.tmp/pytest   # --basetemp avoids Windows temp-dir permission errors
python -m ruff check app
```

### Frontend (port 5173)

```bash
cd frontend
npm install
npm run dev
```

Checks: `npx tsc -b && npm run lint && npm test && npm run build`.

### Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `AIC_INDEX_DIR` | `backend/app/indexes` | FAISS indexes, mappings, metadata, model weights |
| `AIC_IMAGE_BASE_URL` | local `/static` | where keyframe images are served from |
| `AIC_MODELS` | all | comma list of `beit3,clip,siglip2` to load |
| `AIC_DB_PATH` | `backend/app/data/app.db` | SQLite database |
| `AIC_WARMUP` | `1` | `0` skips loading indexes/models at startup |
| `AIC_CORS_ORIGINS` | any | comma list of allowed origins |
| `VITE_API_BASE_URL` | — | backend URL used by the frontend |
| `VITE_IMAGE_BASE_URL` | `${VITE_API_BASE_URL}/static` | keyframe image host for the frontend |

Copy `frontend/.env.example` to `frontend/.env` to start.

---

## Artifacts

The backend expects in `AIC_INDEX_DIR`:

```
beit3.index, clip.index, siglip2_giant.index   FAISS IndexFlatIP
*_mapping.json                                 {"0": ".../static/images/<name>.jpg", ...}
keyframe_metadata.json                         a LIST of per-keyframe records (not a dict)
beit3_large_patch16_384_coco_retrieval.pth, beit3.spm, CLIP / SigLIP2 weights
ocr_clean.json, ocr_clean_nodau.json           OCR text (with / without diacritics)
```

They are produced by the notebooks in `notebooks/` on Colab and synced to the
server from S3 (`deploy/p6/ssm-sync-indexes.sh`, `docs/updating-indexes.md`).

---

## Evaluation

`backend/app/evaluation/` replays a benchmark of queries with known answers
(`seeds/round{1,2,3}-*.json`) against the live search and scores it:

- video level: Hit@1, Recall@{3,5,10}, MRR
- frame-interval level (official scoring): R@{1,5,20,50,100}

Runs are started and inspected from the **Evaluation** page of the frontend.
Repeated runs of the same configuration can differ by up to ~0.05 MRR, so compare
averages over several runs.

---

## Deployment

Pushing to `staging` runs `.github/workflows/deploy.yml`: version guard →
frontend checks (lint, tsc, tests, build) and backend checks (ruff, import,
pytest) → frontend to Cloudflare Pages, backend image to GHCR and to EC2 via SSM →
smoke test with automatic rollback. The server is CPU-only (8 vCPU, 64 GiB);
all query-time encoding and FAISS search run on CPU.

---

## License

MIT — see [LICENSE](LICENSE).
