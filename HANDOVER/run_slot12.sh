#!/bin/bash
# Slot 1 + 2 in one API-down window: core3 on A and B, then rerank_diag on A ONLY.
# Usage (root): SHA=<commit> setsid nohup /root/run_slot12.sh > /root/run_slot12.log 2>&1 < /dev/null &
exec 9>/root/run_suite.lock; flock -n 9 || { echo "already running"; exit 1; }
: "${SHA:?set SHA}"
C="docker compose -f /opt/aic/app/docker-compose.yml"
OUT=/opt/aic/data/ablation_out
SRC=/opt/aic/ablation/src-$SHA
A_ONLY=round1-v3,round2-v2,round3-v2
ALL=round1-v3,round2-v2,round3-v2,final-v2
log() { echo "$(date +%T) $*"; }
trap 'log "trap: start api"; $C start api >/dev/null 2>&1' EXIT

log "0: code $SHA"
mkdir -p $SRC $OUT
aws s3 cp --only-show-errors s3://aic2026-artifacts/ablation/aic-ablation-$SHA.tar.gz /opt/aic/ablation/ || { log "ABORT: archive download"; exit 1; }
tar xzf /opt/aic/ablation/aic-ablation-$SHA.tar.gz -C $SRC
CID=$($C ps -q api)
docker exec $CID rm -rf /tmp/ablation
docker cp $SRC $CID:/tmp/ablation

log "1: Gemini check"
docker exec $CID python /tmp/ablation/scripts/check_expand.py > $OUT/check_expand.out 2>&1
tail -n 2 $OUT/check_expand.out
grep -q "OK: Gemini answered" $OUT/check_expand.out || { log "ABORT: Gemini check failed, API left running"; exit 1; }

log "2: fetch Expand texts for core3 (API up)"
ok=0
for t in 1 2 3; do
  docker exec -e AIC_INDEX_DIR=/opt/aic/indexes $CID sh -c "python /tmp/ablation/scripts/prefetch_text_cache.py --preset core3 --policy expand_gemini --datasets $ALL --out $OUT/text_cache.jsonl >> $OUT/prefetch.out 2>&1" && { ok=1; break; }
  log "prefetch try $t failed"; sleep 30
done
[ $ok = 1 ] || { log "ABORT: prefetch, API left running"; tail -n 20 $OUT/prefetch.out; exit 1; }
tail -n 2 $OUT/prefetch.out

log "3: stop api"; $C stop api; docker rm -f ablation-run >/dev/null 2>&1

log "4: suite core3 on A and B"
$C run --rm --no-deps --name ablation-run -v $SRC:/tmp/ablation -e AIC_COMMIT=$SHA -e AIC_DB_PATH=$OUT/scratch.db api \
  sh -c "python /tmp/ablation/scripts/run_ablation_suite.py --preset core3 --datasets $ALL --out $OUT > $OUT/core3.out 2>&1"
log "core3 exit $?"
R1=$(ls -1dt $OUT/20*/ | head -n 1 | xargs basename); log "core3 folder $R1"

log "5: suite rerank_diag on A only"
docker rm -f ablation-run >/dev/null 2>&1
$C run --rm --no-deps --name ablation-run -v $SRC:/tmp/ablation -e AIC_COMMIT=$SHA -e AIC_DB_PATH=$OUT/scratch.db api \
  sh -c "python /tmp/ablation/scripts/run_ablation_suite.py --preset rerank_diag --datasets $A_ONLY --out $OUT > $OUT/rerank_diag.out 2>&1"
log "rerank_diag exit $?"
R2=$(ls -1dt $OUT/20*/ | head -n 1 | xargs basename); log "rerank_diag folder $R2"

log "6: start api"; $C start api

log "7: pack and upload"
cd $OUT && tar czf /tmp/slot12-$SHA.tgz --exclude=scratch.db $R1 $R2 text_cache.jsonl core3.out rerank_diag.out prefetch.out check_expand.out
aws s3 cp --only-show-errors /tmp/slot12-$SHA.tgz s3://aic2026-artifacts/ablation/out/ablation-out-slot12-$SHA.tgz
log "ALL DONE core3=$R1 rerank_diag=$R2"
