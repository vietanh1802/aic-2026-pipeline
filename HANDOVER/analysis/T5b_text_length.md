### T5b. Tokens of the searched text under each encoder's own tokenizer, against its context limit.

| Text | Bench | Encoder | Queries | Median tokens | p90 | Max | Limit | Over the limit | Truncated by the code | Tokens by |
|---|---|---|---|---|---|---|---|---|---|---|
| Expand (LLM-prepared English) | A | BEiT-3 | 86 | 45 | 67 | 111 | 64 | 12 (14.0%) | 0 (0.0%) | tokenizer |
| Expand (LLM-prepared English) | A | OpenCLIP | 86 | 46 | 68 | 109 | 77 | 3 (3.5%) | 3 (3.5%) | tokenizer |
| Expand (LLM-prepared English) | A | SigLIP2 | 86 | 44 | 65 | 107 | 64 | 10 (11.6%) | 10 (11.6%) | tokenizer |
| Expand (LLM-prepared English) | B | BEiT-3 | 28 | 40 | 63 | 101 | 64 | 3 (10.7%) | 0 (0.0%) | tokenizer |
| Expand (LLM-prepared English) | B | OpenCLIP | 28 | 40 | 68 | 101 | 77 | 2 (7.1%) | 2 (7.1%) | tokenizer |
| Expand (LLM-prepared English) | B | SigLIP2 | 28 | 38 | 67 | 99 | 64 | 4 (14.3%) | 4 (14.3%) | tokenizer |
| Expand (LLM-prepared English) | A+B | BEiT-3 | 114 | 43 | 67 | 111 | 64 | 15 (13.2%) | 0 (0.0%) | tokenizer |
| Expand (LLM-prepared English) | A+B | OpenCLIP | 114 | 44 | 69 | 109 | 77 | 5 (4.4%) | 5 (4.4%) | tokenizer |
| Expand (LLM-prepared English) | A+B | SigLIP2 | 114 | 43 | 65 | 107 | 64 | 14 (12.3%) | 14 (12.3%) | tokenizer |
| plain translation (Google Translate) | A | BEiT-3 | 86 | 62 | 96 | 110 | 64 | 38 (44.2%) | 0 (0.0%) | tokenizer |
| plain translation (Google Translate) | A | OpenCLIP | 86 | 63 | 95 | 111 | 77 | 27 (31.4%) | 27 (31.4%) | tokenizer |
| plain translation (Google Translate) | A | SigLIP2 | 86 | 62 | 95 | 110 | 64 | 38 (44.2%) | 38 (44.2%) | tokenizer |
| plain translation (Google Translate) | B | BEiT-3 | 28 | 54 | 99 | 149 | 64 | 7 (25.0%) | 0 (0.0%) | tokenizer |
| plain translation (Google Translate) | B | OpenCLIP | 28 | 54 | 100 | 160 | 77 | 6 (21.4%) | 6 (21.4%) | tokenizer |
| plain translation (Google Translate) | B | SigLIP2 | 28 | 52 | 100 | 160 | 64 | 7 (25.0%) | 7 (25.0%) | tokenizer |
| plain translation (Google Translate) | A+B | BEiT-3 | 114 | 58 | 97 | 149 | 64 | 45 (39.5%) | 0 (0.0%) | tokenizer |
| plain translation (Google Translate) | A+B | OpenCLIP | 114 | 58 | 97 | 160 | 77 | 33 (28.9%) | 33 (28.9%) | tokenizer |
| plain translation (Google Translate) | A+B | SigLIP2 | 114 | 57 | 96 | 160 | 64 | 45 (39.5%) | 45 (39.5%) | tokenizer |
| expand_keywords | A | BEiT-3 | 86 | 18 | 26 | 37 | 64 | 0 (0.0%) | 0 (0.0%) | tokenizer |
| expand_keywords | A | OpenCLIP | 86 | 19 | 26 | 36 | 77 | 0 (0.0%) | 0 (0.0%) | tokenizer |
| expand_keywords | A | SigLIP2 | 86 | 18 | 25 | 36 | 64 | 0 (0.0%) | 0 (0.0%) | tokenizer |
| expand_keywords | B | BEiT-3 | 28 | 16 | 25 | 32 | 64 | 0 (0.0%) | 0 (0.0%) | tokenizer |
| expand_keywords | B | OpenCLIP | 28 | 16 | 25 | 32 | 77 | 0 (0.0%) | 0 (0.0%) | tokenizer |
| expand_keywords | B | SigLIP2 | 28 | 15 | 24 | 31 | 64 | 0 (0.0%) | 0 (0.0%) | tokenizer |
| expand_keywords | A+B | BEiT-3 | 114 | 18 | 26 | 37 | 64 | 0 (0.0%) | 0 (0.0%) | tokenizer |
| expand_keywords | A+B | OpenCLIP | 114 | 19 | 27 | 36 | 77 | 0 (0.0%) | 0 (0.0%) | tokenizer |
| expand_keywords | A+B | SigLIP2 | 114 | 17 | 25 | 36 | 64 | 0 (0.0%) | 0 (0.0%) | tokenizer |
| raw Vietnamese | A | BEiT-3 | 86 | 150 | 220 | 280 | 64 | 86 (100.0%) | 0 (0.0%) | tokenizer |
| raw Vietnamese | A | OpenCLIP | 86 | 244 | 360 | 437 | 77 | 86 (100.0%) | 86 (100.0%) | tokenizer |
| raw Vietnamese | A | SigLIP2 | 86 | 73 | 112 | 147 | 64 | 55 (64.0%) | 55 (64.0%) | tokenizer |
| raw Vietnamese | B | BEiT-3 | 28 | 136 | 246 | 343 | 64 | 28 (100.0%) | 0 (0.0%) | tokenizer |
| raw Vietnamese | B | OpenCLIP | 28 | 226 | 397 | 485 | 77 | 28 (100.0%) | 28 (100.0%) | tokenizer |
| raw Vietnamese | B | SigLIP2 | 28 | 68 | 120 | 187 | 64 | 15 (53.6%) | 15 (53.6%) | tokenizer |
| raw Vietnamese | A+B | BEiT-3 | 114 | 147 | 223 | 343 | 64 | 114 (100.0%) | 0 (0.0%) | tokenizer |
| raw Vietnamese | A+B | OpenCLIP | 114 | 240 | 376 | 485 | 77 | 114 (100.0%) | 114 (100.0%) | tokenizer |
| raw Vietnamese | A+B | SigLIP2 | 114 | 72 | 114 | 187 | 64 | 70 (61.4%) | 70 (61.4%) | tokenizer |

- Tokens include the encoder's start and end tokens. OpenCLIP and SigLIP2 cut a longer text (their tokenizer truncates), so over the limit means the end of the text was not read. This backend does NOT cut text for BEiT-3 (preprocess._Beit3Tokenizer adds no truncation): a text over 64 tokens is longer than the 64 the BEiT-3 retrieval model was fine-tuned on, which is a different problem than being cut, and why its truncated column is 0.
- Tokens by: tokenizer (the encoder's real tokenizer, loaded without its weights) or estimate (a word-count approximation, words x 1.4 + 2, used when a tokenizer was not on the host; the reason is stored per query). TRAKE-N queries count the longest of their event texts.
