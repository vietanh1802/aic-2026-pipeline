# Scavenger — Video Query Finder (AIC 2025)

A text-to-video **keyframe retrieval** system built for the **AI Challenge (AIC) 2025**.
You describe a scene in natural language and the system finds the matching moments
across a large video archive, then lets you jump straight to that point in the
original video.

The project is a monorepo with three independent parts:

| Component            | Stack                              | Port  | Role                                                            |
| -------------------- | ---------------------------------- | ----- | -------------------------------------------------------------- |
| `backend/`           | Python · FastAPI · FAISS · PyTorch | 8000  | Search API over pre-extracted keyframes and embeddings.        |
| `frontend/`          | React · TypeScript · Vite · Tailwind | 5173  | Web UI: query, browse results, preview the clip.               |
| `drive-video-proxy/` | Node.js · Express                  | 5000  | Streams the source videos from Google Drive (with HTTP Range). |

---

## How it works

1. **Keyframes** are extracted from the video archive ahead of time. For each frame the
   pipeline stores its text/visual embedding plus metadata (OCR text, detected objects,
   colors, actions) in a keyframe database.
2. The **frontend** sends a query to the **backend**, which offers several search modes
   (see [Search modes](#search-modes)).
3. Results come back as ranked keyframes with a similarity score and an image URL.
4. Clicking a result opens a **video popup**; the frontend asks the **drive-video-proxy**
   to stream the correct video from Google Drive and seeks to the frame's timestamp.

### Search modes

All are exposed by the backend and selectable from the query bar in the UI.

| Endpoint                  | Mode              | Description                                                                    |
| ------------------------- | ----------------- | ------------------------------------------------------------------------------ |
| `POST /text-search`       | Text + agent      | An LLM (GitHub Models, `gpt-4.1`) expands the query into synonyms / keywords from a classified vocabulary before matching against keyframe metadata. |
| `POST /text-no-agent-search` | Text (plain)   | Keyword matching without the LLM expansion step.                               |
| `POST /faiss-search`      | Semantic (FAISS)  | Encodes the query with `all-mpnet-base-v2` and does nearest-neighbor search over the FAISS embedding index. |
| `POST /ocr-search`        | OCR               | Matches against text detected inside the frames.                               |
| `POST /combined-search`   | Combined          | Mixes text and OCR signals.                                                    |
| `POST /filter-search`     | Filter            | Filters by `object` / `color` / `action` / `ocr` tags.                         |
| `GET /status`, `GET /`    | Health            | Service status and endpoint listing.                                           |

Interactive API docs are available at `http://localhost:8000/docs` once the backend runs.

---

## Repository layout

```
AIC-pipeline-2025/
├── backend/
│   ├── app/
│   │   ├── main.py            # FastAPI app + search endpoints
│   │   ├── models.py          # Pydantic request/response models
│   │   ├── preprocess.py      # FAISS semantic search (all-mpnet-base-v2)
│   │   ├── agent.py           # LLM keyword expansion (GitHub Models)
│   │   ├── data/              # Data & model artifacts (NOT in git — see below)
│   │   │   ├── temp.json              # keyframe database
│   │   │   ├── classified_vocab.json
│   │   │   ├── decode_files/          # id→path / name→URL maps
│   │   │   └── faiss/                 # FAISS indexes (data.index, image.index)
│   │   └── static/images/     # keyframe images (NOT in git — served at /static/images)
│   ├── requirements.txt
│   ├── .env.example
│   └── .gitignore
├── frontend/
│   ├── src/
│   │   ├── components/        # UI components (query bar, results, video popup, …)
│   │   ├── store/            # Zustand state stores
│   │   ├── helpers/          # formatting / mapping helpers
│   │   ├── mapping/          # frame ↔ video ↔ fps ↔ Drive-file-id maps
│   │   ├── types/            # API client and shared types
│   │   ├── Animations/       # ReactBits UI animation components
│   │   └── TextAnimations/
│   ├── .env.example
│   └── package.json
└── drive-video-proxy/
    ├── server.js
    ├── .env.example
    └── package.json          # service-account key stays local, never committed
```

### Data & model artifacts (provided out of band)

The keyframe database, FAISS indexes, id-maps and the ~294k keyframe images are **too
large for git** (the FAISS index alone is ~900 MB) and are therefore **git-ignored**.
Before running the backend, obtain these files and place them exactly as documented in
[`backend/app/data/README.md`](backend/app/data/README.md), and put the keyframe images
under `backend/app/static/images/`.

---

## Prerequisites

- **Python** 3.10+
- **Node.js** 18+ (Express 5 and the Vite toolchain expect a modern runtime)
- A **GitHub token** with access to GitHub Models (for the agent-based text search)
- A **Google Cloud service account** key with read access to the Drive videos (for the proxy)

---

## Setup & run

Run each component in its own terminal.

### 1. Backend (API — port 8000)

```bash
cd backend
python -m venv venv
venv\Scripts\activate            # Windows;  source venv/bin/activate on macOS/Linux
pip install -r requirements.txt

cp .env.example .env             # then edit .env and set GITHUB_TOKEN
# ensure app/data/* and app/static/images/* are in place (see note above)

uvicorn app.main:app --reload
```

Backend env vars (`backend/.env`):

| Variable                 | Required | Default                                | Purpose                             |
| ------------------------ | -------- | -------------------------------------- | ----------------------------------- |
| `GITHUB_TOKEN`           | yes      | —                                      | Auth for GitHub Models (`gpt-4.1`). |
| `GITHUB_MODELS_ENDPOINT` | no       | `https://models.github.ai/inference`   | Models API endpoint.                |
| `GITHUB_MODELS_MODEL`    | no       | `gpt-4.1`                              | Model used for keyword expansion.   |

> The first request loads the `all-mpnet-base-v2` model and the FAISS index into memory,
> so it can take a while to warm up.

### 2. Drive video proxy (port 5000)

```bash
cd drive-video-proxy
npm install
# place the Google service account key here as service-account2.json
#   (or set GOOGLE_APPLICATION_CREDENTIALS to its path)
node server.js
```

Proxy env vars (`drive-video-proxy/.env`, optional):

| Variable                         | Default                   | Purpose                             |
| -------------------------------- | ------------------------- | ----------------------------------- |
| `PORT`                           | `5000`                    | Port to listen on.                  |
| `GOOGLE_APPLICATION_CREDENTIALS` | `./service-account2.json` | Path to the Drive service-account key. |

### 3. Frontend (UI — port 5173)

```bash
cd frontend
npm install
cp .env.example .env             # optional; adjust if you use env vars
npm run dev
```

Then open the URL Vite prints (default `http://localhost:5173`). The backend CORS config
already allows this origin, and the video popup expects the proxy at
`http://localhost:5000`.

---

## Security notes

- **Never commit secrets.** `.env` files and `service-account*.json` are git-ignored.
  Use the `.env.example` templates as a starting point.
- If a token or key was ever committed in the past, treat it as compromised and
  **rotate it** — removing it from the working tree does not remove it from old history.
- The Firebase web config in `frontend/src/firebase.js` uses a public client `apiKey`
  (this is expected for Firebase); protect data with Firebase Security Rules instead.

---

## License

See [LICENSE](LICENSE).
