# Updating the indexes

Step-by-step runbook for the team, in Vietnamese: [`huong-dan-cap-nhat-index.md`](huong-dan-cap-nhat-index.md). This file is the reference behind it — what the pieces are and what goes wrong.

`/opt/aic/indexes` holds two different kinds of file:

- **Index data**, produced by the offline notebooks — `beit3.index`, `clip.index`,
  `beit3_mapping.json`, `clip_mapping.json`, `keyframe_metadata.json`, `keyframes_list.json`.
- **Model weights**, downloaded once and then kept — `beit3_large_patch16_384_coco_retrieval.pth`,
  `beit3.spm`, `open_clip_model.safetensors`.

`s3://aic2026-artifacts/indexes/` is the canonical copy. The API host syncs from it, and
docker-compose mounts the directory into the container **read-only**.

## Steps

1. Regenerate the index files locally. They land in `backend/app/indexes/`.

2. Publish to S3 first — it is the source of truth.

   ```powershell
   aws s3 sync backend/app/indexes/ s3://aic2026-artifacts/indexes/ --profile aic
   ```

   Add `--delete` when files have been removed. Without it the old ones stay and the host
   ends up holding both.

   Steps 3 to 5 below are what the `Indexes` workflow runs, so in practice they
   are one button. They are kept here because knowing what the button does is the
   difference between fixing a red run and guessing at it.

3. Pull onto the API box:

   ```bash
   aws s3 sync s3://aic2026-artifacts/indexes/ /opt/aic/indexes/
   ```

4. Restart the API container. This is required, not optional: indexes are cached in module
   globals and loaded once, so a running container keeps serving the old data even after the
   files on disk change.

   ```bash
   cd /opt/aic/app && sudo docker compose restart api
   ```

   Warm-up takes 90–140s.

5. Verify. `/health` must report `warmup.state: ready`, and `/status` must report
   `stale_files: []` with every `index_files.<name>.loaded` fingerprint matching what
   `head-object` returns for the same key in S3. `deploy/p6/verify-indexes.sh` does
   both, plus a real `/ensemble-search` call.

6. Bump `VERSION` so the running build can be identified.

## Traps

- **Index, mapping and metadata must change together.** A mismatch makes `faiss_id` point at
  the wrong frame. Nothing raises; the results are just silently wrong.
- **`docker ps` showing `healthy` proves nothing.** The healthcheck only asks whether
  `/health` returns 200, and it does that even when warm-up has failed. Read `warmup.state`.
- **Counts cannot tell a new index set from an old one.** A rebuild over the same
  keyframes reports the same `keyframes` and `vectors.beit3`, and those numbers are read
  from module globals — so a container that never restarted reports exactly what a
  correctly updated one does. `index_files` records the size and mtime of each file as it
  was read into memory; `stale_files` lists the ones the disk has moved on from. Non-empty
  `stale_files` means the sync landed and the restart did not.
- **The directory is mounted read-only on purpose.** Anything the API tries to write there
  fails with `OSError: [Errno 30] Read-only file system`. Every weight the API needs must be
  staged into the directory ahead of time, never downloaded by the running container.

## Why the read-only trap is called out

`_ensure_clip_checkpoint()` fetches the CLIP weights with `hf_hub_download(local_dir=INDEX_DIR)`.
That works on a developer machine, where the directory is writable, and fails in production,
where it is not. Warm-up died with `Read-only file system: '/opt/aic/indexes/.cache'`, the smoke
test refused the deploy, and the pipeline rolled back — the deploy machinery behaved correctly;
the assumption about the directory did not.

The fix was to stage `open_clip_model.safetensors` into `/opt/aic/indexes/` so the
`os.path.exists()` guard short-circuits and the container writes nothing. The weights were
already on the host inside the HuggingFace cache, so this was a local copy rather than a
10.2 GB download.

## Publishing weights to S3

`aic2026-api-ec2-role` is read-only on the artifacts bucket by design, so the API box cannot
overwrite the canonical index set. Publishing a new weight file therefore needs a grant that is
added and then taken away:

```powershell
aws iam put-role-policy --role-name aic2026-api-ec2-role --policy-name tmp-publish-indexes `
  --policy-document file://deploy/p7/tmp-publish-indexes-policy.json --profile aic
# run the upload from the host, verify with head-object, then:
aws iam delete-role-policy --role-name aic2026-api-ec2-role --policy-name tmp-publish-indexes --profile aic
```

Pass the policy as `file://`. Inlining JSON on the command line fails on Windows with
`MalformedPolicyDocument`, because the quotes are stripped before the CLI sees them. Allow a few
seconds for the grant to propagate before the first upload attempt.

The index set in S3 is now self-contained: 9 objects, 15.0 GiB, including
`open_clip_model.safetensors`. A rebuilt instance that syncs from S3 gets everything the API
needs and never downloads at run time.
