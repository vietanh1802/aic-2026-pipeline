# Ablation benchmark: design (Phase 2)

Status: DESIGN ONLY. Nothing here is implemented. Branch `feature/ablation-benchmark`, cut from `origin/staging` at `e9a7e61`.
Tags: CONFIRMED = read in code or run; INFERRED = reasoned, not run. Paths are relative to the repo root, line numbers refer to `e9a7e61`.
Policy carried over: the shipped system is evaluated as-is. No setting is tuned on final-day queries.

---

## 0. Phase 1 findings the design rests on

### 0.1 The production default configuration (CONFIRMED)

What the UI sends for a normal search (`frontend/src/App.tsx:550-562`, `types/api.ts` `ensembleSearch`, `store/queryStore.ts:94-127`):

| Field | UI default | Notes |
|---|---|---|
| route | `POST /ensemble-search` | |
| `query` | the text in the search box, verbatim | no automatic translation or expansion |
| `limit` (top_k) | 100 | `resultLimit: "100"` |
| `top_m` | 50 | `topM: 50` |
| `use_rerank` | true | |
| `models` | `["beit3","clip","siglip2"]` | sent whenever non-empty |
| `video_groups` | omitted | only `["N"]` when "traffic only" is ticked |
| `asr_filter`, `ocr_filter` (+ modes) | omitted | sent only when a filter box has text |
| TRAKE route | `POST /trake-search-text`, `top_m` 50, `top_videos` 20 (App.tsx:495), `gap_c` 60, `min_score` 0.1, `model` "clip" | `types/api.ts` `trakeSearchText` |

Text preparation is a human action, not a pipeline step:
- Translate button (`QueryInput/index.tsx:167-185`): the BROWSER calls `translate.googleapis.com/translate_a/single?client=gtx&sl=auto&tl=en&dt=t`, overwrites the box. No timeout, no retry, silent on failure.
- Expand button (`QueryInput/index.tsx:198-215` sends task type "KIS" always; `TaskBrief/index.tsx:58` sends the real task type): `POST /api/expansion` then `expansion.expand_query`.

Differences between production and `backend/app/evaluation/ensemble.py` (CONFIRMED):

| | production | evaluation today |
|---|---|---|
| models | all three | `["beit3","clip"]` (`ensemble.py:31`) |
| query text | as typed (raw, gtx or Expand) | Gemini policy `literal_v1` per run, re-translated every run |
| TRAKE queries | `trake_search_candidates` (per-event) | plain `ensemble_search` over the whole text |
| annotation | `annotate_request` after search if a filter is set | none |
| `top_k`, `top_m`, rerank | 100, 50, true | same |
| search function | `preprocess.ensemble_search` | same function, fixed args |

### 0.2 Text policies (CONFIRMED, `backend/app/translation.py`, `backend/app/expansion.py`)

| id | provider / model | returns | key needed |
|---|---|---|---|
| `literal_v1` (evaluation default), `visual_faithful`, `scene_clauses`, `retrieval_compact`, `salience_first`, `literal_visual_v2` | Gemini `gemini-3.5-flash-lite`, temperature 0.0 | one string | yes (`translation.py:381`) |
| `google_gtx_v1` | Google gtx, same params as the browser button (`translation.py` `_translate_google_gtx`), server-side with a browser User-Agent | one string | no |
| Expand (`expansion.expand_query`) | Gemini one call, temperature 0.0, fallback Ollama only if `AIC_OLLAMA_URL` is set (empty on EC2) | `{eng_query, check_units[], translated_query, provider, elapsed_ms}` | yes |

Shared mechanics: network retry 3 tries (2 s, 5 s backoff), HTTP 429 one retry, per-provider pacing floor 4.5 s (`translation.py:41`), Expand timeout 30 s, translation timeout 15 s. Expand has an in-memory cache of 512 entries keyed `(query_text, task_type)`. `check_units` are verifier phrases, never used for ranking; evaluation will record them.

### 0.3 Encoders, fusion, rerank (CONFIRMED, `preprocess.py` at `e9a7e61`)

