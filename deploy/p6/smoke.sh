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

# Warm-up reads about 16 GB, and while it does the box is saturated enough that
# Cloudflare intermittently gives up on the origin and answers 520 or 525. That
# is load, not a broken deployment, but a single failed request used to be
# enough to roll a good build back. Retry before believing the failure.
#
# Each attempt writes to a scratch file and only a complete, successful response
# reaches stdout. Letting the caller redirect `retry` directly would open the
# target once and append every partial attempt into it, producing a body that
# parses as neither one response nor the other.
retry() {
  local attempt out="$tmp/.retry-body"
  for attempt in $(seq 1 "${AIC_SMOKE_RETRIES:-6}"); do
    if "$@" > "$out"; then
      cat "$out"
      return 0
    fi
    echo "  request failed, retry $attempt/${AIC_SMOKE_RETRIES:-6}" >&2
    sleep "${AIC_SMOKE_RETRY_DELAY:-10}"
  done
  return 1
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

if [ -n "${AIC_EXPECTED_VERSION:-}" ]; then
  deployed="$(jq -r '.version // "unknown"' "$tmp/health.json")"
  echo "deployed version=$deployed expected=$AIC_EXPECTED_VERSION"
  if [ "$deployed" != "$AIC_EXPECTED_VERSION" ]; then
    echo "Backend serves $deployed but $AIC_EXPECTED_VERSION was deployed" >&2
    exit 1
  fi
fi

retry curl_json "$AIC_BACKEND_URL/status" > "$tmp/status.json"
jq -e '
  (.files | all(.[]; . == true)) and
  (.vectors.beit3 > 0) and
  (.keyframes > 0)
' "$tmp/status.json" > /dev/null

search() {
  curl --fail --silent --show-error --location \
    --user-agent "$UA" \
    --header "Accept: application/json" \
    --header "Content-Type: application/json" \
    --data "{\"query\":\"$QUERY\",\"limit\":10,\"top_m\":100,\"use_rerank\":true}" \
    "$AIC_BACKEND_URL/ensemble-search"
}
retry search > "$tmp/search.json"

jq -e '.returned_results > 0 and (.results | length > 0)' "$tmp/search.json" > /dev/null

frontend() {
  curl --fail --silent --show-error --location \
    --user-agent "$UA" \
    --output /dev/null \
    "$AIC_FRONTEND_URL"
}
retry frontend

echo "Smoke passed"
