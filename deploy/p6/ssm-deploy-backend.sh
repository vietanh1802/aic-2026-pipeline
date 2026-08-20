#!/usr/bin/env bash
set -euo pipefail

: "${AIC_INSTANCE_ID:?AIC_INSTANCE_ID is required}"
: "${AIC_NEW_IMAGE:?AIC_NEW_IMAGE is required}"
: "${AIC_DEPLOY_ID:?AIC_DEPLOY_ID is required}"
# The payload builder below reads this out of os.environ, so the default has
# to be exported. Written as `: "${VAR:=default}"` it set a shell variable the
# child process never saw, and the default only appeared to work because the
# workflow always passes the value explicitly.
export AIC_REMOTE_APP_DIR="${AIC_REMOTE_APP_DIR:-/opt/aic/app}"
: "${AWS_REGION:?AWS_REGION is required}"
# The 100s ceiling on `aws ssm wait command-executed` is not enough for a
# deploy onto a box that was stopped between sessions: it pulls the image
# cold and recreates the container. When the waiter gave up, the job failed
# and the workflow stopped the instance out from under a command that was
# still running.
: "${AIC_SSM_TIMEOUT_SECONDS:=1800}"

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

remote="$tmp/remote-deploy.sh"
cat > "$remote" <<'REMOTE'
set -euo pipefail

: "${AIC_NEW_IMAGE:?}"
: "${AIC_DEPLOY_ID:?}"
: "${AIC_REMOTE_APP_DIR:?}"

cd "$AIC_REMOTE_APP_DIR"

if [ -n "${GHCR_USERNAME:-}" ] && [ -n "${GHCR_TOKEN:-}" ]; then
  printf '%s' "$GHCR_TOKEN" | docker login ghcr.io --username "$GHCR_USERNAME" --password-stdin
fi

rollback_tag="aic2026-api:rollback-$AIC_DEPLOY_ID"
if docker image inspect aic2026-api:local >/dev/null 2>&1; then
  docker tag aic2026-api:local "$rollback_tag"
fi

# The database lives on the host beside the indexes. Docker would create the
# directory itself, but only as root with no way to say what mode — making it
# here keeps ownership predictable for backups.
mkdir -p /opt/aic/data

docker pull "$AIC_NEW_IMAGE"
docker tag "$AIC_NEW_IMAGE" aic2026-api:local
# A deploy killed between compose renaming the running container and creating
# its replacement leaves the old one as <id>_<service>. Compose then refuses
# every later deploy with a name conflict, so one interrupted run wedges the
# pipeline until someone logs in and deletes the container by hand. The
# canonical name carries no underscore prefix, so it never matches this filter.
leftovers="$(docker ps -a --filter 'name=_aic2026-api-1' --format '{{.Names}}' || true)"
if [ -n "$leftovers" ]; then
  echo "removing containers left by an aborted deploy: $leftovers"
  docker rm -f $leftovers
fi

docker compose up -d --force-recreate api
docker compose ps api

# Seed the six accounts. Idempotent: an account that already exists keeps its
# password, so this is a no-op on every deploy after the first. It has to run
# here because there is no member-management screen — a fresh database with no
# rows means nobody can sign in and there is no way to fix that from the UI.
#
# Best effort: the API is still warming up (90-145s) and the accounts are not
# needed until a human logs in, so a failure here must not roll back a
# perfectly good image. The smoke test is what decides that.
if ! docker compose exec -T api python -m scripts.seed_team; then
  echo "WARNING: seeding failed; run 'docker compose exec api python -m scripts.seed_team' by hand" >&2
fi
REMOTE

command_payload="$tmp/command.json"
python - "$remote" "$command_payload" <<'PY'
import json
import os
import pathlib
import sys

remote = pathlib.Path(sys.argv[1]).read_text()
exports = {
    "AIC_NEW_IMAGE": os.environ["AIC_NEW_IMAGE"],
    "AIC_DEPLOY_ID": os.environ["AIC_DEPLOY_ID"],
    "AIC_REMOTE_APP_DIR": os.environ["AIC_REMOTE_APP_DIR"],
    "GHCR_USERNAME": os.environ.get("GHCR_USERNAME", ""),
    "GHCR_TOKEN": os.environ.get("GHCR_TOKEN", ""),
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
    --comment "P6 deploy backend $AIC_DEPLOY_ID" \
    --parameters "file://$command_payload" \
    --query 'Command.CommandId' \
    --output text
)"

echo "SSM deploy command_id=$command_id"
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
  echo "SSM deploy finished with status=$status" >&2
  exit 1
fi
