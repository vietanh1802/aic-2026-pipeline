#!/usr/bin/env bash
set -euo pipefail

: "${AIC_BACKEND_URL:?AIC_BACKEND_URL is required}"
: "${AIC_FRONTEND_URL:?AIC_FRONTEND_URL is required}"

UA="${AIC_SMOKE_UA:-Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36 AIC-P6-Smoke/1.0}"
QUERY="${AIC_SMOKE_QUERY:-orange news graphics}"

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

curl_json() {
  curl --fail --silent --show-error --location \
    --user-agent "$UA" \
    --header "Accept: application/json" \
    "$@"
}

echo "Smoke: waiting for backend warm-up at $AIC_BACKEND_URL"
ready=0
for _ in $(seq 1 48); do
  if curl_json "$AIC_BACKEND_URL/health" > "$tmp/health.json"; then
    state="$(jq -r '.warmup.state // "unknown"' "$tmp/health.json")"
    echo "health warmup.state=$state"
    if [ "$state" = "ready" ]; then
      ready=1
      break
    fi
    if [ "$state" = "failed" ]; then
      cat "$tmp/health.json"
      exit 1
    fi
  fi
  sleep 10
done

if [ "$ready" != "1" ]; then
  echo "Backend did not report warmup.state=ready in time"
  cat "$tmp/health.json" 2>/dev/null || true
  exit 1
fi

curl_json "$AIC_BACKEND_URL/status" > "$tmp/status.json"
jq -e '
  (.files | all(.[]; . == true)) and
  (.vectors.beit3 > 0) and
  (.keyframes > 0)
' "$tmp/status.json" > /dev/null

curl --fail --silent --show-error --location \
  --user-agent "$UA" \
  --header "Accept: application/json" \
  --header "Content-Type: application/json" \
  --data "{\"query\":\"$QUERY\",\"limit\":10,\"top_m\":100,\"use_rerank\":true}" \
  "$AIC_BACKEND_URL/ensemble-search" > "$tmp/search.json"

jq -e '.returned_results > 0 and (.results | length > 0)' "$tmp/search.json" > /dev/null

curl --fail --silent --show-error --location \
  --user-agent "$UA" \
  --output /dev/null \
  "$AIC_FRONTEND_URL"

echo "Smoke passed"
