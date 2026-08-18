# Updating the indexes

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

5. Verify `/status` reports the new counts and `/health` reports `warmup.state: ready`.

6. Bump `VERSION` so the running build can be identified.

## Traps

- **Index, mapping and metadata must change together.** A mismatch makes `faiss_id` point at
  the wrong frame. Nothing raises; the results are just silently wrong.
- **`docker ps` showing `healthy` proves nothing.** The healthcheck only asks whether
  `/health` returns 200, and it does that even when warm-up has failed. Read `warmup.state`.
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

## Outstanding

`open_clip_model.safetensors` is on the API host but **not yet in
`s3://aic2026-artifacts/indexes/`**: the instance role has read-only access to that bucket, by
design. Until it is published, a rebuilt instance syncing from S3 will not get the CLIP weights
and will hit the read-only failure again. To publish it, grant `s3:PutObject` on
`arn:aws:s3:::aic2026-artifacts/indexes/*` to `aic2026-api-ec2-role` long enough to run the
upload, then remove it.
