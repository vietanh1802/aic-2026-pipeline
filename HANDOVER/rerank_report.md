# Rerank report (Task 2)

Branch `ablation/final-v2`. Tags: CONFIRMED = read in code or measured from a file or a run; INFERRED = reasoned.

## 1. Suspects H1 to H9

| # | Suspect | Status | Evidence |
|---|---|---|---|
| H1 | neighbour id or vector mapping defect | **REFUTED** (CONFIRMED by measurement) | Read-only check on the host, `/opt/aic/indexes` (v002), 2026-10-05: every stored neighbour id of all 727,574 linked keyframes resolves to a frame of the same video at frame-order offsets -3..-1, +1..+3 only; 0 missing, 0 in another video. FAISS id to frame name agrees for all 991,469 frames in `clip_mapping.json` and `beit3_mapping.json` (SigLIP2 is looked up by name). Script and output: `/opt/aic/data/ablation_out/diag/h1_neighbors.py`, `h1.out`. |
| H8 | index version (competition on v001) | **REFUTED for the rerank** (CONFIRMED) | Same check on `/opt/aic/indexes_backup_v001_20261001`: the neighbour lists of the 720,036 linked frames common to both versions name exactly the same frames. v002 only adds M06_V024 to V030 (7,538 frames, `merge_info.json`). |
| H4 | scale mismatch between stored-link and fallback videos | **CONFIRMED (mechanism read, effect measured)** | Shipped rerank: linked videos sum 6 neighbours without self, fallback videos (263,895 L frames, 73% of L) sum 5 frames with self, no normalisation, then one scale (`s_max`). Run 2 (`20261004-095339`, Benchmark A, 81 KIS/QA queries, 17 reference videos linked, 64 fallback): the rank-1 video is a LINKED video in 76/81 queries for BEiT-3 with rerank vs 29/81 without; all three encoders 44/81 vs 32/81; OpenCLIP 68 vs 39; SigLIP2 55 vs 34. Rerank pushes linked videos (all of M, N, S and 251 L videos) to the top regardless of the query. |
| H7 | difference from the source method | **CONFIRMED (read)** | Tran et al., CVPRW 2025 (arXiv 2504.08384), Sec. 3.2.1 and 3.3, Alg. 2: 4 evenly spaced keyframes per shot after TransNetV2, near-duplicates (cos > 0.9) removed within a shot; neighbourhood motivated as "the areas surrounding a keyframe ... within a shot"; the aggregate is a sum; GetNeighbors is not specified numerically; no quantitative rerank ablation (Fig. 5 is qualitative). Ours: up to 40 keyframes per shot, no dedup, +-3 keyframes regardless of shot (N is one "shot" per video). Variants R05, R10 to R12 follow the source's "within a shot". |
| H2 | collection mismatch (L only in the preliminary rounds) | partly addressed by H4 | Rerank on raises the rank-1 share of M videos on A (all three encoders 14 vs 8 of 81; BEiT-3 30 vs 10), but N and S barely move (N 1 vs 1). The excess goes to LINKED videos, L or M, which H4 explains. An L-only re-run was not done (no time). |
| H3 | neighbourhood by keyframe count crosses shots | tested by R05, R06, R07, R10 to R12 | see section 3 |
| H5 | query text (operators typed short keywords) | tested in part | the Expand keyword text (`expand_keywords`) is the short-text condition; see section 3 |
| H6 | metric | not re-examined | the interval-level score also dropped in run 1 (0.477 vs 0.514), per Brief 1 |
| H9 | harness defect | **REFUTED** (CONFIRMED) | the equivalence gate passed 18/18 on the real indexes in the core3 run, including the new line "shipped rerank variant == ensemble_search" |

## 2. Live settings (2.1)

Not done: no time to read `app.db`. Frontend default at competition time: `useRerank: true`, `topM 50`, `resultLimit 100`
(pinned by `test_default_run_config_equals_production_defaults`).

## 3. Development grid on Benchmark A (CONFIRMED, run `20261005-075632`, commit `f976e70`, A only)

All three encoders, 86 queries, video level. Every row of the declared grid, nothing dropped. Selection by
`scripts/select_rerank_variant.py` (rule committed in `f976e70` before the run).

