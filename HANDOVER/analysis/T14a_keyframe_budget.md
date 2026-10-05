### T14a. Keyframes per shot against the duration rule n(T) = min(40, 2 + ceil(max(0, T - 1.67) / 2)).

| Slice | Shots | Mean | Median | p5 / p95 | Max | At the cap of 40 | Equals n(T) | Within 1 of n(T) | Mean (observed - n(T)) |
|---|---|---|---|---|---|---|---|---|---|
| all shots | 204,365 | 4.85 | 3 | 2 / 8 | 1222 | 0.5 | 98.1 | 99.9 | +0.91 |
| without each video's last shot | 202,878 | 3.86 | 3 | 2 / 8 | 40 | 0.3 | 98.3 | 100.0 | -0.02 |
| L | 96,746 | 3.73 | 3 | 2 / 7 | 40 | 0.4 | 98.2 | 100.0 | -0.02 |
| M | 97,434 | 3.46 | 3 | 2 / 7 | 40 | 0.0 | 98.1 | 100.0 | -0.02 |
| N | 298 | 675.24 | 616 | 485 / 1202 | 1222 | 99.0 | 0.0 | 0.0 | +635.52 |
| S | 9,887 | 9.39 | 6 | 2 / 32 | 40 | 3.1 | 100.0 | 100.0 | +0.00 |

- T is estimated: the first keyframe of the next shot minus this shot's first keyframe, over the frame rate; the true shot boundaries are not stored. Spearman correlation between estimated duration and keyframe count: 0.94.