- Each model searches only its own index and maps ids through its own mapping (`_search_one`, L751). A frame missing from a model's index can never be a hit for that model. SigLIP2 ids are looked up by file name (`_fid_of`, L597); a frame it did not index returns -1 and is skipped, including as a rerank neighbour.
- `rerank_one_model` (L844) uses only that model's hits, index and the shared metadata. `_merge_ensemble` (L904): `active` = models with at least one hit; weights 0.5 each, renormalised over `active`; per model `s_max = max(score)` (1.0 if <= 0); contribution `score / s_max * w`; ties broken by insertion order = model order in the `models` list. `ensemble_search` (L951) is a loop over models followed by that merge.
- Therefore retrieval and rerank of one model do NOT depend on which other models are active. Only the final merge does, and it is a pure function of the per-model lists. Arm sharing is valid (section C).
- `use_rerank=False`: the hit list keeps cosine `score`, then the same merge runs.
- Neighbours: `neighbors_clip` (adjacent keyframes of the same video, offsets +-1..3, self excluded) when present; else +-2 keyframes INCLUDING the frame itself (L832-841). On the local Batch 1 metadata `neighbors_clip` is empty for 263,895 of 360,531 frames (251 of 873 videos have it). Batch 2 metadata is likely empty too (INFERRED). The rerank ablation therefore mixes two neighbour definitions across videos; reports must slice by video prefix.
- Fusion and rerank code is byte-identical between the earlier branch and staging apart from SigLIP2 id plumbing (CONFIRMED by AST comparison).

### 0.4 TRAKE (CONFIRMED)

- `trake_search_text` splits the single input on `\.\s+` (L1343), needs >= 2 parts; `trake_search_candidates` (L1389): for each event a full `ensemble_search(q, top_k=top_m, use_rerank=True)` over ALL active models, rank videos by (number of events in which they appear, summed distance), keep `top_videos`; then ONE local encoder (`model_name`, default "clip") scores every frame of each shortlisted video; greedy sequential pick with a hard gap `gap_c` seconds; videos with no feasible chain are dropped; result sorted by `combined_score`. Anchored DP exists only in `/trake-search` and needs a known anchor frame; the UI never calls it.
- Production gives TRAKE-N no help from Expand: Expand returns ONE sentence, which the splitter cannot split. The operator types events separated by ". ". So "per-event translation path" does not exist in production; section B defines an event-wise one and labels it as such.
- 9 of the 31 seed events contain an internal ". " the production splitter would cut (`round3-v2 p3-21 E3`, all four events of `f1-trake-01` and `f2-trake-04`). Evaluation passes the event list directly to `trake_search_candidates`, which is the same function but not the same splitting.
- The 8 TRAKE queries (1 + 2 + 2 + 3) have 3, 4, 4, 4, 4, 4, 4, 4 events = 31 events. EVERY event has a single team reference frame (`reference_frame_idx`); NONE has a valid interval (`valid_start_frame` and `valid_end_frame` are null). Scores: video rank always; per-event correctness as `|frame_idx - ref| <= tolerance` (default 5 s, the same radius as final-v1 KIS), which needs no new labels.

### 0.5 Text signal (CONFIRMED, `text_signal.py`)

- `/ensemble-search` runs `annotate_request` after retrieval inside its own try/except. It annotates the videos present in the returned rows only, searching each video's full frame list. It never removes or reorders a frame (module docstring; `annotate_request` signature). Sources: OCR substring (exact, then diacritic-folded; word scatter; multi-term OR up to 5), ASR substring (frame text = ASR window text +-5 s), ASR BM25 (60 s windows, vocabulary keeps diacritics), regex.
- Stage D (injection) is absent: no `inject` symbol in `backend/`. "Declutter" is absent: no match for `declutter` in `backend/`, `frontend/src/`, `docs/`.
- So an OCR/ASR run can change NO ranking metric today. It can change annotation-level measures only.
- `annotate_request` can be called in-process on stored `frame_results` (rows need `video` and `name`). No search is repeated.

### 0.6 Seeds, labels, data coverage (CONFIRMED by `scratchpad/audit_seeds.py`, using paper_rerun coverage CSVs dated 29 Sep for Batch 2)

| Seed | n | KIS/QA/TRAKE | reference groups | confidence field | filter_terms |
|---|---|---|---|---|---|
| round1-v3 | 24 | 19/4/1 | L24 | 23 manual_review_interval, 1 manual_submission (the TRAKE) | 24 |
| round2-v2 | 29 | 19/8/2 | L29 | 27 + 2 manual_submission (both TRAKE) | 29 |
| round3-v2 | 33 | 25/6/2 | L33 | 33 manual_review_interval | 33 |
| final-v1 | 28 | 14/11/3 | L11 M13 S2 N2 | 28 team_appeal_answer | 0 |