| Config | H@1 | R@5 | R@10 | MRR | | Config | H@1 | R@5 | R@10 | MRR |
|---|---|---|---|---|---|---|---|---|---|---|
| R01S off | 39.5 | 65.1 | 70.9 | 0.512 | | R01K off | 38.4 | 61.6 | 68.6 | 0.492 |
| R02S shipped | 30.2 | 61.6 | 74.4 | 0.453 | | R02K shipped | 30.2 | 61.6 | 68.6 | 0.440 |
| R03S stored-style, sum | 37.2 | 66.3 | 74.4 | 0.499 | | R03K | 34.9 | 64.0 | 72.1 | 0.474 |
| R04S stored-style, mean | 37.2 | 66.3 | 74.4 | 0.497 | | R04K | 34.9 | 64.0 | 72.1 | 0.474 |
| R05S same shot, mean | 38.4 | 64.0 | 72.1 | 0.502 | | R05K | 36.0 | 58.1 | 67.4 | 0.477 |
| R06S 2 s window, mean | 40.7 | 68.6 | 73.3 | 0.522 | | R06K | 33.7 | 62.8 | 69.8 | 0.465 |
| R07S 3 s window, mean | 40.7 | 67.4 | 73.3 | 0.519 | | R07K | 36.0 | 62.8 | 68.6 | 0.483 |
| R08S own + 0.5 mean stored | 39.5 | 66.3 | 72.1 | 0.511 | | R08K | 36.0 | 62.8 | 69.8 | 0.494 |
| R09S own + 1.0 mean stored | 37.2 | 65.1 | 73.3 | 0.499 | | R09K | 36.0 | 64.0 | 70.9 | 0.493 |
| R10S same shot, sum | 32.6 | 66.3 | 70.9 | 0.464 | | R10K | 30.2 | 60.5 | 69.8 | 0.440 |
| **R11S own + 0.5 mean same shot** | **41.9** | 64.0 | 73.3 | **0.524** | | R11K | 38.4 | 61.6 | 68.6 | 0.490 |
| R12S own + 1.0 mean same shot | 40.7 | 64.0 | 72.1 | 0.517 | | R12K | 37.2 | 61.6 | 67.4 | 0.486 |

Consistency: R01S equals core2/core3 C08 and R02S equals C01 to the last digit.

Step 1 (text): R01S 39.5 > R01K 38.4, so the Expand sentence. Step 2: R11S, the frame's own cosine plus 0.5 times the
mean cosine of its neighbours at offsets -3..+3 within the same shot. Frozen in `808faa1`
(`backend/app/evaluation/frozen_selection.json`) before any B number of this variant existed.

Reading (INFERRED): every variant that removes the 6-vs-5 sum (any mean, or own score kept) recovers most of the loss;
the sum within a shot (R10, the closest to the source paper's Alg. 2) does not, because a sum still favours frames with
more same-shot neighbours. The margin of the winner over rerank off is small: 2 queries of 86.

## 4. Frozen selection on Benchmark B, once (CONFIRMED, run `20261005-081235`, commit `808faa1`, preset `final_table`)

| | A H@1 | A R@5 | A R@10 | A MRR | B H@1 | B R@5 | B R@10 | B MRR |
|---|---|---|---|---|---|---|---|---|
| F01 full system (R11S) | 41.9 | 64.0 | 73.3 | 0.524 | 53.6 | 75.0 | 82.1 | 0.624 |
| F02 without rerank | 39.5 | 65.1 | 70.9 | 0.512 | 46.4 | 75.0 | 85.7 | 0.598 |
| shipped rerank (core3 C01) | 30.2 | 61.6 | 74.4 | 0.453 | 46.4 | 71.4 | 82.1 | 0.575 |

Paired Hit@1, F01 against F02: A 2 gained, 0 lost; B 2 gained, 0 lost (exact two-sided McNemar p = 0.5 each).
The direction holds on the held-out set, but neither difference is significant with 86 and 28 queries.

## 5. Statement for the lead

(a)/(b): a defect in the shipped rerank was found (H4: two neighbour formulas with different summand counts on one
scale; with BEiT-3 the rank-1 video is a linked video in 76 of 81 A queries against 17 references). The corrected
variant chosen on A (R11S) beats rerank off on A (41.9 vs 39.5 H@1) and holds on B (53.6 vs 46.4), by 2 queries on each.
It is an evaluation-side re-implementation: the competition system ran the shipped rerank (C01), and the paper must say
so. Recall@10 is lower with the corrected rerank on B (82.1 vs 85.7). Proposed production patch: not written yet.
