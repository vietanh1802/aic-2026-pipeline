# scripts/aggregate_error_labels.py
"""Aggregate the manual error labels from a filled error_labeling_sheet.csv.

    python scripts/aggregate_error_labels.py <analysis folder>/errors/error_labeling_sheet.csv --run-dir <ablation_out/timestamp>

The sheet has one row per query the baseline missed at rank 1. The person fills error_codes (D1 to D9,
semicolon separated), small_detail_query (yes or no), text_cue_present (ocr, asr, both, none) and
label_doubt (yes or no). This script writes, next to the sheet in aggregated/:
    L1_error_codes            queries per code overall
    L2_codes_by_prefix_task   queries per code by reference-video prefix and by task type
    L3_codes_by_auto_label    queries per code cross-tabulated with the automatic labels already in the sheet
    L4_cues_and_doubt         text_cue_present and label_doubt counts
    L5_small_detail_by_encoder  claim C4: Hit@1 and R@10 of each single encoder on small_detail_query yes versus no
    L1_error_codes.pdf/png    bar figure of L1
Descriptive only: the rows are the baseline's misses, so the groups say nothing about queries it got right.
A sheet inside a folder named *_SYNTHETIC or *_SMOKE is stamped as such.
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
if hasattr(sys.stdout, "reconfigure") :
    sys.stdout.reconfigure(encoding = "utf-8")

from ablation_analysis import stats  # noqa: E402
from ablation_analysis.errors import TAXONOMY  # noqa: E402
from ablation_analysis.tablefmt import Table, interval, pct  # noqa: E402

MEANING = dict(TAXONOMY)


def read_sheet(path : Path) -> list[dict[str, str]] :
    with open(path, encoding = "utf-8-sig", newline = "") as handle :
        return list(csv.DictReader(line for line in handle if not line.startswith("#")))


def codes_of(row : dict[str, str]) -> list[str] :
    return [c.strip().upper() for c in (row.get("error_codes") or "").replace(",", ";").split(";") if c.strip()]


def aggregate(rows : list[dict[str, str]]) -> list[Table] :
    """The L1 to L4 tables from a filled sheet. Rows without error_codes are counted as unlabelled."""
    labelled = [r for r in rows if codes_of(r)]
    counts : dict[str, int] = {}
    for r in labelled :
        for code in codes_of(r) :
            counts[code] = counts.get(code, 0) + 1
    all_codes = sorted(set(counts) | set(MEANING))
    tables = [Table("L1", "L1_error_codes", f"Manual error codes ({len(labelled)} of {len(rows)} sheet rows labelled).", ["Code", "Meaning", "Queries", "Share of labelled rows"],
                    [[c, MEANING.get(c, ""), str(counts.get(c, 0)), pct(counts.get(c, 0) / len(labelled)) if labelled else ""] for c in all_codes], align = "llrr",
                    notes = ["A query can carry several codes, so counts add up to more than the number of rows."])]

    prefixes, tasks = ("L", "M", "N", "S"), ("KIS", "QA", "TRAKE")
    rows_out = []
    for c in all_codes :
        mine = [r for r in labelled if c in codes_of(r)]
        rows_out.append([c, *[str(sum(1 for r in mine if r["ref_video"][ : 1] == p)) for p in prefixes], *[str(sum(1 for r in mine if r["task"] == t)) for t in tasks]])
    tables.append(Table("L2", "L2_codes_by_prefix_task", "Error codes by reference-video prefix and by task type (queries).", ["Code", *prefixes, *tasks], rows_out, align = "l" + "r" * 7))

    autos = sorted({a.strip() for r in labelled for a in (r.get("auto_labels") or "").split(";") if a.strip()})
    rows_out = []
    for c in all_codes :
        mine = [r for r in labelled if c in codes_of(r)]
        rows_out.append([c, *[str(sum(1 for r in mine if a in [x.strip() for x in (r.get("auto_labels") or "").split(";")])) for a in autos]])
    tables.append(Table("L3", "L3_codes_by_auto_label", "Manual error codes against the automatic labels of the same queries (queries).", ["Code", *autos], rows_out, small = True, align = "l" + "r" * len(autos)))

    def tally(field : str, options : list[str]) -> list[str] :
        return [str(sum(1 for r in labelled if (r.get(field) or "").strip().lower() == o)) for o in options]
    tables.append(Table("L4", "L4_cues_and_doubt", "Text cues and label doubt on the labelled rows.", ["Field", "Counts"],
                        [["text_cue_present (ocr / asr / both / none)", " / ".join(tally("text_cue_present", ["ocr", "asr", "both", "none"]))],
                         ["label_doubt (yes / no)", " / ".join(tally("label_doubt", ["yes", "no"]))]], align = "ll"))
    return tables


def small_detail_table(rows : list[dict[str, str]], run_dir : Path) -> Table | None :
    """Claim C4 check from the single-encoder runs of the run folder."""
    from ablation_analysis.data import load_run_folder

    flagged = {(r["dataset"], r["query_key"]) : (r.get("small_detail_query") or "").strip().lower() for r in rows if (r.get("small_detail_query") or "").strip().lower() in ("yes", "no")}
    if (not flagged) :
        return None
    data = load_run_folder(run_dir)
    out = []
    for model, label in (("beit3", "BEiT-3"), ("clip", "OpenCLIP"), ("siglip2", "SigLIP2")) :
        code = data.code_for(f"single:{model}")
        if (not code) :
            continue
        for answer in ("yes", "no") :
            results = [data.by_code[code][u] for u, a in flagged.items() if a == answer and u in data.by_code[code]]
            if (not results) :
                continue
            h1, h10 = sum(1 for r in results if r.hit(1)), sum(1 for r in results if r.hit(10))
            out.append([label, answer, str(len(results)), f"{pct(h1 / len(results))} {interval(*stats.wilson(h1, len(results)))}", f"{pct(h10 / len(results))} {interval(*stats.wilson(h10, len(results)))}"])
    return Table("L5", "L5_small_detail_by_encoder", "Claim C4: single-encoder results on the labelled misses, by small_detail_query.", ["Encoder", "Small detail", "n", "Hit@1 [95%]", "R@10 [95%]"], out, align = "llrll",
                 notes = ["Descriptive. The rows are only the queries the baseline missed at rank 1, so this cannot compare easy queries with hard ones, and the groups are small."])


def main() -> int :
    parser = argparse.ArgumentParser(description = __doc__.split("\n")[0])
    parser.add_argument("sheet", help = "the filled error_labeling_sheet.csv")
    parser.add_argument("--run-dir", default = None, help = "run folder with ablation.db, for the small-detail check (claim C4)")
    args = parser.parse_args()

    sheet = Path(args.sheet)
    rows = read_sheet(sheet)
    folder = sheet.parent.parent
    stamp = next((m for m in ("SYNTHETIC", "SMOKE") if folder.name.endswith("_" + m) or sheet.parent.name.endswith("_" + m)), "")
    stamp = f"{stamp} RUN" if stamp else ""
    out = sheet.parent / "aggregated"
    tables = aggregate(rows)
    if (args.run_dir) :
        extra = small_detail_table(rows, Path(args.run_dir))
        if (extra) :
            tables.append(extra)
    for table in tables :
        table.write(out, stamp)
    try :
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        first = tables[0]
        fig, ax = plt.subplots(figsize = (11.7 / 2.54, 2.8), constrained_layout = True)
        ax.bar([r[0] for r in first.rows], [int(r[2]) for r in first.rows], color = "#0072B2", hatch = "//", edgecolor = "white")
        ax.set_ylabel("queries")
        ax.set_title("Manual error codes" + (f" ({stamp}: not results)" if stamp else ""), color = "#cc0000" if stamp else "black", fontsize = 8)
        fig.savefig(out / "L1_error_codes.pdf")
        fig.savefig(out / "L1_error_codes.png", dpi = 300)
    except ImportError :
        print("matplotlib not installed: no figure written")
    labelled = sum(1 for r in rows if codes_of(r))
    print(f"{labelled} of {len(rows)} rows labelled; wrote {len(tables)} tables to {out}")
    return 0


if (__name__ == "__main__") :
    raise SystemExit(main())
