# scripts/analyze_ablation.py
"""Turn an ablation run folder into everything the paper needs: statistics, tables (CSV, LaTeX, Markdown),
figures (PDF and PNG), error analysis, qualitative cases and written aids.

    pip install -r scripts/requirements-analysis.txt
    python scripts/analyze_ablation.py --run-dir ablation_out/20261005-101500 --features ablation_out/features
    python scripts/analyze_ablation.py --run-dir ... --features ... --labels error_labeling_sheet_filled.csv --images-dir <keyframe images>

Reads ablation.db with sqlite3 and never imports the backend. A run folder that is synthetic or a smoke
test (see ablation_analysis/data.py) is written to <out>_SYNTHETIC or <out>_SMOKE and every output is
stamped. A builder that raises is reported, the other outputs are still written, and the exit code is 1.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import platform
import sys
import time
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
if hasattr(sys.stdout, "reconfigure") :
    sys.stdout.reconfigure(encoding = "utf-8")

from ablation_analysis import errors as E  # noqa: E402
from ablation_analysis import qualitative, stats, tables_core, tables_more, writeups  # noqa: E402
from ablation_analysis.context import Ctx  # noqa: E402
from ablation_analysis.data import load_run_folder  # noqa: E402
from ablation_analysis.facts import load_facts  # noqa: E402
from ablation_analysis.features import load_features  # noqa: E402
from ablation_analysis.tablefmt import Table  # noqa: E402

TABLE_BUILDERS = (
    tables_core.t1_corpus_and_benchmarks, tables_core.t2_main_ablation, tables_core.t3_encoder_grid, tables_core.t4_rerank,
    tables_core.t5_text_policy, tables_core.t5b_text_length, tables_core.t5c_truncated_vs_not, tables_core.t5s_sanity, tables_core.t6_by_task_and_prefix, tables_more.t7_trake, tables_more.t8_complementarity,
    tables_more.t9_interval_level, tables_more.t10_errors, tables_more.t11_text_signal, tables_more.t12_efficiency,
    tables_core.t13_sensitivity, tables_more.t14_sampling,
)
PAPER_PREFIXES = ("T1", "T2_", "T3", "T4", "T7", "T8", "T10", "T12")


def sha256(path : Path) -> str | None :
    if (not path.exists()) :
        return None
    digest = hashlib.sha256()
    with open(path, "rb") as handle :
        for chunk in iter(lambda : handle.read(1 << 20), b"") :
            digest.update(chunk)
    return digest.hexdigest()


def read_labels(path : Path | None) -> list[dict[str, str]] | None :
    if (path is None) :
        return None
    with open(path, encoding = "utf-8-sig", newline = "") as handle :
        return list(csv.DictReader(handle))


def write_csv(path : Path, rows : list[dict], stamp : str) -> None :
    path.parent.mkdir(parents = True, exist_ok = True)
    with open(path, "w", encoding = "utf-8", newline = "") as handle :
        if (stamp) :
            handle.write(f"# {stamp}: these numbers are not results\n")
        if (not rows) :
            return
        fields = list(dict.fromkeys(k for row in rows for k in row))
        writer = csv.DictWriter(handle, fieldnames = fields, lineterminator = "\n")
        writer.writeheader()
        writer.writerows(rows)


def main() -> int :
    parser = argparse.ArgumentParser(description = __doc__.split("\n")[0])
    parser.add_argument("--run-dir", required = True, help = "folder with ablation.db (and suite.json, provenance.json)")
    parser.add_argument("--features", default = None, help = "folder written by scripts/dump_corpus_features.py")
    parser.add_argument("--labels", default = None, help = "the filled error_labeling_sheet.csv")
    parser.add_argument("--images-dir", default = None, help = "keyframe images, for the qualitative page")
    parser.add_argument("--facts", default = None, help = "JSON overriding the supplied numbers in ablation_analysis/facts.py")
    parser.add_argument("--out", default = None, help = "output folder (default <run-dir>/analysis)")
    parser.add_argument("--skip-figures", action = "store_true")
    args = parser.parse_args()

    started = time.monotonic()
    run_dir = Path(args.run_dir)
    features = load_features(Path(args.features)) if args.features else None
    data = load_run_folder(run_dir, features_synthetic = bool(features and features.synthetic))
    out = Path(args.out) if args.out else run_dir / "analysis"
    if (data.mode != "REAL" and not out.name.endswith("_" + data.mode)) :
        out = out.with_name(out.name + "_" + data.mode)
    out.mkdir(parents = True, exist_ok = True)
    ctx = Ctx(data = data, features = features, labels = read_labels(Path(args.labels)) if args.labels else None, facts = load_facts(Path(args.facts) if args.facts else None),
              out = out, images_dir = Path(args.images_dir) if args.images_dir else None)
    print(f"run folder {run_dir}: {len(data.results)} results, {len(data.configs)} configurations, mode {data.mode} {data.mode_reasons}")
    failures : list[str] = []

    def attempt(name : str, fn, *a) :
        try :
            return fn(*a)
        except Exception as exc :
            traceback.print_exc()
            failures.append(f"{name}: {type(exc).__name__}: {exc}")
            ctx.skip(name, f"FAILED with {type(exc).__name__}: {exc}")
            return None

    tables : list[Table] = []
    for builder in TABLE_BUILDERS :
        built = attempt(builder.__name__, builder, ctx)
        tables += built or []
    for table in tables :
        table.write(out / "tables", ctx.stamp)
    (out / "tables" / "all_tables.md").write_text((f"# {ctx.stamp}\n\n" if ctx.stamp else "") + "\n".join(t.to_markdown(ctx.stamp) for t in tables), encoding = "utf-8")
    paper = [t for t in tables if t.slug.startswith(PAPER_PREFIXES)]
    (out / "paper_tables.tex").write_text(((f"% {ctx.stamp}: these numbers are not results\n") if ctx.stamp else "") + "\n".join(t.to_latex(ctx.stamp) for t in paper), encoding = "utf-8")

    written = {"tables" : [t.slug for t in tables]}
    if (not args.skip_figures) :
        from ablation_analysis import figures
        written["figures"] = attempt("figures", figures.build_all, ctx, out / "figures") or []

    # Error analysis: per-query labels, property correlations, the manual labelling sheet.
    labels = []
    for bench in ("A", "B") :
        labels += list((attempt(f"cross_labels {bench}", E.cross_labels, data, bench) or {}).values())
    write_csv(out / "errors" / "query_labels.csv", labels, ctx.stamp)
    corr = []
    for bench in ("A", "B", "A+B") :
        results = data.results_of(ctx.base) if bench == "A+B" else data.results_of(ctx.base, bench)
        corr += [{"bench" : bench, **row} for row in E.property_correlations(results, features)]
    write_csv(out / "errors" / "property_correlations.csv", corr, ctx.stamp)
    sheet = E.labeling_sheet(data, features)
    E.write_sheet(out / "errors", sheet)
    written["errors"] = ["query_labels.csv", "property_correlations.csv", "error_labeling_sheet.csv", "taxonomy.csv"]

    summary = attempt("qualitative", qualitative.write_qualitative, ctx, out / "qualitative")
    written["qualitative"] = [f"{summary['cases']} cases"] if summary else []

    for name, fn in (("claims_check.md", writeups.claims_check), ("protocol.md", writeups.protocol), ("limitations_candidates.md", writeups.limitations), ("numbers_to_fix_in_paper.md", writeups.numbers_to_fix)) :
        text = attempt(name, fn, ctx)
        if (text) :
            (out / name).write_text(text, encoding = "utf-8")
    written["aids"] = ["claims_check.md", "protocol.md", "limitations_candidates.md", "numbers_to_fix_in_paper.md"]
    (out / "README.md").write_text(writeups.readme(ctx, written), encoding = "utf-8")

    import numpy
    try :
        import matplotlib
        mpl = matplotlib.__version__
    except ImportError :
        mpl = None
    (out / "analysis_provenance.json").write_text(json.dumps({
        "mode" : data.mode, "mode_reasons" : data.mode_reasons, "synthetic" : data.mode == "SYNTHETIC", "smoke" : data.mode == "SMOKE",
        "commit_full" : data.provenance.get("commit_full"), "run_version" : data.provenance.get("version"),
        "inputs" : {"ablation.db" : sha256(run_dir / "ablation.db"), "provenance.json" : sha256(run_dir / "provenance.json"), "suite.json" : sha256(run_dir / "suite.json"),
                    **({f"features/{p.name}" : sha256(p) for p in sorted(Path(args.features).glob("*"))} if args.features else {}), **({"labels" : sha256(Path(args.labels))} if args.labels else {})},
        "seed" : stats.SEED, "bootstrap_resamples" : stats.N_BOOT, "python" : platform.python_version(), "numpy" : numpy.__version__, "matplotlib" : mpl,
        "skipped_or_failed" : ctx.skipped, "seconds" : round(time.monotonic() - started, 1),
    }, indent = 1), encoding = "utf-8")

    print(f"wrote {len(tables)} tables, {len(written.get('figures', []))} figure files to {out} in {time.monotonic() - started:.0f} s")
    for line in ctx.skipped :
        print(f"  skipped: {line}")
    return 1 if failures else 0


if (__name__ == "__main__") :
    raise SystemExit(main())
