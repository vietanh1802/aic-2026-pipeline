# Running the ablation suite on EC2 (preset core2)

The suite runs as a SEPARATE PROCESS in a SEPARATE CONTAINER, with the live API stopped. It reads the same indexes
(the compose service mounts `/opt/aic/indexes`) and writes to its own SQLite file under `/opt/aic/data/ablation_out/`,
never to `app.db`. Nothing is pushed or deployed: the code comes from a `git archive` of the local commit.

Where each command runs is marked **[PC]** (your PowerShell, in `C:\Users\hongp\Downloads\aic-ablation`) or **[EC2]**
(the AWS console **Session Manager** shell on the API host, as root: open the instance in the AWS console, Connect,
Session Manager, then `sudo -i` if the prompt is not root). There is no `aws ssm start-session` step: that is for a
terminal with the AWS CLI, and this guide does not assume one on the EC2 side.

## 0. The memory lesson: never run the suite inside the live container

Measured on the instance (CPU only, `r6i.2xlarge`, 8 vCPU, 61 GB, no swap):

- the live API process holds about **32 GB** (three encoders, three indexes, the metadata, OCR and ASR);
- the suite loads its own copy of the same indexes and models, about **32 GB** more;
- so the two do not fit together. The first attempt, run inside the live container, was killed by the kernel (OOM) while
  loading SigLIP2. With no swap, an out-of-memory kill can take the live API with it.

The procedure that worked, and the only one this guide supports: **stop the API, run the suite in a separate container
started with `docker compose run`, start the API afterwards.** The API is down for the length of the run. Do not run
this during a live round. Measured on the first real run (commit 9a6f528, preset `core`, 60 runs, 114 queries, API
stopped, all 8 CPUs): **16 minutes** in total, the first arm of a text about 2 s per query (it pays for the three
per-model searches), later arms about 0.12 s per query (they reuse them), `C13` (post-fusion rerank) 0.75 s per query,
TRAKE-N about 15 s per query (every event is a full ensemble search). Expand calls are paced at 4.5 s each (the shared
provider pacing of `translation.py`).

For `core2` expect roughly 20 to 30 minutes of retrieval (INFERRED, not measured: three texts instead of two, plus the
Expand events of TRAKE-N), plus a few minutes to load and to verify shared search. The 145 Expand texts add about 15
minutes of paced network calls if they are fetched inside the run; step 4 fetches them BEFORE the API is stopped, so they
cost no downtime. The script prints seconds per query and an ETA after every run; trust that over this paragraph.

## 1. [PC] Build the archive

```powershell
cd C:\Users\hongp\Downloads\aic-ablation
$sha = (git rev-parse HEAD).Trim()
git archive --format=tar.gz -o "$env:TEMP\aic-ablation-$sha.tar.gz" HEAD
echo $sha
```

Use the commit you intend to run (the newest on `feature/ablation-benchmark`). The archive has no `.git`, so the EC2
commands pass `AIC_COMMIT` and provenance records it. The committed `seeds/text_cache/translate_gtx.jsonl` already holds
the 145 plain-translation texts, so `C14` needs no call to Google.

## 2. [PC] Hand the archive to EC2 with a presigned URL

```powershell
$bucket = "aic2026-artifacts"
aws s3 cp "$env:TEMP\aic-ablation-$sha.tar.gz" "s3://$bucket/ablation/aic-ablation-$sha.tar.gz" --profile aic
aws s3 presign "s3://$bucket/ablation/aic-ablation-$sha.tar.gz" --expires-in 7200 --profile aic
```

Copy the printed URL. A presigned URL needs no S3 permission on the instance role.

## 3. [EC2] Unpack, and check the two things that went wrong last time

```bash
export SHA=<the sha from step 1>
export URL='<the presigned URL>'
export COMPOSE="docker compose -f /opt/aic/app/docker-compose.yml"
export CID=$($COMPOSE ps -q api)

mkdir -p /opt/aic/ablation/src-$SHA
curl -fsSL -o /opt/aic/ablation/aic-ablation-$SHA.tar.gz "$URL"
tar xzf /opt/aic/ablation/aic-ablation-$SHA.tar.gz -C /opt/aic/ablation/src-$SHA

# Copies into the running container's own filesystem only for the two checks below. The image, the live
# process and app.db are untouched. The suite itself later mounts the same folder into its own container.
docker cp /opt/aic/ablation/src-$SHA $CID:/tmp/ablation
free -g
```

