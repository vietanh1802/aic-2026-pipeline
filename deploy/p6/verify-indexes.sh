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

# Counts prove the three files agree with each other. They do not prove the
# process picked up the new generation: a rebuild that keeps the same keyframes
# reports the same counts, and the counts come from module globals, so a
# container that never restarted looks identical to one that did. The
# fingerprints below are what separates the two.
echo "== index files the process is serving =="
jq '.index_files' "$tmp/status.json"

stale="$(jq -r '(.stale_files // []) | join(", ")' "$tmp/status.json")"
if [ -n "$stale" ]; then
  echo "The files on disk moved but the process did not reload them: $stale" >&2
  echo "The API is still answering from the previous index set. Restart it." >&2
  exit 1
fi

# With AIC_INDEX_S3_URI set, go one step further and check that what the process
# holds in memory is byte-for-byte what S3 publishes. `aws s3 sync` stamps the
# object's LastModified onto the file it writes, so size and mtime together
# identify the S3 generation without hashing 15 GB.
if [ -n "${AIC_INDEX_S3_URI:-}" ] && command -v aws > /dev/null 2>&1; then
  s3="${AIC_INDEX_S3_URI#s3://}"
  s3_prefix="${s3#*/}"
  s3_bucket="${s3%%/*}"
  echo "== comparing the loaded set against s3://$s3_bucket/$s3_prefix =="

  mismatch=0
  # tr -d is not decoration. jq built for Windows ends every line with CRLF, so
  # word splitting leaves a trailing CR on each name but the last, and every
  # head-object built from those names asks S3 for a key that does not exist.
  # The workflow runs on Linux and never sees this; an operator running the same
  # script from Git Bash does.
  for name in $(jq -r '.index_files | keys[]' "$tmp/status.json" | tr -d '\r'); do
    loaded_bytes="$(jq -r --arg n "$name" '.index_files[$n].loaded.bytes // "none"' "$tmp/status.json")"
    loaded_mtime="$(jq -r --arg n "$name" '.index_files[$n].loaded.mtime // "none"' "$tmp/status.json")"

    # Any failure here is a real answer, not a reason to skip. A missing key
    # means S3 does not hold what the API loaded; AccessDenied means the check
    # never ran. Both used to pass silently, which is worse than not checking.
    if ! head="$(aws s3api head-object \
      --bucket "$s3_bucket" --key "$s3_prefix$name" \
      --query '{bytes:ContentLength,mtime:LastModified}' \
      --output json 2>"$tmp/head.err")"; then
      echo "  $name: cannot read s3://$s3_bucket/$s3_prefix$name" >&2
      sed 's/^/      /' "$tmp/head.err" >&2
      mismatch=1
      continue
    fi
    s3_bytes="$(printf '%s' "$head" | jq -r '.bytes')"
    s3_mtime="$(printf '%s' "$head" | jq -r '.mtime')"

    if [ "$loaded_bytes" = "$s3_bytes" ] && [ "$loaded_mtime" = "$s3_mtime" ]; then
      echo "  $name: serving the S3 copy ($s3_bytes bytes, $s3_mtime)"
    else
      echo "  $name: MISMATCH loaded=${loaded_bytes}B@${loaded_mtime} s3=${s3_bytes}B@${s3_mtime}" >&2
      mismatch=1
    fi
  done

  if [ "$mismatch" != "0" ]; then
    echo "Could not confirm the running API is serving the index set published to S3" >&2
    exit 1
  fi
fi

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
