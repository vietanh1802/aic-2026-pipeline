#!/usr/bin/env bash
set -euo pipefail

: "${AIC_INSTANCE_ID:?AIC_INSTANCE_ID is required}"
: "${AIC_DEPLOY_ID:?AIC_DEPLOY_ID is required}"
: "${AIC_REMOTE_APP_DIR:=/opt/aic/app}"
: "${AWS_REGION:?AWS_REGION is required}"

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

remote="$tmp/remote-rollback.sh"
cat > "$remote" <<'REMOTE'
set -euo pipefail

: "${AIC_DEPLOY_ID:?}"
: "${AIC_REMOTE_APP_DIR:?}"

cd "$AIC_REMOTE_APP_DIR"

rollback_tag="aic2026-api:rollback-$AIC_DEPLOY_ID"
docker image inspect "$rollback_tag" >/dev/null
docker tag "$rollback_tag" aic2026-api:local
docker compose up -d --force-recreate api
docker compose ps api
REMOTE

command_payload="$tmp/command.json"
python - "$remote" "$command_payload" <<'PY'
import json
import os
import pathlib
import sys

remote = pathlib.Path(sys.argv[1]).read_text()
exports = {
    "AIC_DEPLOY_ID": os.environ["AIC_DEPLOY_ID"],
    "AIC_REMOTE_APP_DIR": os.environ["AIC_REMOTE_APP_DIR"],
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
    --comment "P6 rollback backend $AIC_DEPLOY_ID" \
    --parameters "file://$command_payload" \
    --query 'Command.CommandId' \
    --output text
)"

echo "SSM rollback command_id=$command_id"
aws ssm wait command-executed \
  --region "$AWS_REGION" \
  --command-id "$command_id" \
  --instance-id "$AIC_INSTANCE_ID"

aws ssm get-command-invocation \
  --region "$AWS_REGION" \
  --command-id "$command_id" \
  --instance-id "$AIC_INSTANCE_ID" \
  --query '{Status:Status,StandardOutputContent:StandardOutputContent,StandardErrorContent:StandardErrorContent}' \
  --output json
