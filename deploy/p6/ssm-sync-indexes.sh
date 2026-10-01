#!/usr/bin/env bash
#
# Pull the canonical index set from S3 onto the API host and restart the API.
#
# This is steps 3 and 4 of docs/updating-indexes.md. Step 2 — uploading the new
# index set from a workstation to S3 — stays manual: the files are 15 GB and live
# on the operator's machine, where no runner can reach them.
set -euo pipefail

: "${AIC_INSTANCE_ID:?AIC_INSTANCE_ID is required}"
: "${AWS_REGION:?AWS_REGION is required}"
# : "${AIC_INDEX_S3_URI:=s3://aic2026-artifacts/indexes/}"
# Old default. That prefix does not exist on the new AWS account (334737651335);
# the live set is indexes_LMNS_v002/ (v001 + M06_V024-V030 from notebook 125d,
# plus OCR and asr/ from notebook 127). v002 holds no model checkpoints — those
# stay in indexes_LMNS_v001/ and are already on the host — see the --delete
# guard below.
: "${AIC_INDEX_S3_URI:=s3://aic2026-artifacts/indexes_LMNS_v002/}"
: "${AIC_REMOTE_INDEX_DIR:=/opt/aic/indexes}"
: "${AIC_REMOTE_APP_DIR:=/opt/aic/app}"
: "${AIC_SYNC_DELETE:=false}"
# The API reads roughly 16 GB during warm-up, so a cold sync plus a restart can
# run well past the 100s that `aws ssm wait command-executed` allows by default.
: "${AIC_SSM_TIMEOUT_SECONDS:=1800}"
# A sync from an empty or mistyped prefix would, with --delete, erase the index
# set the running API depends on. Refuse to proceed unless the source holds at
# least this many objects. The real set has 9.
: "${AIC_MIN_SOURCE_OBJECTS:=5}"

bucket="${AIC_INDEX_S3_URI#s3://}"
prefix="${bucket#*/}"
bucket="${bucket%%/*}"

echo "Source: s3://$bucket/$prefix"
source_objects="$(
  aws s3api list-objects-v2 \
    --region "$AWS_REGION" \
    --bucket "$bucket" \
    --prefix "$prefix" \
    --query 'length(Contents || `[]`)' \
    --output text
)"
echo "source_objects=$source_objects"

if [ "$source_objects" -lt "$AIC_MIN_SOURCE_OBJECTS" ]; then
  echo "Refusing to sync: source holds $source_objects objects, expected at least $AIC_MIN_SOURCE_OBJECTS" >&2
  echo "Publish the index set to $AIC_INDEX_S3_URI before running this workflow." >&2
  exit 1
fi

# --delete against a prefix without the model checkpoints (v002 is one) would
# wipe beit3_large_patch16_384_coco_retrieval.pth, open_clip_model.safetensors and
# siglip2_giant_model/ from the host, and the container mounts the directory
# read-only so it cannot fetch them back. Nothing raises until the next restart.
if [ "$AIC_SYNC_DELETE" = "true" ] && ! aws s3api head-object \
    --region "$AWS_REGION" --bucket "$bucket" \
    --key "${prefix}beit3_large_patch16_384_coco_retrieval.pth" > /dev/null 2>&1; then
  echo "Refusing --delete: s3://$bucket/$prefix holds no model checkpoints, so --delete would remove them from the host." >&2
  echo "Run without delete_removed." >&2
  exit 1
fi

export AIC_SYNC_DELETE_FLAG=""
if [ "$AIC_SYNC_DELETE" = "true" ]; then
  export AIC_SYNC_DELETE_FLAG="--delete"
  echo "Sync mode: --delete (files absent from S3 will be removed from the host)"
else
  echo "Sync mode: additive (stale files stay on the host)"
fi

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

remote="$tmp/remote-sync.sh"
cat > "$remote" <<'REMOTE'
set -euo pipefail

: "${AIC_INDEX_S3_URI:?}"
: "${AIC_REMOTE_INDEX_DIR:?}"
: "${AIC_REMOTE_APP_DIR:?}"

echo "== disk before =="
df -h "$AIC_REMOTE_INDEX_DIR" | tail -1

echo "== sync =="
aws s3 sync "$AIC_INDEX_S3_URI" "$AIC_REMOTE_INDEX_DIR/" ${AIC_SYNC_DELETE_FLAG:-} --only-show-errors
ls -la "$AIC_REMOTE_INDEX_DIR"

echo "== disk after =="
df -h "$AIC_REMOTE_INDEX_DIR" | tail -1

# Indexes are cached in module globals and read once per process. Without this
# the container keeps serving the previous index set from memory, and the files
# on disk say the update worked.
echo "== restart api =="
cd "$AIC_REMOTE_APP_DIR"
docker compose restart api
docker compose ps api
REMOTE

command_payload="$tmp/command.json"
python3 - "$remote" "$command_payload" <<'PY'
import json
import os
import pathlib
import sys

remote = pathlib.Path(sys.argv[1]).read_text()
exports = {
    "AIC_INDEX_S3_URI": os.environ["AIC_INDEX_S3_URI"],
    "AIC_REMOTE_INDEX_DIR": os.environ["AIC_REMOTE_INDEX_DIR"],
    "AIC_REMOTE_APP_DIR": os.environ["AIC_REMOTE_APP_DIR"],
    "AIC_SYNC_DELETE_FLAG": os.environ.get("AIC_SYNC_DELETE_FLAG", ""),
}
prefix = "\n".join(f"export {key}={json.dumps(value)}" for key, value in exports.items())
command = f"{prefix}\nbash -se <<'REMOTE'\n{remote}\nREMOTE"
pathlib.Path(sys.argv[2]).write_text(json.dumps({"commands": [command]}))
PY

command_id="$(
  aws ssm send-command \
    --region "$AWS_REGION" \
    --instance-ids "$AIC_INSTANCE_ID" \
    --document-name AWS-RunShellScript \
    --comment "Sync index set from S3 and restart API" \
    --timeout-seconds "$AIC_SSM_TIMEOUT_SECONDS" \
    --parameters "file://$command_payload" \
    --query 'Command.CommandId' \
    --output text
)"
echo "SSM sync command_id=$command_id"

# Poll rather than `aws ssm wait command-executed`: that waiter gives up after
# 100s, which a 15 GB sync can exceed.
deadline=$(( SECONDS + AIC_SSM_TIMEOUT_SECONDS ))
status="Pending"
while [ "$SECONDS" -lt "$deadline" ]; do
  status="$(
    aws ssm get-command-invocation \
      --region "$AWS_REGION" \
      --command-id "$command_id" \
      --instance-id "$AIC_INSTANCE_ID" \
      --query 'Status' \
      --output text 2>/dev/null || echo Pending
  )"
  case "$status" in
    Success|Failed|Cancelled|TimedOut) break ;;
  esac
  echo "  status=$status"
  sleep 15
done

aws ssm get-command-invocation \
  --region "$AWS_REGION" \
  --command-id "$command_id" \
  --instance-id "$AIC_INSTANCE_ID" \
  --query '{Status:Status,StandardOutputContent:StandardOutputContent,StandardErrorContent:StandardErrorContent}' \
  --output json

if [ "$status" != "Success" ]; then
  echo "SSM sync finished with status=$status" >&2
  exit 1
fi
