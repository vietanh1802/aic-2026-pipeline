# Running the ablation suite on EC2 without touching the live API

The suite runs as a SEPARATE PROCESS inside the existing API container. No restart, no redeploy, no
push to `staging`. It reads the same indexes (the container already mounts `/opt/aic/indexes` read-only)
and writes to its own SQLite file under `/opt/aic/data/ablation_out/`, never to `app.db`.

**It shares the 8 CPUs and the RAM with live search, and the memory margin is thin.** Measured on the
instance (CPU only, 8 vCPU, 61 GB, no swap): about 29 GB is available while the live API runs, and the
suite loads a second copy of the indexes and models into that. With no swap, running out means the kernel
kills a process, possibly the live API. Watch available memory (`free -g`, the `available` column) and
stop the suite if it drops below about 6 GB: `docker exec $CID pkill -f run_ablation_suite` (a
`--resume` continues it later). Do not run it during a live round. The commands below limit it to 4
threads so live search keeps some CPU; remove the two thread variables to let it use all 8 (faster,
slower live search). Check memory first: `free -g` must show more than 24 GB available.

Where each command runs is marked **[PC]** (your PowerShell, in `C:\Users\hongp\Downloads\aic-ablation`)
or **[EC2]** (an SSM session on the API host, as root).

## 0. Before you start

- The branch must be committed locally. Nothing is pushed.
- The API runs in the container `api` and listens on port 8000 inside it; use `docker exec`, not a public
  URL. Health and memory from the host shell: `export CID=$(docker compose -f /opt/aic/app/docker-compose.yml ps -q api)`,
  then `docker exec $CID python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=5).read().decode())"`
  and `free -g`. Measured on the live endpoint, warm, one query: all three encoders with rerank 1.58 s,
  BEiT-3 alone 0.28 s, CLIP alone 0.76 s, SigLIP2 alone 0.54 s, all three with rerank off 1.02 s. The first
  call after a restart took 12.9 s (cold).
- The text cache must be full or fetchable. `translate_gtx` calls Google Translate: from the PC used
  for development it answered **HTTP 429** on the first call today, and EC2 may be blocked as well. If a
  call fails, run the prefetch script from a machine that can reach Google (step 1b) and ship the file
  with the archive.

## 1. [PC] Build the archive

```powershell
cd C:\Users\hongp\Downloads\aic-ablation
$sha = (git rev-parse HEAD).Trim()
git archive --format=tar.gz -o "$env:TEMP\aic-ablation-$sha.tar.gz" HEAD
echo $sha
```

### 1b. [PC] Optional: prefetch the gtx texts and ship them in the archive

About 145 texts (114 queries + 31 TRAKE events), 4.5 s each, about 11 minutes. It prints how many were
fetched, already cached and failed, and can be rerun until failed is 0.

```powershell
python scripts\prefetch_text_cache.py --preset core
git add backend\app\evaluation\seeds\text_cache\translate_gtx.jsonl
git commit -m "chore(evaluation): gtx text cache for the core preset"
$sha = (git rev-parse HEAD).Trim()
git archive --format=tar.gz -o "$env:TEMP\aic-ablation-$sha.tar.gz" HEAD
```

The seed import loads every `seeds/text_cache/*.jsonl` when the suite starts, so EC2 then finds the
cache full and makes no network call.

## 2. [PC] Hand the archive to EC2 with a presigned URL

A presigned URL needs no S3 permission on the instance role. The role works with the AWS CLI (account and
role were confirmed with `aws sts get-caller-identity`), but a write to the artifacts bucket has not been
tested from the instance, so this guide does not depend on it.

```powershell
$bucket = "aic2026-artifacts"
aws s3 cp "$env:TEMP\aic-ablation-$sha.tar.gz" "s3://$bucket/ablation/aic-ablation-$sha.tar.gz" --profile aic
aws s3 presign "s3://$bucket/ablation/aic-ablation-$sha.tar.gz" --expires-in 7200 --profile aic
```

Copy the printed URL. Then open a shell on the host (instance id from the GitHub variable
`AIC_API_INSTANCE_ID`): `aws ssm start-session --target <instance-id> --profile aic`, and `sudo -i`.

## 3. [EC2] Put the code into the running container