**3a. Does Gemini answer?** One real Expand call, made the way the suite makes it. It exits non-zero unless the provider
is Gemini (no Ollama or other fallback), and on a failure it prints the cause that `expand_query` hides (HTTP status,
exception type; the key is never printed):

```bash
docker exec $CID python /tmp/ablation/scripts/check_expand.py
```

Expect `provider gemini`, an `elapsed_ms` of about a second, an `eng_query` word count and a `check_units` count, and
`OK: Gemini answered`. Anything else: fix the key or the network first (the presence of `GEMINI_API_KEY` in the
container, which provenance records, does not prove it is valid).

**3b. Are the OCR and ASR texts loadable, and does the lookup find terms?** Loads no encoder model, about 5 GB of RAM:

```bash
docker exec -e AIC_INDEX_DIR=/opt/aic/indexes $CID python /tmp/ablation/scripts/check_text_artifacts.py
```

It prints each artifact file (path, exists, size), whether this process loaded them, keyframes with OCR and ASR text per
prefix L, M, N, S with the same `get_text` functions annotation uses, a lookup test of five round 2 ASR cues in their
reference videos with the matched snippet, and whether the three tokenizers load (or fall back to a labelled estimate).
Paste the output back. The suite script now loads the ASR text itself and refuses to start without it; this check shows
why if it cannot.

## 4. [EC2] Fetch the Expand texts while the API is still up (saves about 15 minutes of downtime)

This needs the archive of a commit that contains `prefetch_text_cache.py --policy expand_gemini` (the one this guide ships
with). It loads no index and no model, so it fits next to the live API. It calls the production Expand function (paced at
4.5 s per call, Gemini answers only), rewrites the file after every text, and resumes if run again:

```bash
docker exec -d -e AIC_INDEX_DIR=/opt/aic/indexes $CID \
  sh -c 'python /tmp/ablation/scripts/prefetch_text_cache.py --preset core2 --policy expand_gemini --out /opt/aic/data/ablation_out/text_cache.jsonl > /opt/aic/data/ablation_out/prefetch.out 2>&1'
tail -n 3 /opt/aic/data/ablation_out/prefetch.out        # "needed 145, cached before 0, fetched 145, failed 0" at the end
```

The suite imports `/opt/aic/data/ablation_out/text_cache.jsonl` when it starts (`--text-cache` changes the path), finds
the Expand arm fully cached and makes no provider call. Skipping this step is safe: the suite then fetches the missing
texts itself before creating any run, and stops with every failed text listed if one cannot be fetched.

## 5. [EC2] Stop the API and run the suite in its own container

```bash
$COMPOSE stop api
free -g                       # "available" should now be above 50 GB

$COMPOSE run -d --no-deps --name ablation-run \
  -v /opt/aic/ablation/src-$SHA:/tmp/ablation \
  -e AIC_COMMIT=$SHA -e AIC_DB_PATH=/opt/aic/data/ablation_out/scratch.db \
  api sh -c 'python /tmp/ablation/scripts/run_ablation_suite.py --preset core2 --out /opt/aic/data/ablation_out > /opt/aic/data/ablation_out/core2.out 2>&1'

tail -n 5 /opt/aic/data/ablation_out/core2.out           # watch it
docker ps --filter name=ablation-run                      # still running?
```

`AIC_DB_PATH` points at a scratch file only as a second safety: the script already uses its own database inside the run
folder. No thread limit is set: nothing else is running, so the suite may use all 8 CPUs.

What the script does, in order, and what it prints: refuses to start if the OCR or ASR text did not load; verifies that
`shared_search` reproduces `ensemble_search` on the real indexes (17 PASS lines, refuses on a FAIL); prints how many texts
are needed, cached and missing; fetches the missing ones (failure stops it with every failed text listed, nothing
falls back to another provider; what was fetched stays in `text_cache.jsonl`); creates the 76 runs; runs them, printing
one line per run with seconds per query and an ETA. It ends with `done`.

A started run can be stopped with `docker stop ablation-run`; to continue, start a new container (the finished queries are
kept) and pass the folder it created:

```bash
docker rm ablation-run
$COMPOSE run -d --no-deps --name ablation-run \
  -v /opt/aic/ablation/src-$SHA:/tmp/ablation \
  -e AIC_COMMIT=$SHA -e AIC_DB_PATH=/opt/aic/data/ablation_out/scratch.db \
  api sh -c 'python /tmp/ablation/scripts/run_ablation_suite.py --resume /opt/aic/data/ablation_out/<timestamp> >> /opt/aic/data/ablation_out/core2.out 2>&1'
```

