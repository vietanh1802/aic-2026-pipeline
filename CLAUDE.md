# CLAUDE.md

Working conventions for this repo. Follow these for every file you create or
edit here, not just when explicitly reminded.

---

## Language and punctuation

Always use English. Code, comments, docstrings, Markdown, variable names,
everything. Use an en dash (-) where a dash is needed. Never use an em dash.

---

## File headers

Every source file starts with a one-line comment giving its own path
relative to the repo root, before any imports :

```python
# backend/app/text_signal.py

import re
```

```typescript
// frontend/src/components/TextSignalBadge.tsx

import React from 'react'
```

This is not optional decoration - when a file is opened in isolation (a diff,
a search hit, a pasted snippet), the header is the only thing that says where
it lives.

---

## Documentation and comments

Comments and docstrings exist to make the *next* reader (including future
you, or Claude in a later session) understand the code quickly without
re-deriving it. Write them generously where intent isn't obvious :

- Every module that isn't trivial gets a short docstring or top comment
  explaining what it's for and how it fits into the pipeline - e.g. "loads
  the gzipped ASR index at startup; degrades gracefully if the file is
  missing" tells a reader in one line what would otherwise take a full read
  of the module to figure out.
- Non-obvious decisions get a comment explaining *why*, not what : "diacritics
  kept in the BM25 vocab - stripping them breaks lookup against the indexed
  artifact" is worth writing down; `x += 1  # increment x` is not.
- Fallback branches, retry logic, and anything that silently changes
  behavior under failure need a comment saying what triggers the fallback
  and what the consequence is downstream.
- Don't narrate obvious operations. The line between "helpful" and
  "clutter" is whether a competent reader would otherwise have to stop and
  think - if yes, write the comment; if the code already says it, don't.

Prefer real documentation (module docstrings, function docstrings for
anything with non-trivial inputs/outputs) over relying on the code being
self-explanatory. Terse code and clear documentation are not in tension -
the code stays compact, the comments carry the reasoning.

---

## Code style

Compact, horizontally readable. Spaces around operators and type
annotations :

```python
n_matched  = sum(1 for r in results if r['matched'])
axis       : int   = 1
threshold  : float = 0.7
```

```python
{"key" : value, "mode" : "bm25"}
```

Space before the colon in control structures and definitions :

```python
def annotate_videos(query : str, mode : str) -> dict :
    ...

if text_filter_active :
    ...

for video_id in candidates :
    ...
```

Spaced slicing :

```python
results[ : 10]
tokens[start : end]
```

Align related assignments and dictionary colons within the same block :

```python
BM25_INDEX_PATH = Path('indexes/bm25.json')
ASR_INDEX_PATH  = Path('indexes/asr_text_index.json.gz')
CACHE_SIZE      = 512
```

Two blank lines before top-level function/class definitions, one blank line
between other logical blocks. No blank line after the final statement in a
function body or notebook cell.

Keep short lists, dicts, comprehensions, paths, and method chains on one
line. Break only when a line is genuinely too long, and when wrapping, group
arguments logically rather than one item per line. Use meaningful
intermediate variables instead of deeply nested calls.

These rules apply to code and code-adjacent content (scripts, notebooks,
config, inline snippets in explanations). They do not apply to prose,
Markdown write-ups, or commit messages.

---

## Simplicity

Default to the simplest implementation that correctly does the task. No
extra classes, wrapper layers, config systems, CLIs, logging frameworks, or
defensive machinery unless there's a concrete, immediate reason.

A helper function earns its place by removing real duplication or making
the main flow clearly easier to follow. If it's called once and doesn't
simplify anything, inline it.

Don't catch broad exceptions without a specific recovery action, and never
silently swallow an error. The one confirmed exception in this repo: a
side-feature (annotation, filter extraction) that fails must not take the
core search response down with it - wrap *that specific call* narrowly and
say in a comment why it's isolated (see "annotation block has its own
try/except" pattern already in `main.py`).

Don't add metrics, reports, validation, or configurability that wasn't
asked for. Default to the simple approach and mention a hardened
alternative only if it's actually relevant.

---

## Notebooks

Run Python directly in the notebook process - no `subprocess`, shell
wrappers, or CLI calls for code that can be called as a function.

One clear stage per code cell. No blank line after the final statement of a
cell. Long-running cells show visible progress (`tqdm`, per-item prints).
Errors surface directly, not swallowed behind broad excepts.

Markdown between cells is short and explains *why*, not *what*. Don't
narrate obvious operations ("now we load the file"). Organize around the
actual workflow (`## 2. Build the ASR index`, `### 2.1 Timestamp overlap`),
not one heading per cell.

Give each new analysis/build notebook a clear, descriptive filename so it's
identifiable without opening it.

---

## Repo layout (confirmed from the codebase so far)

```
backend/
  app/
    main.py              - FastAPI endpoints; EnsembleSearchRequest / SearchResponseEx;
                            annotation block wrapped in its own try/except so a
                            side-feature failure never produces a 500
    preprocess.py         - core retrieval (FAISS / CLIP / BEiT3) - do not modify
                            casually; this is the ranking invariant everything
                            else builds on top of
    asr_text.py            - loads asr_text_index.json.gz at startup, O(1) frame
                            lookup, degrades gracefully if the file is missing
    text_signal.py          - annotate_videos(); substring / regex / bm25 modes,
                            post-retrieval only - never changes rankings
    filter_extraction.py    - Gemini-based ASR/OCR filter term extraction from
                            query text, cached (see cache note below)
    expansion.py             - query expansion; filter_extraction.py shares its
                            provider/retry/pacing chain
  tests/

scripts/
  build_asr_text_index.py   - offline index builder (windows.jsonl + fps_map.json
                            + CLIP/BEiT3 mappings -> gzipped JSON), deterministic
  generate_filter_terms.py   - offline Gemini annotation of seed files, idempotent,
                            rate-limited, skips writing on provider failure so
                            failed queries stay retryable

frontend/
  src/
    components/
      TextSignalBadge.tsx    - colored-dot annotation + hover popover
      FrameDisplay.tsx        - mounts the badge on each result card
      QueryInput.tsx           - text-filter row + mode selector
      DropDown.tsx              - controlled dropdown, optional description field
    store/
      queryStore.ts              - textFilter / textFilterMode state
      useSearchStore.ts           - videoAnnotations state
    App.tsx                        - wires filter state into the search call
    types/api.ts                    - VideoAnnotation, SearchResponse types
```

> Deploy steps, environment/test commands, seed accounts, and any
> migration/versioning conventions specific to this repo aren't captured
> here yet - add them once confirmed rather than assuming they match a
> different project.

---

## Things already known to bite here

- **`preprocess.py` is the retrieval core.** Don't touch it for feature
  work; if a change seems to require it, that's a signal to re-scope the
  feature, not the file.
- **Side-features must fail closed.** Annotation/filter-extraction errors
  are caught narrowly so they degrade the extra signal, never the base
  search response.
- **BM25 vocabulary keeps diacritics.** Stripping them before tokenizing
  silently looks up the wrong term - confirmed from artifact inspection,
  don't "clean up" this behavior.
- **ASR on Vietnamese-language video can garble embedded English terms**
  (Whisper transcription artifact). Treat English filter terms as OCR-only
  unless there's specific evidence the ASR actually caught them.
- **Frontend derived state must be cleared eagerly.** `queryStore` setters
  clear `videoAnnotations` immediately when the filter field changes, so
  stale badges never linger while the user is still typing - keep that
  pattern for any new derived-from-query state.

---

Update this file when a new rule is needed or a real time-sink is
discovered - don't let it drift from what the repo actually does.