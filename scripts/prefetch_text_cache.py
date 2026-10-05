# scripts/prefetch_text_cache.py
"""Fetch every translate_gtx or Expand text a preset needs and export it as JSONL, on any machine.

gtx may be unreachable from EC2. Run this on a PC that can reach Google Translate, then commit or copy
the file into backend/app/evaluation/seeds/text_cache/ (seed time imports every *.jsonl there) or
import it with POST /api/admin/evaluation/text-cache/import. A suite then finds the cache full and
never calls the network.

Covers the query text of the preset's translate_gtx configurations on the chosen datasets AND the
event text of every TRAKE query (for the TRAKE-N task mode). Texts already cached, in the seeds or in
the --out file, are not fetched again.

--policy expand_gemini fetches the Expand (Gemini) texts of the preset instead: the query text of its
expand_gemini configurations plus the event text of every TRAKE query. It calls expansion.expand_query,
which paces itself at 4.5 s per call (about 15 minutes for the 145 texts of core2), needs GEMINI_API_KEY and
accepts only a Gemini answer (never the Ollama fallback). It loads no index and no model, so it can run in the
live API container while the API is up; the suite, started later, imports the file (--text-cache, default
<out>/text_cache.jsonl) and finds the cache full, so the API is down only for the retrieval itself.

Gentler on the provider than the backend's own 4.5 s pacing: a configurable delay between requests
(--delay, default 1.5 s), exponential backoff on HTTP 429 and 5xx (honouring Retry-After), and the
JSONL is rewritten after EVERY successful fetch, so a crash or Ctrl+C loses nothing. Run it again and
it resumes: the file is read first and only the missing texts are fetched. After --stop-after
consecutive failures it stops instead of hammering a provider that is refusing everything.

    python scripts/prefetch_text_cache.py --preset core --out backend/app/evaluation/seeds/text_cache/translate_gtx.jsonl
    python scripts/prefetch_text_cache.py --preset core2 --policy expand_gemini --out /opt/aic/data/ablation_out/text_cache.jsonl
"""
from __future__ import annotations

import argparse
import os
import sys
import tempfile
import time
import urllib.error
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "backend"))

if hasattr(sys.stdout, "reconfigure") :
    sys.stdout.reconfigure(encoding = "utf-8")

from app.db.connection import get_conn  # noqa: E402
from app.db.migrate import migrate  # noqa: E402
from app.evaluation import text_cache  # noqa: E402
from app.evaluation.config import RunConfig  # noqa: E402
from app.evaluation.presets import DEFAULT_DATASETS, preset_configs  # noqa: E402
from app.evaluation.runner import _db_path_env  # noqa: E402
from app.evaluation.seed import import_all_seeds  # noqa: E402

DEFAULT_OUT = REPO_ROOT / "backend" / "app" / "evaluation" / "seeds" / "text_cache" / "translate_gtx.jsonl"
TIMEOUT_S = 15.0
MAX_ATTEMPTS = 6
BACKOFF_S = 2.0       # 2, 4, 8, 16, 32 s between attempts unless Retry-After says more


def make_gtx_fn(delay : float, say = print) :
    """The same gtx call the backend and the browser button make (translation._translate_google_gtx),
    with this script's own pacing and retry: 429 and 5xx back off exponentially, any other HTTP error
    (403, 400) fails that text at once because retrying cannot fix it."""
    from app.translation import _retry_after_seconds, _translate_google_gtx

    last = {"at" : 0.0}

    def fetch(text : str) -> tuple[str, float] :
        for attempt in range(1, MAX_ATTEMPTS + 1) :
            wait = delay - (time.monotonic() - last["at"])
            if (wait > 0) :
                time.sleep(wait)
            last["at"] = time.monotonic()
            started = time.monotonic()
            try :
                return _translate_google_gtx(text, TIMEOUT_S), (time.monotonic() - started) * 1000.0
            except urllib.error.HTTPError as exc :
                if (not (exc.code == 429 or exc.code >= 500) or attempt == MAX_ATTEMPTS) :
                    raise
                pause = max(BACKOFF_S * 2 ** (attempt - 1), _retry_after_seconds(exc) or 0.0)
                say(f"  HTTP {exc.code}, attempt {attempt}/{MAX_ATTEMPTS}, waiting {pause:.0f} s")
            except (TimeoutError, urllib.error.URLError) as exc :
                if (attempt == MAX_ATTEMPTS) :
                    raise
                pause = BACKOFF_S * 2 ** (attempt - 1)
                say(f"  {type(exc).__name__}, attempt {attempt}/{MAX_ATTEMPTS}, waiting {pause:.0f} s")
            time.sleep(pause)
        raise RuntimeError("unreachable")

    return fetch


