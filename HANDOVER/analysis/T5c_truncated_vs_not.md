### T5c. Hit@1 and R@10 for queries whose searched text is over an encoder's context limit against the others, on the arms that search the baseline text and its plain-translation counterpart.

| Configuration | Bench | Split | n | Hit@1 | R@10 | MRR |
|---|---|---|---|---|---|---|
| C01 baseline | A | text over a limit for some encoder | 12 | 25.0 | 75.0 | 0.456 |
| C01 baseline | A | text within every limit | 74 | 31.1 | 74.3 | 0.452 |
| C14 plain translation (translate_gtx) | A | text over a limit for some encoder | 39 | 23.1 | 64.1 | 0.376 |
| C14 plain translation (translate_gtx) | A | text within every limit | 47 | 38.3 | 66.0 | 0.487 |
| C02 beit3 only | A | text over the BEiT-3 limit | 12 | 8.3 | 50.0 | 0.214 |
| C02 beit3 only | A | text within the BEiT-3 limit | 74 | 8.1 | 40.5 | 0.169 |
| C03 clip only | A | text over the OpenCLIP limit | 3 | 0.0 | 66.7 | 0.114 |
| C03 clip only | A | text within the OpenCLIP limit | 83 | 16.9 | 55.4 | 0.283 |
| C04 siglip2 only | A | text over the SigLIP2 limit | 10 | 20.0 | 60.0 | 0.367 |
| C04 siglip2 only | A | text within the SigLIP2 limit | 76 | 35.5 | 67.1 | 0.462 |
| C01 baseline | B | text over a limit for some encoder | 4 | 25.0 | 75.0 | 0.333 |
| C01 baseline | B | text within every limit | 24 | 50.0 | 83.3 | 0.615 |
| C14 plain translation (translate_gtx) | B | text over a limit for some encoder | 7 | 28.6 | 57.1 | 0.329 |
| C14 plain translation (translate_gtx) | B | text within every limit | 21 | 42.9 | 85.7 | 0.585 |
| C02 beit3 only | B | text over the BEiT-3 limit | 3 | 0.0 | 33.3 | 0.056 |
| C02 beit3 only | B | text within the BEiT-3 limit | 25 | 24.0 | 72.0 | 0.433 |
| C03 clip only | B | text over the OpenCLIP limit | 2 | 0.0 | 0.0 | 0.022 |
| C03 clip only | B | text within the OpenCLIP limit | 26 | 42.3 | 84.6 | 0.576 |
| C04 siglip2 only | B | text over the SigLIP2 limit | 4 | 50.0 | 50.0 | 0.510 |
| C04 siglip2 only | B | text within the SigLIP2 limit | 24 | 41.7 | 83.3 | 0.595 |
| C01 baseline | A+B | text over a limit for some encoder | 16 | 25.0 | 75.0 | 0.426 |
| C01 baseline | A+B | text within every limit | 98 | 35.7 | 76.5 | 0.492 |
| C14 plain translation (translate_gtx) | A+B | text over a limit for some encoder | 46 | 23.9 | 63.0 | 0.369 |
| C14 plain translation (translate_gtx) | A+B | text within every limit | 68 | 39.7 | 72.1 | 0.517 |
| C02 beit3 only | A+B | text over the BEiT-3 limit | 15 | 6.7 | 46.7 | 0.182 |
| C02 beit3 only | A+B | text within the BEiT-3 limit | 99 | 12.1 | 48.5 | 0.236 |
| C03 clip only | A+B | text over the OpenCLIP limit | 5 | 0.0 | 40.0 | 0.077 |
| C03 clip only | A+B | text within the OpenCLIP limit | 109 | 22.9 | 62.4 | 0.353 |
| C04 siglip2 only | A+B | text over the SigLIP2 limit | 14 | 28.6 | 57.1 | 0.408 |
| C04 siglip2 only | A+B | text within the SigLIP2 limit | 100 | 37.0 | 71.0 | 0.494 |

- Descriptive: the two groups are different queries (long texts come from long, detailed queries), so a difference is not the effect of the cut. For a single-encoder arm the split uses that encoder's own limit, which isolates it from the others. Groups are small, read n first.