An optional smoke test first (three queries per dataset, 19 x 4 = 76 runs of 3 queries; most of the time is loading), into
its own folder: the same command with `--limit-queries 3 --out /opt/aic/data/ablation_smoke`. A smoke folder is stamped
SMOKE by the analysis and is never a result.

## 6. [EC2] When it says `done`: corpus features, then start the API again

```bash
docker rm ablation-run

# Corpus features for the analysis (statistics only, no models, about 3 GB of RAM). Also writes, per video, the share of
# keyframes with stored neighbour links that table T4b needs.
$COMPOSE run --rm --no-deps -v /opt/aic/ablation/src-$SHA:/tmp/ablation -e AIC_INDEX_DIR=/opt/aic/indexes \
  api python /tmp/ablation/scripts/dump_corpus_features.py --index-dir /opt/aic/indexes --out /opt/aic/data/ablation_out/features

$COMPOSE start api
free -g
docker exec $CID python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=5).read().decode())"
```

The API reloads its indexes and models after the start (the first minutes show `warming` on `/health`). The feature dump
prints the totals for paper section 3.1 (videos, hours as a lower bound, keyframes, shots, per prefix) and the stored-link
counts per prefix.

## 7. [EC2] Pack the output, [PC] bring it back and analyse

```bash
cd /opt/aic/data/ablation_out
ls -d 20*                                                  # the run folder name, <timestamp>
tar czf /tmp/ablation-out-$SHA.tgz --exclude=scratch.db <timestamp> features text_cache.jsonl
ls -la /tmp/ablation-out-$SHA.tgz
```

Keep `ablation.db-wal` and `-shm` if they exist (they are part of the database); leave out only `scratch.db`. The
database holds every query's ranked frames, roughly 60 to 100 MB per 60 runs raw, several times smaller compressed.

**A. S3 from the instance** (not tested: the role works with the CLI, a write to the artifacts bucket has not been tried;
use B on AccessDenied):

```bash
aws s3 cp /tmp/ablation-out-$SHA.tgz s3://aic2026-artifacts/ablation/out/ablation-out-$SHA.tgz
```

then on the PC: `aws s3 cp s3://aic2026-artifacts/ablation/out/ablation-out-$SHA.tgz . --profile aic`.

**B. Presigned PUT, no instance permission needed.** On the PC (needs `pip install boto3`):

```powershell
python -c "import boto3; s=boto3.Session(profile_name='aic').client('s3'); print(s.generate_presigned_url('put_object', Params={'Bucket':'aic2026-artifacts','Key':'ablation/out/ablation-out-$sha.tgz'}, ExpiresIn=7200))"
```

On EC2: `curl -fsS -T /tmp/ablation-out-$SHA.tgz '<that URL>'`, then download with `aws s3 cp` as above.

**C. Last resort, through the session**: only practical for the tables, not the database. Pack a small archive with
`--exclude=ablation.db*`, `base64 -w0` it, paste the line into a file on the PC and decode with
`[IO.File]::WriteAllBytes("out.tgz", [Convert]::FromBase64String((Get-Content b64.txt -Raw)))`.

On the PC, unpack and analyse (the analysis never touches the live system, and also reads a folder made with the older
presets):

```powershell
pip install -r scripts\requirements-analysis.txt
python scripts\analyze_ablation.py --run-dir <timestamp> --features features
```

## 8. [EC2] Clean up

```bash
docker exec $CID rm -rf /tmp/ablation
rm -rf /opt/aic/ablation /tmp/ablation-out-$SHA.tgz
```

## Presets

`--preset` takes one name or several joined with commas.

| Preset | Use | Contents |
|---|---|---|
| `core2` | the paper's main run (default) | 19 configurations x 4 datasets = 76 runs, the Expand text as the baseline, below |
| `core` | the first real run (folder 20261004-045103) | plain translation as the baseline, `C12` raw Vietnamese, `C13` post-fusion rerank; 15 configurations |
| `trake` | the first run's TRAKE part | `T01` TRAKE-N and `T02` plain ensemble, plain-translation text |
| `extras` | pairs with rerank off and an Expand rung | kept so an old command still resolves |

`core2` arms (every arm searches the Expand text unless it varies the text):

