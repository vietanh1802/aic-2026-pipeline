# Rerank and Expand-output selection rule (declared before the development run)

Committed before any `rerank_diag` run exists. The grid, the rule and the script below are fixed by this commit;
nothing is added to the grid after a result is seen, and Benchmark B is not used for any choice.

## What is chosen

1. **Which Expand output the full system searches**: the rewritten sentence (`search_query`, text policy
   `expand_gemini`) or the keyword list (`check_units` joined by ", ", text policy `expand_keywords`). Both come
   from the same recorded Gemini answer, so this choice adds no LLM call.
2. **Which neighbour rerank the full system uses**, among R01 to R12 below, on the chosen text.

## The grid (preset `rerank_diag`, all three encoders, top_m 50, top_k 100)

Every row runs on both Expand outputs (suffix S = sentence, K = keywords): 24 configurations.

| Code | Rerank | Why it is in the grid |
|---|---|---|
| R01 | off | reference |
| R02 | shipped (`preprocess.rerank_one_model`, re-implemented; equality checked on the real index) | reference |
| R03 | offsets -3..-1, +1..+3 for every video, self excluded, sum | one neighbourhood for all videos (H4) |
| R04 | as R03, mean | sum vs mean (H4) |
| R05 | as R03 but only frames of the same shot (`scene_id`), mean | source method: "within a shot" (H3, H7) |
| R06 | every frame within 2 s, self excluded, mean | window in time, not in keyframe count (H3) |
| R07 | every frame within 3 s, self excluded, mean | as R06 |
| R08 | own cosine + 0.5 x mean of R03's neighbours | the shipped rerank discards the frame's own score |
| R09 | own cosine + 1.0 x mean of R03's neighbours | as R08 |
| R10 | same-shot neighbours, sum, self excluded | closest to Tran et al. (CVPRW 2025) Alg. 2 + Sec. 3.3 |
| R11 | own cosine + 0.5 x mean of same-shot neighbours | R08 with the source method's neighbourhood |
| R12 | own cosine + 1.0 x mean of same-shot neighbours | as R11 |

With a mean and no usable neighbour (a shot with one keyframe), the frame's own cosine stands in for the mean.

Rows R10 to R12 were chosen from section 2.4 of Brief 2 (the source paper, read on 2026-10-05: 4 keyframes per shot,
neighbourhood motivated as "within a shot", sum, no numeric ablation) and the corpus check of the same day (H1: stored
neighbour ids are correct, v001 and v002 links identical; so no id-fix row is needed).

## The rule (applied by `scripts/select_rerank_variant.py`, no human judgement)

Data: Benchmark A only (`round1-v3`, `round2-v2`, `round3-v2` pooled, 86 queries), video level, `flags = all`.
The script refuses a run folder that contains any Benchmark B row, or any grid row with n != 86 or a failure.

1. Text: R01S against R01K. Higher Hit@1 wins; tie: higher MRR; tie: higher Recall@10; tie: the sentence.
2. Rerank: R01 to R12 on the winning text. Same order of criteria; a full tie goes to the lower code (R01 first).
3. The winner's RunConfig is written to `backend/app/evaluation/frozen_selection.json`, which is committed before
   preset `final_table` runs. `final_table` is then run once on Benchmarks A and B.

If no variant beats R01 on A, the frozen full system is rerank off, and the lead is told at once so the paper
framing can be adjusted. Every grid row is reported, not only the winner.