- `reference.confidence` is stored in `evaluation_references.confidence` but NOT copied to result rows and not shown in the UI. The seeds do not mark which 7 final queries have remark requests: all 28 notes say the answer comes from the appeal document.
- Degenerate interval: `f2-qa-03` interval is the whole video (566 frames). `f2-qa-14` frame/ms ambiguity is noted in the seed. N videos have variable frame rate (known limitation), so their interval-level results are unreliable; video level is unaffected.
- `filter_terms` for rounds 1 to 3 were audited against the real OCR/ASR engines (commit `6c90853`) and the extraction prompt `filter_extraction.py:_FILTER_SYSTEM` contains examples taken from round-2 queries (sau rieng, dau bon bon, mang cut), so they are leakage-prone: upper bound only.
- Text-signal coverage of the reference video:

| Dataset | OCR + ASR complete | OCR ok, ASR partial | OCR none, ASR ok | none |
|---|---|---|---|---|
| rounds 1 to 3 (86, all L) | 86 | 0 | 0 | 0 |
| final-v1 (28) | 17 (11 L + 6 M) | 5 (M) | 2 (M05_V018, M06_V008: no OCR delivered) | 4 (2 N, 2 S) |

  M OCR is one frame per shot (about 29% of keyframes), so "OCR ok" for M means some frames, not the interval. Coverage must be measured per run from the loaded artifacts, not from this table (EC2 index set `indexes_LMNS_v002` may be newer than 29 Sep).
- The dataset dropdown lists every seeded dataset row (`repository.list_datasets`, no filtering); superseded versions appear if the EC2 DB was seeded earlier (INFERRED, command in section H).

### 0.7 Runner and capacity (CONFIRMED code, INFERRED numbers)

- One daemon thread inside the API process (`runner.py:324-343`), one in-memory queue, one run at a time; `POST /runs` returns 409 while any run is queued, running or cancelling. Startup marks unfinished runs `interrupted`; nothing resumes automatically.
- EC2 is `r6i.2xlarge`, 8 vCPU, 64 GiB, NO GPU (`CLAUDE.md`, "Deploy"). Text encoding and FAISS flat scans are CPU work in the same process as live search.
- Per (query, model) cost estimate: encode 0.5 to 1.5 s plus flat scan about 0.3 to 0.6 s (indexes are 3.5 to 6 GB each, memory bound) = 1 to 2.3 s. Not measured: no indexes or GPU locally and staging was down. Commands to measure are in section H.

---

## A. Run configuration schema

Stored in `evaluation_runs.configuration_json`. Old runs keep their flat keys; new runs write BOTH the legacy flat keys (`models`, `top_k`, `top_m`, `use_rerank`, `translation_policy`) and a `config` block, so the existing page and `configFingerprint` keep working.

```python
# backend/app/evaluation/config.py  (proposed)
ModelName  = Literal["beit3", "clip", "siglip2"]
TextPolicy = Literal["raw_vi", "translate_gtx", "expand_gemini"]


class TrakeConfig(BaseModel) :
    top_videos : int = Field(20, ge = 1, le = 100)    # K, UI default 20
    gap_c      : int = Field(60, ge = 1, le = 600)    # g in seconds, UI default 60
    min_score  : float = 0.10                         # accepted and ignored by the code path
    local_model : ModelName = "clip"                  # UI default; not an arm
    event_tolerance_s : float = 5.0                   # per-event correctness window


class TextFilterConfig(BaseModel) :
    sources  : list[Literal["ocr", "asr"]] = []       # annotation only, never changes ranking
    asr_mode : Literal["substring", "bm25"] = "substring"
    ocr_mode : Literal["substring"] = "substring"
    cue_set  : str | None = None                      # sidecar id, e.g. "cues-a-draft1"
    what_if  : Literal["inject_exact_top10"] | None = None   # NOT shipped; labelled in every output


class QuerySubset(BaseModel) :
    task_types    : list[Literal["KIS", "QA", "TRAKE"]] | None = None
    exclude_flags : list[str] = []                    # e.g. ["remark_requested"]


class RunConfig(BaseModel) :
    name        : str
    models      : list[ModelName] = ["beit3", "clip", "siglip2"]   # canonicalised to this order
    use_rerank  : bool = True
    top_k       : int = Field(100, ge = 1, le = 500)
    top_m       : int = Field(50, ge = 1, le = 200)
    text_policy : TextPolicy = "expand_gemini"
    task_mode   : Literal["ensemble", "trake_n"] = "ensemble"       # trake_n forces task_types = ["TRAKE"]
    trake       : TrakeConfig = TrakeConfig()
    text_filter : TextFilterConfig = TextFilterConfig()
    subset      : QuerySubset = QuerySubset()
```