```bash
export SHA=<the sha from step 1>
export URL='<the presigned URL>'
export COMPOSE="docker compose -f /opt/aic/app/docker-compose.yml"
export CID=$($COMPOSE ps -q api)

mkdir -p /opt/aic/ablation/src-$SHA
curl -fsSL -o /opt/aic/ablation/aic-ablation-$SHA.tar.gz "$URL"
tar xzf /opt/aic/ablation/aic-ablation-$SHA.tar.gz -C /opt/aic/ablation/src-$SHA

# Copies into the running container's own filesystem. The image, the live process and app.db are untouched.
docker cp /opt/aic/ablation/src-$SHA $CID:/tmp/ablation
free -g
```

`AIC_COMMIT` is passed on every run below because an archive has no `.git`; provenance records it.

## 3b. [EC2] Verify shared search against the live search (gates the full run)

The suite fuses memoised per-model lists instead of calling `ensemble_search` once per configuration.
That is only valid if both give the same ranking on the real indexes. This checks it for all 7 encoder
subsets with rerank `per_model` and `off` over the first 5 queries of a dataset (frame order and every
score within 1e-6), one PASS or FAIL line per subset and mode (14 lines). It then checks that the
re-created `after_fusion` order equals `per_model` for each single encoder, where there is nothing to
fuse (3 more lines, 17 in all). It exits non-zero on any FAIL. It loads the indexes and models like the
suite does, so it takes a few minutes.

```bash
docker exec -e AIC_DB_PATH=/opt/aic/data/ablation_out/scratch.db -e OMP_NUM_THREADS=4 -e MKL_NUM_THREADS=4 $CID   python /tmp/ablation/scripts/verify_shared_search.py --dataset round1-v3 --n 5
```

Paste back the 17 lines and the last line (`ALL PASS` or `FAILED`). `run_ablation_suite.py` runs the same
check first on its own and refuses to start when it fails (`--skip-verify` bypasses it, and the
provenance then records that it was skipped), so this step is for seeing the result early.

## 4. [EC2] Smoke test (about 5 to 10 minutes)

Three queries per dataset, 13 configurations x 4 datasets = 52 runs of 3 queries. Most of the time is
loading the indexes and models once.

```bash
docker exec -e AIC_COMMIT=$SHA -e AIC_DB_PATH=/opt/aic/data/ablation_out/scratch.db \
  -e OMP_NUM_THREADS=4 -e MKL_NUM_THREADS=4 $CID \
  python /tmp/ablation/scripts/run_ablation_suite.py --preset core --limit-queries 3 --out /opt/aic/data/ablation_out
```

It must end with `done` and print a seconds-per-query line per run. Look at the newest folder:

```bash
ls /opt/aic/data/ablation_out/*/
cat /opt/aic/data/ablation_out/*/table_A.tex
```

`AIC_DB_PATH` is set to a scratch file only as a second safety: the script already uses its own
database inside the run folder, and this makes sure nothing can reach `/opt/aic/data/app.db` by accident.

## 5. [EC2] The full run

Detached, so it survives the session closing.

Time. Measured: the warm single-query timings in section 0 (1.58 s for all three encoders with rerank). A
derived estimate, NOT measured, for the core preset is roughly 15 to 25 minutes. It comes from: 228 text
variants (114 queries x 2 texts, `translate_gtx` and `raw_vi`) each searched once per model because the
per-model searches are shared across the arms (228 x about 1.6 s is about 6 minutes), plus loading a
second copy of the indexes (a few minutes), plus the `after_fusion` arm, which reranks a candidate pool
under every model (a few minutes), plus the OCR/ASR annotation and per-run overhead. With 4 threads and a
live API competing it is at the slower end. The script prints the real seconds per query and a running ETA
after every run; trust that over this paragraph.

```bash
docker exec -d -e AIC_COMMIT=$SHA -e AIC_DB_PATH=/opt/aic/data/ablation_out/scratch.db \
  -e OMP_NUM_THREADS=4 -e MKL_NUM_THREADS=4 $CID \
  sh -c 'python /tmp/ablation/scripts/run_ablation_suite.py --preset core --out /opt/aic/data/ablation_out > /opt/aic/data/ablation_out/full.out 2>&1'

# watch it
tail -n 5 /opt/aic/data/ablation_out/full.out
```

`--preset trake` (T01 TRAKE-N and T02 plain ensemble on the 8 TRAKE queries) is a SEPARATE second
invocation of the same command with `--preset trake` in place of `--preset core`, started after the core run
has finished (the runner allows one run at a time, and the memory margin above does not allow two copies of
the suite). It writes its own run folder. Optional extras (pairs with rerank off, and the `expand_gemini`
rung, which needs `GEMINI_API_KEY` in the container environment) are likewise a further invocation:
`--preset extras`. Nothing from `core` is rerun.

To stop it: `docker exec $CID pkill -f run_ablation_suite`. To continue, pass the folder it created:

