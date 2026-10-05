#!/bin/bash
# Slot 3: final_table on A and B, once, after the selection was frozen and committed.
# Usage (root): SHA=<commit> setsid nohup /root/run_slot3.sh > /root/run_slot3.log 2>&1 < /dev/null &
exec 9>/root/run_suite.lock; flock -n 9 || { echo "already running"; exit 1; }
: "${SHA:?set SHA}"
C="docker compose -f /opt/aic/app/docker-compose.yml"
OUT=/opt/aic/data/ablation_out
SRC=/opt/aic/ablation/src-$SHA
ALL=round1-v3,round2-v2,round3-v2,final-v2
log() { echo "$(date +%T) $*"; }
trap 'log "trap: start api"; $C start api >/dev/null 2>&1' EXIT

log "0: code $SHA"
mkdir -p $SRC $OUT
aws s3 cp --only-show-errors s3://aic2026-artifacts/ablation/aic-ablation-$SHA.tar.gz /opt/aic/ablation/ || { log "ABORT: archive download"; exit 1; }
tar xzf /opt/aic/ablation/aic-ablation-$SHA.tar.gz -C $SRC
grep -q '"winner": "R11S' $SRC/backend/app/evaluation/frozen_selection.json || { log "ABORT: frozen selection missing"; exit 1; }

log "3: stop api"; $C stop api; docker rm -f ablation-run >/dev/null 2>&1

log "4: suite final_table on A and B"
$C run --rm --no-deps --name ablation-run -v $SRC:/tmp/ablation -e AIC_COMMIT=$SHA -e AIC_DB_PATH=$OUT/scratch.db api \
  sh -c "python /tmp/ablation/scripts/run_ablation_suite.py --preset final_table --datasets $ALL --out $OUT > $OUT/final_table.out 2>&1"
log "final_table exit $?"
R1=$(ls -1dt $OUT/20*/ | head -n 1 | xargs basename); log "final_table folder $R1"

log "6: start api"; $C start api

log "7: pack and upload"
cd $OUT && tar czf /tmp/slot3-$SHA.tgz --exclude=scratch.db $R1 final_table.out
aws s3 cp --only-show-errors /tmp/slot3-$SHA.tgz s3://aic2026-artifacts/ablation/out/ablation-out-slot3-$SHA.tgz
log "ALL DONE final_table=$R1"