| Code | Configuration | One factor varied |
|---|---|---|
| C01 | all three encoders, per-model rerank, Expand | baseline; also carries the OCR/ASR annotation |
| C02 C03 C04 | beit3 / clip / siglip2 only | encoders |
| C05 C06 C07 | beit3+clip / beit3+siglip2 / clip+siglip2 | encoders |
| C08 | all three, rerank off | rerank |
| C09 C10 C11 | each single encoder, rerank off | rerank |
| C12a C12b C12c | each pair, rerank off | rerank (pairs, so the encoder grid is not confounded) |
| C13 | rerank after fusion ("post-fusion rerank, our implementation") | rerank placement, exploratory |
| C14 | plain translation (`translate_gtx`) | **text ablation: C01 against C14 is the text claim** |
| C15 | raw Vietnamese, `sanity = true` | sanity check, not an arm: kept in the CSVs, left out of the paper tables, shown once in `table_sanity.tex` and T5s |
| T01 | TRAKE-N, K 20, g 60 s, Expand per event | task mode |
| T02 | TRAKE queries, plain ensemble over the whole text | task mode |

The suite never calls an LLM per query: the text of every arm is recorded once (`evaluation_text_cache`) and replayed.
A text that cannot be fetched stops the suite before any run is created.

### From 2026-10-05: Benchmark B is `final-v2`, presets `core3`, `rerank_diag`, `final_table`

`DEFAULT_DATASETS` now ends with `final-v2` (KIS and QA cut to the question plus the first two pieces of information).
Never mix `final-v1` and `final-v2` numbers in one table.

Expand returns two texts in one Gemini answer: the rewritten sentence (`search_query`, policy `expand_gemini`) and the
keyword list (`check_units`, policy `expand_keywords`, joined by ", "). `expand_keywords` reads the same recorded answer,
so it needs no extra call; prefetching `expand_gemini` covers it.

`core3` (39 configurations, A and B) = `core2` plus:

| Code | Configuration |
|---|---|
| C16 to C22 | plain translation, rerank off, the seven encoder sets (beit3, clip, siglip2, the three pairs, all three) |
| C23 to C29 | Expand keywords, rerank off, the seven encoder sets |
| C30 | all three, Expand keywords, rerank on |
| T01g, T01k | TRAKE-N on plain translation, on Expand keywords |
| T02b, T02g, T02k | TRAKE queries, whole-description ensemble, rerank off: Expand sentence, plain translation, Expand keywords |

`rerank_diag` (24 configurations, **Benchmark A only**: `--datasets round1-v3,round2-v2,round3-v2`): the grid R01 to R12
of `HANDOVER/rerank_selection_rule.md` on each Expand output (suffix S sentence, K keywords). Rerank variants run through
`rerank_mode = "variant"` (`backend/app/evaluation/rerank_variants.py`); the shipped parameters reproduce
`ensemble_search` (one more line in the equivalence gate, now 18 lines). Then on the PC:

```bash
python scripts/select_rerank_variant.py --run-dir <rerank_diag folder>   # refuses a folder with any B row
git add backend/app/evaluation/frozen_selection.json && git commit -m "Freeze the rerank and text selection"
```

`final_table` (A and B, run once after the freeze) reads `frozen_selection.json`: F01 full system, F02 without rerank (left
out when the frozen setting is rerank off), F03 plain translation, F04 to F06 one encoder removed, F07 the other Expand
output.

## Reading the results

- `results_long.csv`: one row per configuration x benchmark (A = rounds 1 to 3 pooled, B = final-v1, and each round) x
  flag mode (`all` or `exclude_flagged`) x slice (all, KIS, QA, TRAKE, prefix L, M, N, S). Columns: n, failed, hit_at_1,
  r_at_5, r_at_10, mrr, median_rank, interval_final_score (interval R-Score, KIS and QA), event_accuracy, annotation_errors,
  sanity. Hit@1, R@5, R@10 and MRR are video level.
- `table_A.tex`, `table_B.tex`: the paper table, `Configuration & Hit@1 & R@5 & R@10 & MRR`, best value of each column in
  bold, without the sanity arm; `*_noflag.tex` drops the flagged queries (see "Flags"); `table_sanity.tex` shows the
  baseline next to the sanity arm.
- `rank_matrix_A.csv`, `rank_matrix_B.csv`: the reference video's rank per query and configuration, and `flip@1`,
  `flip@5` against C01. `bootstrap_A.csv`, `bootstrap_B.csv`: difference to C01 per metric, 95% interval, 2000 resamples
  of queries, fixed seed, paired.
