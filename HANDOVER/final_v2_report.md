# final-v2 run, Expand outputs, and the component table (Tasks 1 and 3)

Branch `ablation/final-v2`. All numbers CONFIRMED from the run folders below unless tagged INFERRED.
Benchmark A = 86 queries (round1-v3, round2-v2, round3-v2), Benchmark B = 28 queries of `final-v2`. Video level.

## Runs (S3 bucket `aic2026-artifacts`)

| Slot | Preset | Datasets | Commit | Run folder | S3 |
|---|---|---|---|---|---|
| 1 | `core3` (39 configs, 156 runs) | A and B | `f976e70` | `20261005-072438` | `ablation/out/ablation-out-slot12-f976e70....tgz` |
| 2 | `rerank_diag` (24 configs, 72 runs) | A only | `f976e70` | `20261005-075632` | same archive |
| 3 | `final_table` (7 configs, 28 runs) | A and B | `808faa1` | `20261005-081235` | `ablation/out/ablation-out-slot3-808faa1....tgz` |

Every run: 0 failed; the equivalence gate passed 18 of 18 lines (17 old + "shipped rerank variant == ensemble_search").
Expand: `check_expand.py` OK, 25 new texts for final-v2 fetched from Gemini (145 needed, 120 cached), 0 failed. Plain
translation for the 25 texts fetched on the lead's PC and committed in `translate_gtx.jsonl` before the archive.

Consistency checks: on A every core2 arm reproduces run 2 exactly (C01 30.2 / 61.6 / 74.4 / 0.453, C08 39.5 / 65.1 /
70.9 / 0.512); the TRAKE arms T01 and T02 reproduce run 2 (TRAKE queries are unchanged in final-v2); F01 equals R11S and
F02 equals C08 on A.

## Component ablation table (`paper_tables/components.tex`, run `20261005-081235`)

| Row | A H@1 | A R@5 | A R@10 | A MRR | B H@1 | B R@5 | B R@10 | B MRR |
|---|---|---|---|---|---|---|---|---|
| Full system (3 encoders, corrected rerank R11S, Expand sentence) | 41.9 | 64.0 | 73.3 | 0.524 | **53.6** | 75.0 | 82.1 | **0.624** |
| Without rerank | 39.5 | 65.1 | 70.9 | 0.512 | 46.4 | 75.0 | 85.7 | 0.598 |
| Plain translation instead of Expand | 34.9 | 60.5 | 73.3 | 0.476 | 39.3 | 67.9 | 75.0 | 0.510 |
| Without BEiT-3 | **45.3** | 65.1 | 70.9 | **0.549** | 42.9 | 71.4 | 82.1 | 0.580 |
| Without OpenCLIP | 40.7 | 59.3 | 69.8 | 0.507 | 42.9 | 71.4 | 75.0 | 0.565 |
| Without SigLIP2 | 31.4 | 51.2 | 64.0 | 0.414 | 39.3 | 67.9 | 67.9 | 0.505 |
| Expand keywords instead of the sentence | 38.4 | 61.6 | 68.6 | 0.490 | 50.0 | 75.0 | 78.6 | 0.588 |

On B the full system has the best H@1 and MRR of every row. On A, removing BEiT-3 is better than the full system (45.3
vs 41.9): the row stays in the table as the brief requires. Paired Hit@1 of the full system against: no rerank A +2/-0,
B +2/-0; plain translation A +9/-3, B +6/-2; keywords A +14/-11, B +2/-1. With 86 and 28 queries none of these is
significant after Holm adjustment (`paper_tables/components_stats.csv`: exact McNemar on Hit@1 with Holm over the 12
comparisons, paired bootstrap 95% interval of the MRR difference, 10,000 resamples). The one difference whose MRR interval
excludes 0 on both benchmarks is removing SigLIP2 (A +0.110 [+0.052, +0.171], B +0.119 [+0.032, +0.221]). Rerank: A
+0.012 [-0.005, +0.033], B +0.026 [-0.016, +0.085]. Plain translation: A +0.047 [-0.013, +0.109], B +0.115 [-0.023,
+0.251].

## Expand: the two outputs and plain translation (rerank off, core3 `20261005-072438`)