```bash
docker exec -d -e AIC_COMMIT=$SHA -e AIC_DB_PATH=/opt/aic/data/ablation_out/scratch.db $CID \
  sh -c 'python /tmp/ablation/scripts/run_ablation_suite.py --resume /opt/aic/data/ablation_out/<timestamp> >> /opt/aic/data/ablation_out/full.out 2>&1'
```

The run folder is on the host (`/opt/aic/data` is a bind mount), so it survives the container being
recreated by a deploy. The copied code in `/tmp/ablation` does not: repeat step 3 after a deploy.

## 6. Get the output back

The offline analysis (scripts/analyze_ablation.py) needs `ablation.db`, so the archive includes it. The
database holds every query's ranked frames and is roughly 60 to 100 MB raw (a synthetic run of the same
size is 62 MB), several times smaller compressed. Corpus features come first, because the analysis uses them
(statistics only, no models are loaded; it parses the full keyframe metadata, about 3 GB of RAM):

```bash
docker exec -e AIC_INDEX_DIR=/opt/aic/indexes $CID python /tmp/ablation/scripts/dump_corpus_features.py   --index-dir /opt/aic/indexes --out /opt/aic/data/ablation_out/features
```

It prints the totals for paper section 3.1 (videos, hours as a lower bound, keyframes, shots, keyframes per
shot, per prefix) and writes videos.csv, shots.csv, frames_ref.csv, index_files.csv and corpus_totals.json.
Then pack the run folder AND the features folder (keep the `ablation.db-wal` and `-shm` files if present,
they are part of the database; leave out only `scratch.db`):

```bash
cd /opt/aic/data/ablation_out
tar czf /tmp/ablation-out-$SHA.tgz --exclude=scratch.db <timestamp> features
ls -la /tmp/ablation-out-$SHA.tgz
```

On the PC, unpack and analyse (the analysis never touches the live system):

```powershell
pip install -r scriptsequirements-analysis.txt
python scriptsnalyze_ablation.py --run-dir <timestamp> --features features
```

**A. S3, from the instance** (not tested: the role is known to work with the CLI, but a write to the
artifacts bucket has not been tried; if it answers AccessDenied use B):

```bash
aws s3 cp /tmp/ablation-out-$SHA.tgz s3://aic2026-artifacts/ablation/out/ablation-out-$SHA.tgz
```

then on the PC: `aws s3 cp s3://aic2026-artifacts/ablation/out/ablation-out-$SHA.tgz . --profile aic`.

**B. Presigned PUT, no instance permission needed.** On the PC (needs `pip install boto3`):

```powershell
python -c "import boto3; s=boto3.Session(profile_name='aic').client('s3'); print(s.generate_presigned_url('put_object', Params={'Bucket':'aic2026-artifacts','Key':'ablation/out/ablation-out-$sha.tgz'}, ExpiresIn=7200))"
```

On EC2: `curl -fsS -T /tmp/ablation-out-$SHA.tgz '<that URL>'`, then download with `aws s3 cp` as above.

**C. Last resort, copy through the session**: only practical for the tables, not for the database. Pack a
small archive with `--exclude=ablation.db*`, `base64 -w0` it, paste the line into a file on the PC and decode with
`[IO.File]::WriteAllBytes("out.tgz", [Convert]::FromBase64String((Get-Content b64.txt -Raw)))`. The analysis
then has to wait for a route A or B copy of the database.

## 7. [EC2] Clean up

```bash
docker exec $CID rm -rf /tmp/ablation
rm -rf /opt/aic/ablation /tmp/ablation-out-$SHA.tgz
```

## Reading the results

- `results_long.csv`: one row per configuration x benchmark (A = rounds 1 to 3 pooled, B = final-v1,
  round1 to round3 alone) x flag mode (`all` or `exclude_flagged`) x slice (all, KIS, QA, TRAKE, prefix
  L, M, N, S). Columns: n, failed, hit_at_1, r_at_5, r_at_10, mrr, median_rank, interval_final_score
  (interval R-Score, KIS and QA). Hit@1, R@5, R@10 and MRR are video level.
- `table_A.tex`, `table_B.tex`: the paper table, `Configuration & Hit@1 & R@5 & R@10 & MRR`, best value of
  each column in bold; `*_noflag.tex` drops the flagged queries (see "Flags" below for which ones exist).
- `rank_matrix_A.csv`, `rank_matrix_B.csv`: the reference video's rank per query and configuration, and
  `flip@1`, `flip@5` (gained or lost against C01) for failure analysis.