- `text_signal.csv` (cues labelled in `seeds/cues/`): OCR and ASR annotation measures of the baseline per benchmark, cue
  kind (`confirmed`, or `legacy_leaky`, the seeds' old filter terms, an upper bound), variant (ocr, asr, both) and slice
  (all queries, with a cue, with a cue and OCR/ASR coverage of the reference video), each under the shipped OR rule over the
  terms and under a strict rule (all terms of a source's cue in the video). Annotation only: nothing here changes a ranking.
- `text_cache.jsonl`: every recorded text, gtx and Expand (`eng_query`, `check_units`, provider), importable on another host.
- `provenance.json`: full commit, VERSION, every configuration with its hash, seconds per run, per-model index coverage,
  which OCR and ASR files loaded (`runtime_first_run.text_artifacts`), library versions.
- The analysis folder adds, among others: T5 (the text ablation C01 against C14), T5b and T5c (tokens of the searched text
  against each encoder's context, and Hit@1 of the queries over the limit against the rest), T5s (raw Vietnamese,
  sanity), T4b (rerank on against off by stored neighbour links; needs `--features`), and claim C10 in `claims_check.md`
  (LLM-prepared text against plain translation, arms C01 and C14).
- The labels are team-annotated, not official; benchmark B has the team's appeal answers with a plus or minus 5 s interval.

## Flags, and what the exclude_flagged tables change

Two label flags exist (`seeds/flags/`): `vfr_times` (49 N videos whose keyframe timestamps drift from the container clock,
so interval results on them are unreliable) and `whole_video_interval` (the valid interval is the whole video, so the
interval metric is trivially a hit). The id spelling matches: the flag file and the final-v1 seed both write N and S ids
with a hyphen (`N061-V002`, `S01-V009`) and L and M ids with an underscore, the forms `frontend/src/helpers/frameRef.ts`
documents for the real data (`tests/test_evaluation_flags.py` pins the spelling).

How many queries carry each flag (checked by calling `flags.flags_for` on every query of every seed):

| Dataset | Queries | vfr_times | whole_video_interval |
|---|---|---|---|
| round1-v3 | 24 | 0 | 0 |
| round2-v2 | 29 | 0 | 0 |
| round3-v2 | 33 | 0 | 0 |
| final-v1 | 28 | 0 | 1 (`f2-qa-03`, L27_V012) |

The two N reference videos of final-v1 (`N061-V002`, `N025-V002`) are not among the 49 `vfr_times` ids, so the flag does not
fire for them. Consequence: the `exclude_flagged` tables can differ from the all-queries tables only on benchmark B, by the
one query `f2-qa-03` (n goes from 28 to 27). A flagged query is dropped from every metric of that table, video level included.

## What is stored per query (extra_json), for the offline analysis

Besides the columns of `evaluation_query_results` (video rank and hits, interval metrics, `frame_results_json` with the 100
fused frames and each frame's per-model `routes` rank and cosine, `ranked_videos_json` with every video's first-appearance
rank and its first three frames), `extra_json` holds:

- `model_timings`: per model `search_ms` (text encoding plus the FAISS scan) and `rerank_ms`, as measured the first time that
  model was computed for that text, `reused` (true when an earlier arm had already paid), and `fuse_ms` (plus
  `pool_rerank_ms` per model for `after_fusion`). The wall-clock `retrieval_ms` of an arm is NOT its cost, because later
  arms reuse earlier searches; a configuration's latency is rebuilt as the sum of its models' `search_ms` and `rerank_ms`
  plus `fuse_ms`.
- `text_length`: per encoder the tokens of the searched text under that encoder's own tokenizer (the longest event for
  TRAKE-N), its context limit, `over_limit`, `truncated` (over the limit AND the production code cuts: OpenCLIP and
  SigLIP2 do, BEiT-3 does not) and `method` (`tokenizer`, or `estimate: <why>` when a tokenizer was not on the host).
- `interval_gap` (KIS and QA): the returned frame of the reference video closest to the valid interval, its rank and frame
  index, `gap_frames`, `gap_s` and the `fps` used, and how many of the 100 frames belong to the reference video.
- TRAKE-N: `trake.events` (chosen frame and error in seconds per event), `trake.shortlist` and `trake.discovery`; `consistent`
  must be true.
- text, policy and cache digest, `text_provider`, `check_units` (Expand), `flags`, `text_coverage` (keyframes of the reference
  video with OCR and ASR text, `null` for a source that was not loaded), `text_signal`, `video_coverage`.