def write_atomically(path : Path, content : str) -> None :
    """Write to a temporary file and rename, so a crash mid-write never leaves a half-written cache."""
    path.parent.mkdir(parents = True, exist_ok = True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(content, encoding = "utf-8")
    os.replace(temporary, path)


def main() -> int :
    parser = argparse.ArgumentParser(description = __doc__.split("\n")[0])
    parser.add_argument("--preset", default = "core")
    parser.add_argument("--policy", default = "translate_gtx", choices = ("translate_gtx", "expand_gemini"), help = "which text to fetch")
    parser.add_argument("--datasets", default = ",".join(DEFAULT_DATASETS), help = "comma-separated dataset versions")
    parser.add_argument("--out", default = str(DEFAULT_OUT))
    parser.add_argument("--delay", type = float, default = 1.5, help = "seconds between requests")
    parser.add_argument("--stop-after", type = int, default = 8, help = "stop after this many consecutive failures")
    args = parser.parse_args()
    datasets = [d.strip() for d in args.datasets.split(",") if d.strip()]
    out = Path(args.out)

    # A scratch database: the backend's own is not needed and not touched.
    # ignore_cleanup_errors: after a Ctrl+C the SQLite file may still be open (Windows refuses to delete it).
    with tempfile.TemporaryDirectory(ignore_cleanup_errors = True) as scratch, _db_path_env(Path(scratch) / "prefetch.db") :
        conn = get_conn()
        migrate(conn)
        import_all_seeds(conn)
        text_cache.import_seed_caches(conn)
        if (out.exists()) :
            text_cache.import_jsonl(conn, out.read_text(encoding = "utf-8"))

        # expand_keywords arms read the expand_gemini answer, so fetching expand_gemini covers them too.
        configs = [c for c in preset_configs(args.preset) if text_cache.fetch_policy(c.text_policy) == args.policy]
        skipped = len(preset_configs(args.preset)) - len(configs)
        # The TRAKE-N configuration is what asks for per-event texts.
        configs.append(RunConfig(name = "trake events", text_policy = args.policy, task_mode = "trake_n"))

        report = text_cache.preflight(conn, configs, datasets)
        missing = [m for m in report["_missing_items"] if m.policy == args.policy]
        if (missing and report["blocked"]) :
            print(f"BLOCKED: {report['message']}")
            return 2
        print(f"preset {args.preset}: {len(configs) - 1} {args.policy} configurations ({skipped} other-policy ones skipped) on {len(datasets)} datasets")
        print(f"texts needed {report['needed']}, already cached {report['cached']}, to fetch {len(missing)}")

        failures : list = []
        started = time.monotonic()

        def progress(index : int, total : int) -> None :
            # After every successful fetch: a crash from here on loses nothing.
            write_atomically(out, text_cache.export_jsonl(conn))
            elapsed = time.monotonic() - started
            print(f"  {index}/{total}, {len(failures)} failed, ETA {(total - index) * elapsed / max(1, index) / 60:.1f} min", flush = True)

        fetched = text_cache.prefetch(
            conn, missing, gtx_fn = make_gtx_fn(args.delay) if args.policy == "translate_gtx" else None, failures = failures,
            on_progress = progress, stop_after_failures = args.stop_after,
        )

        write_atomically(out, text_cache.export_jsonl(conn))
        conn.close()

    print(f"needed {report['needed']}, cached before {report['cached']}, fetched {fetched}, failed {len(failures)}")
    for item, reason in failures :
        print(f"  FAILED {reason}")
    if (len(failures) >= args.stop_after) :
        print(f"stopped after {args.stop_after} consecutive failures; run it again later and it resumes from {out.name}")
    print(f"wrote {out}")
    return 0 if not failures else 1


if (__name__ == "__main__") :
    raise SystemExit(main())