Validation: non-empty `models`; duplicates rejected; `task_mode = trake_n` requires default `models` and `use_rerank` (discovery inside `trake_search_candidates` uses all active encoders with rerank and cannot be varied without touching `preprocess.py`); `what_if` requires `text_filter.sources`. Defaults equal section 0.1 except `text_policy` (production has no automatic policy; default is a decision, question 1).

`text_policy` mapping to production code, called directly:

| id | what it is in the UI | function called | recorded |
|---|---|---|---|
| `raw_vi` | operator presses neither button | none, `query_vi` as stored | text |
| `translate_gtx` | Translate button | `translation.translate_vi_to_en(text, policy = "google_gtx_v1")` | text |
| `expand_gemini` | Expand button on a task (TaskBrief, real task type) | `expansion.expand_query(text, task_type)` | `eng_query`, `check_units`, `provider`, `translated_query` |

The six old Gemini policies stay available to the legacy single-run flow only.

Example run config JSON:

```json
{"name": "C03 clip only", "models": ["clip"], "use_rerank": true, "top_k": 100, "top_m": 50,
 "text_policy": "expand_gemini", "task_mode": "ensemble",
 "text_filter": {"sources": []}, "subset": {"task_types": null, "exclude_flags": []}}
```

TRAKE event text (task_mode `trake_n`): events are the seed `trake_events[].description_vi`; the intro sentence is not prepended (production operators type events only). Each event goes through the chosen text policy separately (Expand with task type TRAKE, or gtx). This event-wise path is my construction because production has none.

---

## B. Ablation plan (suite)

One request creates an ordered list of named runs. A run is one (configuration, dataset) pair, so every configuration produces 4 runs (round1-v3, round2-v2, round3-v2, final-v1); the report pools rounds 1 to 3 into Benchmark A (86) and keeps final-v1 as Benchmark B (28). Baseline = all three encoders, rerank on, `expand_gemini` (question 1).

| Id | Configuration | One factor varied |
|---|---|---|
| C01 | baseline | none (also carries the annotation, section D) |
| C02 C03 C04 | beit3 / clip / siglip2 only | encoders |
| C05 C06 C07 | beit3+clip / beit3+siglip2 / clip+siglip2 | encoders |
| C08 | all three, rerank off | rerank |
| C09 C10 C11 | each single, rerank off | rerank |
| C12 | text `translate_gtx` | text policy |
| C13 | text `raw_vi` | text policy |
| T01 | TRAKE-N, K 20, g 60, on TRAKE queries only | task mode |

Core = 13 configurations = 12 retrieval x 4 datasets + T01 x 4 = **52 runs**. Optional (cut first): C14 C15 C16 (pairs, rerank off, free with sharing), T02 to T05 (K 5 and 50, g 30 and 120), W01 (what-if). Optional total up to 52 + 12 + 16 + 4 = 84. No factorial: text policy and TRAKE parameters are crossed with nothing.

Wall-clock estimate (INFERRED, CPU only, per (query, model) 1 to 2.3 s, 114 queries):
- Shared search units: 114 queries x 3 text policies x 3 models = 1,026 model-searches = **17 to 40 min**.
- Without sharing: 24 model-searches per query (grid 12, rerank-off 6, two text policies 6) = 2,736 = **46 to 105 min**.
- LLM cache fill, one time: Expand 114 + 31 events, gtx 114 + 31, paced 4.5 s per provider = **about 11 to 22 min** (parallel per provider about 11).
- T01: 8 queries, about 4 events x full ensemble + in-video scoring, 15 to 40 s each = **2 to 5 min**.
- Annotation: three `annotate_request` calls per query with cues, about 53 queries = minutes.
- Total with sharing **about 35 to 70 min**; without about 60 to 130 min.

Cut list if time runs out, in order: T02 to T05, optional pairs, W01, C12, T01. Never cut C01 to C11. If the Gemini key is unavailable on the day, run with `translate_gtx` as baseline and drop `expand_gemini` arms.

---

## C. Arm sharing, cache, execution

### C.1 Shared search (memoisation)

