# Rerank diagnosis: what the neighbour rerank computes, and what the stored results can say about it

Status: analysis only. Nothing here changes shipped behaviour and no run was repeated. Tags: CONFIRMED = read in code
or computed from a file in this checkout's environment; INFERRED = reasoned, not measured. Line numbers refer to
`backend/app/preprocess.py` at the branch base (`origin/staging` e9a7e61).

## 1. How a frame's rerank score is computed (CONFIRMED, read)

`rerank_one_model` (L844 to 880) is applied to the top-m = 50 hits of ONE model. For each hit:

- the neighbour ids come from `_neighbor_faiss_ids(meta, model)` (L804 to 841);
- `compute_score` (L857) is `dot(query_embedding, index.reconstruct(neighbour_id))`;
- the new score is the **sum** over the neighbours (L873 to 877). It is not a mean: nothing divides by the number of
  neighbours used (`n_neighbors` is stored on the hit but not used again);
- the frame's own cosine is **replaced**: the module comment at L799 says the total "only adds the neighbours, NOT its
  own score".

Which neighbours:

| | stored links (`neighbors_clip` non-empty) | fallback (`neighbors_clip` empty) |
|---|---|---|
| source | the stored CLIP ids (for BEiT-3 and SigLIP2 each id is mapped through `_clipid2meta` to that model's own id; ones the model did not index are skipped) | the video's frames in `frame_idx` order, window `pos - 2 .. pos + 2` (L839) |
| self | **excluded** (0 of 96,636 stored lists contain the frame itself, below) | **included** (the window is centred on the frame) |
| count | 6 in the interior (offsets -3..-1 and +1..+3), 3 to 5 near the ends of a video (below) | 5 in the interior, fewer at the ends |
| normalisation | none | none |

So the two groups are scored by **two different formulas** (neighbours only against neighbours plus itself) with
**different summand counts** (6 against 5). In `_merge_ensemble` (L904 to 929) each model's list is then divided by its
own maximum (`s_max`, L918) and weighted, so a video with stored links and a video without are placed on one scale
inside the same ranking even though their raw sums are not comparable. CONFIRMED by reading; the size of the effect is
not measured, because the rerank sums and `n_neighbors` are not stored (a stored route keeps the pre-rerank cosine and
the post-rerank rank, `_merge_ensemble` L926).

## 2. Which videos have stored links (CONFIRMED on the local Batch 1 metadata, 360,531 L keyframes)

Computed with `scripts/dump_corpus_features.py` (now writes `n_with_links`, `share_with_links` per video) and a direct
read of `keyframe_metadata.json`:

- 96,636 keyframes have `neighbors_clip`; 263,895 do not (the number the design doc measured on the host);
- link status is a property of the **video**: 251 videos have it on every keyframe, 622 on none, **0 mixed**. By series:
  L25 has it for all 88 videos; L21 and L30 for none;
- list lengths: 6 for 95,130 frames, 3, 4 and 5 for 502 each (the ends of the 251 videos);
- offsets in frame order: only -3, -2, -1, +1, +2, +3 occur; self never.

The reference videos of the seeds (local metadata, which has L only): benchmark A (86 queries) has **18 with stored links
and 68 without**; benchmark B has 11 L reference videos, **1 with and 10 without**, plus 17 non-L (M 13, N 2, S 2).
M, N and S are described as having links on every frame in the design doc (section 0.3, from the host); that was NOT
measured here.

## 3. What T4b can and cannot say

`tables_rerank.t4b_rerank_by_links` (table T4b, needs `--features` from the new dump) compares each rerank-on arm with
its rerank-off arm for the L reference videos, split by link status of the reference video, at video level (Hit@1, R@10,
MRR, gained and lost counts) and interval level (mean R-Score), plus the mean number of distinct videos and the share of
frames from linked videos in the stored top 100.

It can say whether the on-minus-off difference is different for the two groups. It cannot say:

- **why.** Link status follows the video series. The two groups also differ in batch, content and frame density, and no
  arm applies one neighbourhood to both. If rerank hurts only the no-links group that is consistent with the fallback
  being the problem, and equally consistent with something else that differs between the series;
- anything precise from the "stored links" cell: n = 18 queries in A and 1 in B, so a difference of a few queries is
  noise;
- anything about M, N and S: the one place they appear (B) has 17 queries and, in this checkout, no link measurement.

Hypothesis (c) of the task ("the L result comes from the fallback neighbourhood, not from reranking itself") is **not
testable** with the stored data. What the data allow: whether the harm is concentrated in the no-links group (T4b rows
"fallback") and whether the stored-links group, with the same code but a different neighbourhood, behaves like the M, N
and S videos (B).

## 4. What would test it (not done: it needs a rerun)

An evaluation-side re-implementation of the rerank (the same approach as `shared_search`'s after-fusion arm, no change to
`preprocess.py`) with the neighbourhood as a parameter: (a) the stored definition for every video, derived from the frame
order (offsets -3..-1, +1..+3, self excluded); (b) the fallback definition for every video; (c) the mean instead of the
sum. Run on the 86 L queries, with the per-frame sum and `n_neighbors` stored so the scale can be read. Proposed patch
for the shipped behaviour: `docs/proposed_patches/rerank-one-neighbourhood.md`.
