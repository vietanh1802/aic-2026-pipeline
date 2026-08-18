#!/usr/bin/env bash
#
# Wait for the API to finish warm-up, then check that the index set it loaded is
# internally consistent.
#
# The failure this exists to catch is silent. When the FAISS index, the id->path
# mapping and the keyframe metadata do not come from the same generation run, a
# faiss_id resolves to the wrong frame. Nothing raises; searches keep returning
# results and the results are simply wrong. The counts below are the cheapest
# signal that the three files disagree.
set -euo pipefail

: "${AIC_BACKEND_URL:?AIC_BACKEND_URL is required}"

# Cloudflare answers a request with no User-Agent with `403 error code: 1010`,
# so identify as a browser the way the smoke test does.
UA="${AIC_SMOKE_UA:-Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36 AIC-P6-IndexVerify/1.0}"
: "${AIC_WARMUP_ATTEMPTS:=48}"
: "${AIC_WARMUP_INTERVAL:=10}"

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

curl_json() {
  curl --fail --silent --show-error --location \
    --user-agent "$UA" \
    --header "Accept: application/json" \
    --max-time 30 \
    "$@"
}

echo "Waiting for warm-up at $AIC_BACKEND_URL (up to $((AIC_WARMUP_ATTEMPTS * AIC_WARMUP_INTERVAL))s)"
ready=0
for _ in $(seq 1 "$AIC_WARMUP_ATTEMPTS"); do
  if curl_json "$AIC_BACKEND_URL/health" > "$tmp/health.json"; then
    state="$(jq -r '.warmup.state // "unknown"' "$tmp/health.json")"
    echo "  warmup.state=$state"
    if [ "$state" = "ready" ]; then
      ready=1
      break
    fi
    # A restart that dies during warm-up would otherwise burn the full window.
    if [ "$state" = "failed" ]; then
      cat "$tmp/health.json"
      echo "Warm-up failed after the index sync" >&2
      exit 1
    fi
  fi
  sleep "$AIC_WARMUP_INTERVAL"
done

if [ "$ready" != "1" ]; then
  echo "API did not reach warmup.state=ready in time" >&2
  cat "$tmp/health.json" 2>/dev/null || true
  exit 1
fi

curl_json "$AIC_BACKEND_URL/status" > "$tmp/status.json"

echo "== index set now serving =="
jq '{files, vectors, keyframes, videos, relpath_map, active_models}' "$tmp/status.json"

# Verified against the live deployment on 2026-08-18:
#   vectors.beit3 = keyframes = relpath_map = 868524
#   vectors.clip  = 105817     — the CLIP index covers a subset by design,
#                                so it is bounded, not equal.
jq -e '
  (.files | to_entries | all(.[]; .value == true))
  and (.keyframes > 0)
  and (.videos > 0)
  and (.vectors.beit3 == .keyframes)
  and (.relpath_map == .keyframes)
  and (.vectors.clip > 0)
  and (.vectors.clip <= .keyframes)
' "$tmp/status.json" > /dev/null || {
  echo "Index set is inconsistent — the index, mapping and metadata are not from the same run" >&2
  jq '{vectors, keyframes, relpath_map, files}' "$tmp/status.json" >&2
  exit 1
}

if [ -n "${AIC_EXPECT_KEYFRAMES:-}" ]; then
  actual="$(jq -r '.keyframes' "$tmp/status.json")"
  echo "keyframes=$actual expected=$AIC_EXPECT_KEYFRAMES"
  if [ "$actual" != "$AIC_EXPECT_KEYFRAMES" ]; then
    echo "Keyframe count is not what the operator expected" >&2
    exit 1
  fi
fi

# Consistent counts still would not prove the index answers queries, so run one.
curl --fail --silent --show-error --location \
  --user-agent "$UA" \
  --header "Accept: application/json" \
  --header "Content-Type: application/json" \
  --max-time 120 \
  --data "{\"query\":\"${AIC_SMOKE_QUERY:-orange news graphics}\",\"limit\":10,\"top_m\":100,\"use_rerank\":true}" \
  "$AIC_BACKEND_URL/ensemble-search" > "$tmp/search.json"

jq -e '.returned_results > 0 and (.results | length > 0)' "$tmp/search.json" > /dev/null

echo "Index verification passed"