`backend/app/evaluation/shared_search.py`: `per_model_hits(text, model, top_m) -> {"raw": [...], "reranked": [...]}`, memoised in process on `(sha256(text), model, top_m)`.
- compute: `_load_indexes(); _load_meta(); hits = preprocess._search_one(model, text, top_m)`; if empty store empty; `raw = deepcopy(hits)`; `reranked = preprocess.rerank_one_model(hits, text, model)` (it mutates `hits`, hence the copy first).
- fuse: `preprocess._merge_ensemble({m : lists[m] for m in CANONICAL if m in models and lists[m]}, top_k)` where `lists[m]` is `reranked` or `raw` per `use_rerank`. The merge is the production function itself, so subsets reproduce `ensemble_search` by construction; `active` renormalisation and tie order (canonical model order, same as the UI default) come for free.
- Any run, in any order, only pays for model-searches no earlier run has paid for. The memo lives for the process; a restart recomputes. Memory is trivial (114 x 3 x 50 hits).
- Fallback: if the equivalence test fails or a dependency on the active set appears, the runner calls `ensemble_search(..., models = subset)` per arm, as today.

Equivalence test (`backend/tests/test_evaluation_shared_search.py`): monkeypatch `preprocess._load_indexes`, `_load_meta`, `_search_one`, `rerank_one_model`, `_image_url`, `_has_image` with deterministic fakes that depend only on `(model, query)` (partial per-model coverage, an empty model, tied scores, negative rerank scores to hit the `s_max` fallback). For all 7 subsets x rerank on and off assert that `shared.fuse(...)` equals `ensemble_search(q, 100, 50, rr, models = subset)` row for row (`name`, `distance`, `routes`, order). A real-index version is a script for EC2 (section H) over 10 queries.

### C.2 Record-and-replay cache for LLM text

Table `evaluation_text_cache` (new migration step; CLAUDE.md rule: add a step, never edit a shipped one, do not repeat it in `schema.sql`):

```
id, policy_id, model, prompt_sha256, text_sha256, query_norm, task_type,
output_json, provider, created_at, source_run_id
UNIQUE (policy_id, model, prompt_sha256, text_sha256, task_type)
```
- `text_sha256` is the hash of NFC-normalised, whitespace-collapsed text. `prompt_sha256` = hash of the exact system prompt (`_EXPAND_SYSTEM` or the policy instructions) plus the `[type=...]` wrapper, so a prompt edit invalidates entries automatically. `model` = `gemini-3.5-flash-lite` (or `google_gtx`).
- Expand is recorded only when `provider == "gemini"`. An Ollama fallback result is refused (it would silently change the arm) and surfaces as a prefetch failure.
- Replay: `get_text(policy, query, task_type)` reads the table; no network, no key. Entries are exported to and imported from `seeds/text_cache-*.jsonl` (INSERT OR IGNORE at seed time) so a DB reset or a new host keeps them. Cut candidate: the JSONL export.
- Preflight (`POST /suites` and `POST /runs`): compute the needed `(policy, text, task_type)` set from the selected datasets, subset and TRAKE events; count cached vs missing. Missing and the policy needs a key and the key is unset: **HTTP 422** with a body listing policy, counts and the first 20 missing query keys. Missing and the key is set, or the policy needs none: accepted, and the missing set is filled by a prefetch job that is the FIRST item of the suite in the worker queue. Prefetch is sequential per provider with the 4.5 s floor; if any call fails the suite is stopped before any retrieval and every queued run is marked `failed` with the reason. A run never calls an LLM per query.
- UI: the suite banner shows `cached N, to fetch M, est. T min`; the per-query detail shows `text source: cache | fetched`; `extra_json` holds the cache key digest per query.

### C.3 Suite lifecycle

No suite table. `suite_id` (uuid) and `config_name` live inside `configuration_json`; the run rows are the source of truth.
- `POST /api/admin/evaluation/suites {preset | configs[], datasets[], name}`: preflight, create N `queued` runs in order, enqueue prefetch then the runs. 202 with the run list.
- `GET /suites`, `GET /suites/{id}` (runs grouped by config, counts, ETA from measured ms per query), `POST /suites/{id}/cancel` (cancel every queued run, flag the running one `cancelling`), `POST /suites/{id}/resume` (resume non-completed runs in order; existing `resume_run` is idempotent per run), `GET /suites/{id}/report`.
- The existing 409 rule stays: one active suite or run at a time. The existing single-run flow (`POST /runs`) is unchanged.
- Live API protection: the worker is in the API process, so a suite slows live search (FAISS uses all 8 cores). The competition is over, so default is no throttle; `AIC_EVAL_SLEEP_MS` (default 0) adds a pause between queries, and the UI banner says "shares the live backend". If a live round resumes, cancel the suite.

---

## D. OCR/ASR text-filter evaluation (needs approval)

### D.1 Arms and what they can change

| Arm | Ranking metrics (Hit@k, R@k, MRR) | Annotation-level measures |
|---|---|---|
| none | baseline | none |
| OCR on | **identical to none, by construction** | yes |
| ASR on | **identical to none, by construction** | yes |
| both | **identical to none, by construction** | yes |