- `bootstrap_A.csv`, `bootstrap_B.csv`: difference to C01 per metric with a 95% interval, 2000
  resamples of queries, fixed seed. Paired: every configuration sees the same resampled queries.
- `text_signal.csv` (only when cues are labelled in `seeds/cues/`): OCR and ASR annotation measures of the
  baseline, per benchmark, cue kind (`confirmed`, or `legacy_leaky` = the seed's old filter_terms, an upper
  bound), variant (ocr, asr, both) and slice (all queries, with a cue, with a cue and OCR/ASR coverage of the
  reference video). They never change a ranking. Per-video OCR/ASR coverage is recorded in every run.
- TRAKE: `--preset trake` runs T01 (TRAKE-N, K 20, g 60 s) and T02 (plain ensemble over the whole text) on
  the 8 TRAKE queries; `event_accuracy` in `results_long.csv` is the share of events within 5 s of the
  team's reference frame. Run it after `core`; `core` is unaffected.
- `provenance.json`: full commit, VERSION, every configuration with its hash, seconds per run, per-model
  index coverage and library versions of the first run.
- The text policy is `translate_gtx` for every configuration except C12 (raw Vietnamese). The labels are
  team-annotated, not official; benchmark B has the team's appeal answers with a plus or minus 5 s interval.

## Flags, and what the exclude_flagged tables change

Two label flags exist (`seeds/flags/`): `vfr_times` (49 N videos whose keyframe timestamps drift from the
container clock, so interval results on them are unreliable) and `whole_video_interval` (the valid interval
is the whole video, so the interval metric is trivially a hit). The id spelling matches: the flag file and the
final-v1 seed both write N and S ids with a hyphen (`N061-V002`, `S01-V009`) and L and M ids with an
underscore, the forms `frontend/src/helpers/frameRef.ts` documents for the real data (the EC2 keyframe metadata
was not inspected for this), so no normalisation is needed (`tests/test_evaluation_flags.py` pins the spelling).

How many queries carry each flag (checked by calling `flags.flags_for` on every query of every seed):

| Dataset | Queries | vfr_times | whole_video_interval |
|---|---|---|---|
| round1-v3 | 24 | 0 | 0 |
| round2-v2 | 29 | 0 | 0 |
| round3-v2 | 33 | 0 | 0 |
| final-v1 | 28 | 0 | 1 (`f2-qa-03`, L27_V012) |

The two N reference videos of final-v1 (`N061-V002`, `N025-V002`) are not among the 49 `vfr_times` ids, so the
flag does not fire for them. Whether they were measured at all is not recorded here (the source file
`paper_stats/timestamp_check.csv` is not in the repository).

Consequence: the `exclude_flagged` tables can differ from the all-queries tables only on benchmark B, because
rounds 1 to 3 are all L videos and carry no flag. On B the only difference is the one query `f2-qa-03` (n goes
from 28 to 27). A flagged query is dropped from every metric of that table, video level included, so the
difference is not limited to the interval columns.

## What is stored per query (extra_json), for the offline analysis

Besides the columns of `evaluation_query_results` (video rank and hits, interval metrics, `frame_results_json`
with the 100 fused frames and each frame's per-model `routes` rank and cosine, `ranked_videos_json` with every
video's first-appearance rank and its first three frames), `extra_json` holds:

- `model_timings`: per model `search_ms` (text encoding plus the FAISS scan) and `rerank_ms`, as measured the
  first time that model was computed for that text, `reused` (true when an earlier arm had already paid),
  and `fuse_ms` (plus `pool_rerank_ms` per model for `after_fusion`). The wall-clock `retrieval_ms` of an
  arm is NOT its cost, because later arms reuse earlier searches; a configuration's latency is rebuilt as
  the sum of its models' `search_ms` and `rerank_ms` plus `fuse_ms`.
- `interval_gap` (KIS and QA): the returned frame of the reference video closest to the valid interval, its
  rank and frame index, `gap_frames`, `gap_s` and the `fps` used, and how many of the 100 frames belong to
  the reference video. It covers only the returned frames.
- TRAKE-N: `trake.events` (chosen frame and error in seconds per event), `trake.shortlist` (videos with a
  feasible chain) and `trake.discovery`: the reference video's rank in the rebuilt shortlist stage, how many
  events returned it, whether it was shortlisted and whether a feasible chain exists. `consistent` must be
  true: it checks that every video the real call returned is in the rebuilt shortlist.
- text, policy and cache digest, `check_units`, `flags`, `text_coverage`, `text_signal`, `video_coverage`.
