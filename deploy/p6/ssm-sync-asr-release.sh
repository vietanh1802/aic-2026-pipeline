#!/usr/bin/env bash
#
# Pull the canonical ASR release from S3 onto the API host and restart the API.
#
# The ASR release is published manually from a workstation because the artifact
# contains model/index files that are not stored in git.
#

set -euo pipefail

: "${AIC_INSTANCE_ID:?AIC_INSTANCE_ID is required}"
: "${AWS_REGION:?AWS_REGION is required}"

: "${AIC_ASR_RELEASE_S3_URI:=s3://aic2026-artifacts/releases/aic2026-full-20260817-r01/}"
: "${AIC_REMOTE_ASR_DIR:=/opt/aic/asr/aic2026-full-20260817-r01}"
: "${AIC_REMOTE_APP_DIR:=/opt/aic/app}"

: "${AIC_SYNC_DELETE:=false}"

# ASR release is small, but allow enough time for SSM + restart.
: "${AIC_SSM_TIMEOUT_SECONDS:=1800}"

# Prevent accidental sync from an empty/wrong prefix.
: "${AIC_MIN_SOURCE_OBJECTS:=5}"


bucket_path="${AIC_ASR_RELEASE_S3_URI#s3://}"
bucket="${bucket_path%%/*}"
prefix="${bucket_path#*/}"

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
  echo "Refusing to sync: source contains $source_objects objects, expected at least $AIC_MIN_SOURCE_OBJECTS" >&2
  echo "Upload ASR release to $AIC_ASR_RELEASE_S3_URI first." >&2
  exit 1
fi


export AIC_SYNC_DELETE_FLAG=""

if [ "$AIC_SYNC_DELETE" = "true" ]; then
  export AIC_SYNC_DELETE_FLAG="--delete"
  echo "Sync mode: --delete"
else
  echo "Sync mode: additive"
fi


tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT


remote="$tmp/remote-sync-asr.sh"

cat > "$remote" <<'REMOTE'
set -euo pipefail


: "${AIC_ASR_RELEASE_S3_URI:?}"
: "${AIC_REMOTE_ASR_DIR:?}"
: "${AIC_REMOTE_APP_DIR:?}"


echo "== disk before =="

mkdir -p "$AIC_REMOTE_ASR_DIR"

df -h "$AIC_REMOTE_ASR_DIR" | tail -1


echo "== sync ASR release =="

aws s3 sync \
  "$AIC_ASR_RELEASE_S3_URI" \
  "$AIC_REMOTE_ASR_DIR/" \
  ${AIC_SYNC_DELETE_FLAG:-} \
  --only-show-errors


echo "== ASR files =="

ls -lah "$AIC_REMOTE_ASR_DIR"


echo "== disk after =="

df -h "$AIC_REMOTE_ASR_DIR" | tail -1


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
    "AIC_ASR_RELEASE_S3_URI": os.environ["AIC_ASR_RELEASE_S3_URI"],
    "AIC_REMOTE_ASR_DIR": os.environ["AIC_REMOTE_ASR_DIR"],
    "AIC_REMOTE_APP_DIR": os.environ["AIC_REMOTE_APP_DIR"],
    "AIC_SYNC_DELETE_FLAG": os.environ.get("AIC_SYNC_DELETE_FLAG", ""),
}


prefix = "\n".join(
    f"export {key}={json.dumps(value)}"
    for key, value in exports.items()
)


command = f"{prefix}\nbash -se <<'REMOTE'\n{remote}\nREMOTE"


pathlib.Path(sys.argv[2]).write_text(
    json.dumps({"commands": [command]})
)
PY


command_id="$(
  aws ssm send-command \
    --region "$AWS_REGION" \
    --instance-ids "$AIC_INSTANCE_ID" \
    --document-name AWS-RunShellScript \
    --comment "Sync ASR release from S3 and restart API" \
    --timeout-seconds "$AIC_SSM_TIMEOUT_SECONDS" \
    --parameters "file://$command_payload" \
    --query 'Command.CommandId' \
    --output text
)"


echo "SSM sync command_id=$command_id"


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
    Success|Failed|Cancelled|TimedOut)
      break
      ;;
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
  echo "SSM ASR sync finished with status=$status" >&2
  exit 1
fi