They are not retrieval runs. Executing them as separate runs would produce identical ranking rows and waste time. Implementation: C01 (and any run that sets `text_filter.sources`) calls `annotate_request` on the stored `frame_results` for `ocr`, `asr` and `both`, in its own try/except (a side feature must not fail the query), and stores the three annotation blocks in `extra_json`. Zero extra search.

Evaluating Stage D injection would measure something that did not ship. Optional what-if arm W01 (`what_if = "inject_exact_top10"`, off by default, labelled "NOT PART OF THE SHIPPED SYSTEM" in every table, CSV and LaTeX row): offline, exact-match only, text-matched videos with text rank <= 10 are inserted into the ranked video list, no minimum-match floor, declutter off. The insertion position is a free parameter I need from you (default: after visual rank 5). It reports the change in Hit@1, R@5, R@10, MRR next to C01. Recommendation: do not build it unless everything else is done.

### D.2 Manual label schema (sidecar, not a seed edit)

Seed edits are refused by `seed.py` (sha check), so labels live in a sidecar: `backend/app/evaluation/seeds/cues/<dataset_version>.cues.csv`, loaded at run creation and frozen into the run (`extra_json`).

```
dataset_version,query_key,source,term,cue_type,derivable_from_query,reviewer,status
final-v1,f1-tkis-03,asr,"bun ca",spoken_phrase,yes,hongphat,confirmed
```
- `source` ocr|asr; `cue_type` visible_name | number | sign | spoken_phrase; `derivable_from_query` yes|no (an operator typing from the query text alone could have chosen this term); `status` draft | confirmed | legacy_leaky.
- Workflow: a script writes the draft CSV (final-v1 from the LLM, rounds 1 to 3 from the existing `filter_terms` marked `legacy_leaky`); you edit it in a spreadsheet and set `status`. Only `confirmed` rows count as labelled cues. Faster than a labelling view, so the UI stays out of this.
- Existing `filter_terms` are converted, not trusted: `legacy_leaky` rows are reported as an upper bound in a separate column, unless you re-label them.

### D.3 Leakage control

- Terms are drafted by `filter_extraction.extract_filter_terms(query_vi, task_type)`, whose only input is the query text (CONFIRMED signature). It never sees OCR/ASR content. No engine lookup is allowed during drafting.
- Known contamination: the extraction prompt itself holds examples from round-2 queries and says Whisper (ASR is Parakeet). It is used as-is for final-v1 (system evaluated as-is) and disclosed.
- Final-v1 terms: LLM draft from query text only, then your review in the CSV; nobody else confirms. Decide per row, using only the query text, never the video.

### D.4 Metrics

Per source (ocr, asr, both) on the baseline run's stored frames:
- `flag_rate_ref`: the reference video is flagged (here or elsewhere).
- `here_rate`: the matched frame is among the returned rows.
- `in_interval`: a matched frame lies inside a valid interval (KIS/QA only).
- `precision`: flagged videos in the result list that are the reference video / flagged videos in the result list.
- `base_rate`: share of videos in the result list that are flagged.
- `rescue_potential`: reference flagged while rank > 1 (an upper bound on what injection could fix; it is not a ranking effect).
- If W01 is accepted: change in Hit@1, R@5, R@10, MRR.

Slices: (S1) all queries; (S2) queries with at least one confirmed cue; (S3) S2 AND the reference video has coverage for that source (from the loaded artifacts at run time). Counts are printed with every slice.

### D.5 Measurable today versus after the Colab rerun

- Today: Benchmark A (all L, full OCR and ASR) with `legacy_leaky` cues as an upper bound; final-v1 L queries (11); M queries with partial coverage, reported as S2 only.
- After the Colab OCR/ASR rerun for batch 2: M, N, S queries move into S3. The runner records per query `coverage = {ocr: {frames_with_text, keyframes}, asr: {windows, expected}}` read from the artifacts loaded at that moment, so re-running the suite after the data refresh needs no code change.

---

## E. Output and reporting

