#!/usr/bin/env bash
set -euo pipefail

: "${AIC_INSTANCE_ID:?AIC_INSTANCE_ID is required}"
: "${AIC_POWER_ACTION:?AIC_POWER_ACTION is required}"
: "${AWS_REGION:?AWS_REGION is required}"

UA="${AIC_SMOKE_UA:-Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36 AIC-P6-Power/1.0}"

state() {
  aws ec2 describe-instances \
    --region "$AWS_REGION" \
    --instance-ids "$AIC_INSTANCE_ID" \
    --query 'Reservations[0].Instances[0].State.Name' \
    --output text
}

case "$AIC_POWER_ACTION" in
  start)
    current="$(state)"
    echo "current_state=$current"
    if [ "$current" = "stopped" ]; then
      aws ec2 start-instances --region "$AWS_REGION" --instance-ids "$AIC_INSTANCE_ID"
      aws ec2 wait instance-running --region "$AWS_REGION" --instance-ids "$AIC_INSTANCE_ID"
    fi
    echo "state=$(state)"
    ;;
  stop)
    current="$(state)"
    echo "current_state=$current"
    if [ "$current" = "running" ]; then
      aws ec2 stop-instances --region "$AWS_REGION" --instance-ids "$AIC_INSTANCE_ID"
      aws ec2 wait instance-stopped --region "$AWS_REGION" --instance-ids "$AIC_INSTANCE_ID"
    fi
    echo "state=$(state)"
    ;;
  status)
    echo "state=$(state)"
    if [ "${AIC_BACKEND_URL:-}" ]; then
      curl --silent --show-error --location \
        --user-agent "$UA" \
        --max-time 10 \
        "$AIC_BACKEND_URL/health" || true
      echo
    fi
    ;;
  *)
    echo "Unsupported action: $AIC_POWER_ACTION" >&2
    exit 2
    ;;
esac
