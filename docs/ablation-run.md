# Running the ablation suite on EC2 without touching the live API

The suite runs as a SEPARATE PROCESS inside the existing API container. No restart, no redeploy, no
push to `staging`. It reads the same indexes (the container already mounts `/opt/aic/indexes` read-only)
and writes to its own SQLite file under `/opt/aic/data/ablation_out/`, never to `app.db`.

**It shares the 8 CPUs and about 16 GB more RAM with live search.** A second copy of the indexes and
models is loaded for it. Do not run it during a live round. The commands below limit it to 4 threads so
live search keeps some CPU; remove the two thread variables to let it use all 8 (faster, slower live
search). Check memory first: `free -g` must show more than 24 GB available.

Where each command runs is marked **[PC]** (your PowerShell, in `C:\Users\hongp\Downloads\aic-ablation`)
or **[EC2]** (an SSM session on the API host, as root).

## 0. Before you start

- The branch must be committed locally. Nothing is pushed.
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

A presigned URL needs no S3 permission on the instance role (the role may only read `indexes*`).

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

Detached, so it survives the session closing. Expect roughly 35 to 70 minutes with 8 threads and more
with 4 (estimate: about 1 to 2.3 s per query and model, 114 queries, 3 text policies; the script prints
the real seconds per query and a running ETA after every run).

```bash
docker exec -d -e AIC_COMMIT=$SHA -e AIC_DB_PATH=/opt/aic/data/ablation_out/scratch.db \
  -e OMP_NUM_THREADS=4 -e MKL_NUM_THREADS=4 $CID \
  sh -c 'python /tmp/ablation/scripts/run_ablation_suite.py --preset core --out /opt/aic/data/ablation_out > /opt/aic/data/ablation_out/full.out 2>&1'

# watch it
tail -n 5 /opt/aic/data/ablation_out/full.out
```

Optional extras (pairs with rerank off, and the `expand_gemini` rung, which needs `GEMINI_API_KEY` in
the container environment) go in a second run: `--preset extras`. Nothing from `core` is rerun.

To stop it: `docker exec $CID pkill -f run_ablation_suite`. To continue, pass the folder it created:

```bash
docker exec -d -e AIC_COMMIT=$SHA -e AIC_DB_PATH=/opt/aic/data/ablation_out/scratch.db $CID \
  sh -c 'python /tmp/ablation/scripts/run_ablation_suite.py --resume /opt/aic/data/ablation_out/<timestamp> >> /opt/aic/data/ablation_out/full.out 2>&1'
```

The run folder is on the host (`/opt/aic/data` is a bind mount), so it survives the container being
recreated by a deploy. The copied code in `/tmp/ablation` does not: repeat step 3 after a deploy.

## 6. Get the output back

Output is small once the database is left out (CSVs, LaTeX, provenance, log).

```bash
cd /opt/aic/data/ablation_out
tar czf /tmp/ablation-out-$SHA.tgz --exclude=ablation.db --exclude=scratch.db <timestamp>
ls -la /tmp/ablation-out-$SHA.tgz
```

**A. S3, from the instance** (works only if the instance role may write the bucket; if it answers
AccessDenied use B):

```bash
aws s3 cp /tmp/ablation-out-$SHA.tgz s3://aic2026-artifacts/ablation/out/ablation-out-$SHA.tgz
```

then on the PC: `aws s3 cp s3://aic2026-artifacts/ablation/out/ablation-out-$SHA.tgz . --profile aic`.

**B. Presigned PUT, no instance permission needed.** On the PC (needs `pip install boto3`):

```powershell
python -c "import boto3; s=boto3.Session(profile_name='aic').client('s3'); print(s.generate_presigned_url('put_object', Params={'Bucket':'aic2026-artifacts','Key':'ablation/out/ablation-out-$sha.tgz'}, ExpiresIn=7200))"
```

On EC2: `curl -fsS -T /tmp/ablation-out-$SHA.tgz '<that URL>'`, then download with `aws s3 cp` as above.

**C. Last resort, copy through the session** (the archive is about 1 MB): `base64 -w0 /tmp/ablation-out-$SHA.tgz`,
paste the line into a file on the PC and decode with `[IO.File]::WriteAllBytes("out.tgz", [Convert]::FromBase64String((Get-Content b64.txt -Raw)))`.

The database `ablation.db` (tens of MB: every query's ranked frames) stays on the host; fetch it the same
way if you want per-query frame lists.

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
  each column in bold; `*_noflag.tex` drops the flagged queries (the 49 `vfr_times` videos and the
  whole-video interval).
- `rank_matrix_A.csv`, `rank_matrix_B.csv`: the reference video's rank per query and configuration, and
  `flip@1`, `flip@5` (gained or lost against C01) for failure analysis.
- `bootstrap_A.csv`, `bootstrap_B.csv`: difference to C01 per metric with a 95% interval, 2000
  resamples of queries, fixed seed. Paired: every configuration sees the same resampled queries.
- `provenance.json`: full commit, VERSION, every configuration with its hash, seconds per run, per-model
  index coverage and library versions of the first run.
- The text policy is `translate_gtx` for every configuration except C12 (raw Vietnamese). The labels are
  team-annotated, not official; benchmark B has the team's appeal answers with a plus or minus 5 s interval.