`backend/app/evaluation/report.py`, reusing `scoring._video_metrics` on result rows (so existing metrics are unchanged):
- Slices: pooled over a suite's datasets (A = round1+2+3, B = final) per configuration; per task type; per round (dataset); per video prefix L/M/N/S; with and without flagged queries (`exclude_flags`).
- Metrics: Hit@1, R@5, R@10, MRR primary; interval R-Score secondary (KIS/QA); TRAKE video-level plus per-event accuracy for T runs; n, failed count; median reference rank; latency p50/p95.
- Per-query rank matrix: rows = queries, columns = configurations, cell = reference video rank (blank = not retrieved), plus flip flags versus the baseline (hit to miss, miss to hit at k = 1 and 5).
- Paired bootstrap (nice to have): 2000 resamples of queries, fixed seed, 95% interval of the difference to the baseline for each metric.
- Export: CSV (long format and the rank matrix); LaTeX with header `Configuration & Hit@1 & R@5 & R@10 & MRR \\`, best value per column in bold, optional `+-` half-width, what-if rows footnoted.
- Provenance per run in `runtime_json` and `extra_json`: full commit hash (`AIC_COMMIT`), short commit, `VERSION`, config hash (sha256 of the canonical config), query-set hash (dataset `source_sha256` plus selected keys), cache key digests, resolved model list, per-model index coverage, `device`, `index_files` identities, torch and faiss versions.

Per-model coverage snapshot (new `evaluation/coverage.py`, read-only over `preprocess` globals, computed once per process): per model `ntotal`, mapping entries, entries present in metadata, and per prefix L/M/N/S the share of metadata frames covered; per seed reference video the share of its keyframes covered by each model. Reported next to every table so single-model arms are read against it. Because arms with different coverage see different pools, the report also carries a sensitivity row restricted to queries whose reference video is fully covered by all three models.

---

## F. UI (Benchmark tab)

Keep `pages/RetrievalBenchmark.tsx` and the single-run flow. Add a second view "Ablation suite" in the same tab:
1. Configuration builder: preset dropdown (Paper core, Encoders only, Text ladder, TRAKE), editable table of configs (checkboxes beit3 / clip / siglip2, rerank toggle, text policy select, task mode, K and g), run count and ETA.
2. Preflight banner: cached / missing counts per policy, key status, 422 messages shown verbatim.
3. Suite progress: one row per configuration with per-dataset status, polling like the existing 2.5 s loop, cancel and resume buttons.
4. Comparison table: rows = configurations, columns Hit@1, R@5, R@10, MRR, n, delta versus baseline; slice selectors (A pooled, B, each round, task type, prefix, include/exclude flagged); CI toggle.
5. Query diff: the rank matrix with flips highlighted.
6. Download buttons: CSV, LaTeX.
Reuse: `StatusBadge`, `ScoreBar`, `pct`, `RAtHeatStrip`, `ResultIndicator`, polling pattern, `configFingerprint` (extended), the two-column layout of `CompareSection` (L310), `listDatasets`/`listRuns`. New: `components/AblationSuite/`, `helpers/ablationTable.ts` (formatting, deltas, LaTeX escape; pure, unit-tested), API functions in `api/retrievalBenchmark.ts`.

---

## G. Change list, effort, order

Order puts the encoder grid and the rerank toggle first. Hours are working estimates including tests.

| # | Item | Files | h | Half-time plan |
|---|---|---|---|---|
| 1 | Config schema, preflight, record-and-replay cache | new `evaluation/config.py`, `evaluation/text_cache.py`, `db/migrations.py` (new step: `evaluation_text_cache`, `evaluation_query_results.extra_json`), `repository.py`, `routers/evaluation.py`, `runner.py` | 3.0 | keep; drop JSONL export |
| 2 | Models and rerank plumbing, shared search | new `evaluation/shared_search.py`, `ensemble.py`, `runner.py`, test | 2.5 | keep |
| 3 | Suites: create, sequential execution, cancel, resume | `routers/evaluation.py`, `repository.py`, `runner.py` | 2.0 | keep |
| 4 | Metrics grouping, compare, CSV, LaTeX, bootstrap | new `evaluation/report.py`, router GET | 3.0 | drop bootstrap |
| 5 | Benchmark tab UI | `RetrievalBenchmark.tsx`, new `components/AblationSuite/`, `api/retrievalBenchmark.ts`, helpers | 4.0 | comparison table and downloads only |
| 6 | TRAKE-N task mode | `ensemble.py`/new `evaluation/trake.py`, `scoring.py` (per-event) | 2.5 | T01 only |
| 7 | Text-filter arms and cue sidecar | new `evaluation/cues.py`, `scripts/draft_cues.py`, `runner.py` | 3.0 | C01 annotation, no W01 |
| 8 | Provenance and coverage snapshot | new `evaluation/coverage.py`, `runner.py` | 1.0 | keep |

