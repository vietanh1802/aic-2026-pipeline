# Proposed patch (NOT applied): one neighbourhood definition for the neighbour rerank

File: `backend/app/preprocess.py`, `_neighbor_faiss_ids` (L804 to 841). Production code; the ablation branch must not edit
it, so this is a proposal with a test plan, not a change.

## The inconsistency (CONFIRMED by reading, see docs/rerank-diagnosis.md)

`rerank_one_model` sums the query similarity over a frame's neighbours. Which neighbours depends on the video:

| video | neighbours | summands | self |
|---|---|---|---|
| stored `neighbors_clip` (251 of 873 L videos, and M, N, S by the design doc) | offsets -3..-1, +1..+3 | 6 | excluded |
| empty `neighbors_clip` (622 L videos; all of benchmark A except 18 queries) | offsets -2..+2 (L839) | 5 | included |

Both are plain sums with no normalisation, and `_merge_ensemble` puts both groups on one scale (division by the model's
maximum). Which of the two is better is not known; what is known is that they are not the same function.

## Smallest change that makes them the same

Make the fallback reproduce the stored definition exactly (the stored lists are offsets -3..+3 without self):

```python
-    lo, hi = max(0, pos - 2), min(len(frames), pos + 3)
-    out = [_fid_of(frames[i], id_field) for i in range(lo, hi)]   # [siglip2]
+    lo, hi = max(0, pos - 3), min(len(frames), pos + 4)
+    out = [_fid_of(frames[i], id_field) for i in range(lo, hi) if i != pos]   # [siglip2]
```

Alternatives: ignore `neighbors_clip` and always derive from the frame order (also removes the dependence on how a
metadata file was built); or divide by `used` (mean instead of sum).

## Why it is not applied, and what must happen first

- The effect on ranking is unknown and may be negative. It changes the order for 622 L videos, i.e. most of benchmark A.
- Project policy: the shipped system is evaluated as it is, and nothing is tuned on the final day.
- Test plan: re-implement the rerank on the evaluation side with the neighbourhood as a parameter (the way
  `shared_search` re-creates the post-fusion order), run the 86 L queries and the 28 final queries with
  (a) stored-style for all, (b) fallback for all, (c) mean instead of sum, storing the per-frame sum and `n_neighbors`;
  compare with the current arms with the paired tests of the analysis. Decide only after that.