| Encoders | Text | A H@1 | A R@10 | A MRR | B H@1 | B R@10 | B MRR |
|---|---|---|---|---|---|---|---|
| All three | Expand sentence (C08) | 39.5 | 70.9 | 0.512 | 46.4 | 85.7 | 0.598 |
| All three | Expand keywords (C29) | 38.4 | 68.6 | 0.492 | 50.0 | 78.6 | 0.597 |
| All three | Plain translation (C22) | 31.4 | 72.1 | 0.451 | 39.3 | 75.0 | 0.510 |
| BEiT-3 | sentence / keywords / plain | 32.6 / 30.2 / 26.7 | | | 32.1 / 35.7 / 42.9 | | |
| OpenCLIP | sentence / keywords / plain | 29.1 / 26.7 / 30.2 | | | 32.1 / 46.4 / 39.3 | | |
| SigLIP2 | sentence / keywords / plain | 39.5 / 41.9 / 31.4 | | | 46.4 / 35.7 / 32.1 | | |

Expand (either output) beats plain translation on H@1 and MRR with all three encoders on both benchmarks. Sentence
against keywords is mixed: the sentence wins on A, the keywords on B H@1, the sentence on B R@10. The choice was made on A
(sentence). Mean keyword text is 11.7 words against 37.3 for the sentence (from the recorded core2 texts).

TRAKE (8 queries, `trake.tex`): TRAKE-N 50.0 H@1 on Expand sentence and on plain translation; whole-description search
with rerank off 12.5 (sentence), 0.0 (plain), 37.5 (keywords). Eight queries decide it: describe, do not claim.

## Method-section numbers (`paper_tables/corpus.tex`, from `analysis/T1a_corpus.md`)

| Group | Videos | Hours (lower bound) | Keyframes | Shots | KF/hour | Gap (s) |
|---|---|---|---|---|---|---|
| L | 873 | 130.6 | 360,531 | 96,746 | 2,761 | 1.30 |
| M | 304 | 99.5 | 336,876 | 97,434 | 3,386 | 1.06 |
| N | 298 | 48.3 | 201,221 | 298 | 4,166 | 0.86 |
| S | 12 | 46.6 | 92,841 | 9,887 | 1,992 | 1.81 |
| Total | 1,487 | 325.0 | 991,469 | 204,365 | 3,051 | 1.18 |

Replaces the draft's 1,480 videos, 323.8 h, 983,931 keyframes, 202,114 shots, M 297 / 95,183 / 329,338. Stored neighbour
lists: 727,574 of 991,469 keyframes (73.4%); the 263,895 without are all L. ASR: the deployed BM25 index has 18,489
documents (18,546 windows built; the difference was not traced).

## Truncation on final-v2 (`analysis/T5b_text_length.md`, `T5c_truncated_vs_not.md`)

Share of queries over the encoder's context (Benchmark B): Expand sentence OpenCLIP 7.1%, SigLIP2 14.3%; plain
translation 21.4% and 25.0%; Expand keywords 0%. Final-v1 was 17.9% / 50.0% (Expand) and 85.7% / 96.4% (plain).

## Error labelling

`analysis/error_labeling_sheet.xlsx` (73 rows): every query the FULL SYSTEM (F01) does not rank first, A and B, with the
top-5 videos and automatic labels. To fill by hand: `error_codes` (D1 to D9, `taxonomy.csv`), `small_detail_query`,
`text_cue_present`, `label_doubt`; then `python scripts/aggregate_error_labels.py <filled csv> --run-dir 20261005-081235`.

## Not done (time)

- Prompt variants of Task 3.5 (no new Gemini prompt was tried) and the 10 example pairs of Task 3.4.
- Reading `app.db` for the live settings (Task 2.1); H2 as an L-only re-run.
- A production patch for the rerank fix (`docs/proposed_patches/`).
- Filling the error labels (needs a person).

## Commands

```
# PC
python scripts/prefetch_text_cache.py --preset core3 --datasets round1-v3,round2-v2,round3-v2,final-v2
git archive --format=tar.gz -o aic-ablation-<sha>.tar.gz HEAD; aws s3 cp ... s3://aic2026-artifacts/ablation/
# EC2 (root): /root/run_slot12.sh (core3 A+B, then rerank_diag A only), then /root/run_slot3.sh (final_table A+B)
# PC
python scripts/select_rerank_variant.py --run-dir 20261005-075632
python scripts/make_paper_tables.py --run-dir 20261005-072438 --final-dir 20261005-081235
```

The wrapper scripts are copies of Brief 1 section 9.3 (flock, API restarted by a trap) with the two suites of slots 1 and
2 in one API-down window; their text is in `HANDOVER/run_slot12.sh` and `HANDOVER/run_slot3.sh`.