Full list about 21 h, more than one day of focused work. Proposed cut line for the deadline: items 1 to 4 and 8 (about 11.5 h), then a minimal item 5 (comparison table and downloads, about 2 h), then 6, then 7 as time allows. If the UI slips, ship `scripts/run_ablation_suite.py` calling the same backend functions and writing CSV and LaTeX, so the table exists regardless.

Regression tests (backend `backend/tests`, frontend vitest):
- default `RunConfig` equals the production default of section 0.1; validation rejects empty or duplicate models and `trake_n` with non-default models;
- shared search equals `ensemble_search` for every subset x rerank (C.1);
- preflight: missing key + missing cache = 422 with the listing; missing key + all cached = accepted; key set = accepted;
- replay: with the key unset and a full cache, no network function is called (monkeypatch raises), including TRAKE event texts;
- cache key stability: same text with different Unicode forms or whitespace gives one key; changing the prompt text changes the key; Ollama fallback is refused;
- `scoring.py` outputs unchanged on a stored legacy run (golden);
- suite: ordering, cancel marks queued runs, resume skips completed;
- report: pooled metrics equal a hand computation, flag exclusion, per-prefix grouping, rank matrix flips, CSV golden, LaTeX golden (header, escaping, bold best);
- TRAKE-N stub: video rank and per-event correctness with tolerance, infeasible chains dropped;
- text-filter metrics on a tiny fixture (3 videos, known cues), three slices;
- frontend: `ablationTable` helpers (delta, flip, LaTeX escape), table render.

Commands after each item (PowerShell, from the worktree):

```powershell
cd C:\Users\hongp\Downloads\aic-ablation\backend
python -m pytest tests -q --basetemp=$env:TEMP\pytest-abl
python -m ruff check app
cd ..\frontend
npm test; npx tsc -b; npm run lint; npm run build
git diff --stat origin/staging -- backend/app/preprocess.py   # must print nothing
```

---

## H. Commands to run on EC2 and what to paste back

1. Hardware and loaded index set (no auth): `curl -s https://aic-api.umaga.fun/status | python3 -c "import sys,json; s=json.load(sys.stdin); print({k:s[k] for k in ('device','active_models','vectors','keyframes','videos','stale_files')})"` and `nproc; free -g; nvidia-smi -L`. Paste the output.
2. Per-model coverage and neighbour gap (host Python, no torch; reads the files in `/opt/aic/indexes`, about 3 GB RAM):
   ```bash
   python3 - <<'PY'
   import json, collections
   d = "/opt/aic/indexes/"
   meta = json.load(open(d + "keyframe_metadata.json"))
   names = {m["name"] for m in meta}
   def mapped(f): return {p.rsplit("/", 1)[-1] for p in json.load(open(d + f)).values() if p}
   maps = {"beit3": mapped("beit3_mapping.json"), "clip": mapped("clip_mapping.json"), "siglip2": mapped("siglip2_giant_mapping.json")}
   by = collections.defaultdict(lambda: collections.Counter())
   for m in meta:
       g = m["video"][0]; by[g]["frames"] += 1; by[g]["empty_neighbors_clip"] += (not m.get("neighbors_clip"))
       for k, s in maps.items(): by[g][k] += (m["name"] in s)
   print("metadata frames", len(meta), {k: len(v) for k, v in maps.items()}, {k: len(v & names) for k, v in maps.items()})
   for g, c in sorted(by.items()): print(g, dict(c))
   PY
   ```
   Paste the output.
3. Seeds loaded on EC2: `docker compose -f /opt/aic/app/docker-compose.yml exec -T api python -c "import sqlite3;c=sqlite3.connect('/opt/aic/data/app.db');print(c.execute('select slug,version,query_count from evaluation_datasets').fetchall())"`. Paste the output.
4. Timing of one query per encoder set (live endpoint, run each twice; the second is the warm number): `curl -s -X POST https://aic-api.umaga.fun/ensemble-search -H 'Content-Type: application/json' -d '{"query":"a lion dance on poles","limit":100,"top_m":50,"use_rerank":true,"models":["beit3","clip","siglip2"]}' | python3 -c "import sys,json; print(json.load(sys.stdin)['processing_time'])"`, then again with `["beit3"]`, `["clip"]`, `["siglip2"]`, and once with `"use_rerank":false`. Paste the five numbers.
5. Is the Gemini key present on the host (value never printed): `grep -c '^GEMINI_API_KEY=.' /opt/aic/app/.env` (1 = set, 0 = missing) and `docker compose -f /opt/aic/app/docker-compose.yml exec -T api python -c "import os;print(bool(os.getenv('GEMINI_API_KEY')))"`. Paste the two answers.
