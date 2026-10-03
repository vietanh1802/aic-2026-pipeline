# scripts/prefetch_text_cache.py
"""Fetch every translate_gtx text a preset needs and export it as JSONL, on any machine.

gtx may be unreachable from EC2. Run this on a PC that can reach Google Translate, then commit or copy
the file into backend/app/evaluation/seeds/text_cache/ (seed time imports every *.jsonl there) or
import it with POST /api/admin/evaluation/text-cache/import. A suite then finds the cache full and
never calls the network.

Covers the query text of the preset's translate_gtx configurations on the chosen datasets AND the
event text of every TRAKE query (for the TRAKE-N task mode). Texts already cached, in the seeds or in
the --out file, are not fetched again. Expand (Gemini) texts are not fetched here.

    python scripts/prefetch_text_cache.py --preset core --out backend/app/evaluation/seeds/text_cache/translate_gtx.jsonl
"""
from __future__ import annotations

import argparse
import sys
import tempfile
import time
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


def main() -> int :
    parser = argparse.ArgumentParser(description = __doc__.split("\n")[0])
    parser.add_argument("--preset", default = "core")
    parser.add_argument("--datasets", default = ",".join(DEFAULT_DATASETS), help = "comma-separated dataset versions")
    parser.add_argument("--out", default = str(DEFAULT_OUT))
    args = parser.parse_args()
    datasets = [d.strip() for d in args.datasets.split(",") if d.strip()]
    out = Path(args.out)

    # A scratch database: the backend's own is not needed and not touched.
    with tempfile.TemporaryDirectory() as scratch, _db_path_env(Path(scratch) / "prefetch.db") :
        conn = get_conn()
        migrate(conn)
        import_all_seeds(conn)
        text_cache.import_seed_caches(conn)
        if (out.exists()) :
            text_cache.import_jsonl(conn, out.read_text(encoding = "utf-8"))

        configs = [c for c in preset_configs(args.preset) if c.text_policy == "translate_gtx"]
        skipped = len(preset_configs(args.preset)) - len(configs)
        # The TRAKE-N configuration is what asks for per-event texts.
        configs.append(RunConfig(name = "trake events", text_policy = "translate_gtx", task_mode = "trake_n"))

        report = text_cache.preflight(conn, configs, datasets)
        missing = [m for m in report["_missing_items"] if m.policy == "translate_gtx"]
        print(f"preset {args.preset}: {len(configs) - 1} translate_gtx configurations ({skipped} other-policy ones skipped) on {len(datasets)} datasets")
        print(f"texts needed {report['needed']}, already cached {report['cached']}, to fetch {len(missing)}")

        failures : list = []
        started = time.monotonic()

        def progress(index : int, total : int) -> None :
            elapsed = time.monotonic() - started
            print(f"  {index}/{total}, {len(failures)} failed, ETA {(total - index) * elapsed / max(1, index) / 60:.1f} min", flush = True)

        fetched = text_cache.prefetch(conn, missing, failures = failures, on_progress = progress)

        out.parent.mkdir(parents = True, exist_ok = True)
        out.write_text(text_cache.export_jsonl(conn), encoding = "utf-8")
        conn.close()

    print(f"fetched {fetched}, cached before {report['cached']}, failed {len(failures)}")
    for item, reason in failures :
        print(f"  FAILED {reason}")
    print(f"wrote {out}")
    return 0 if not failures else 1


if (__name__ == "__main__") :
    raise SystemExit(main())
