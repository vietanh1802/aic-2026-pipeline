# scripts/make_paper_tables.py
"""Ready-to-paste LaTeX tables for the paper, computed from the per-query ranks of run folders.

Every number is recomputed from rank_matrix_A.csv / rank_matrix_B.csv (video rank of the reference per query and
configuration; blank = not retrieved, MRR contribution 0), so a cell traces to one run folder and one configuration
name. sources.csv lists that mapping for every cell. TRAKE rows pool the TRAKE queries of A and B (8 queries).

    python scripts/make_paper_tables.py --run-dir <core3 folder> [--final-dir <final_table folder>] [--visual-text sentence]

Tables (written to <run-dir>/paper_tables/, or --out):
  visual.tex        seven encoder sets, rerank off, one text (--visual-text), A and B
  text_step.tex     Expand sentence vs Expand keywords vs plain translation, rerank off, each single encoder and all three
  trake.tex         TRAKE-N vs whole-description search, rerank off, per text policy
  rerank_onoff.tex  supplement: rerank on vs off, Expand sentence, seven encoder sets
  components.tex    the component ablation table, from the final_table run (--final-dir)
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

LABEL = {"beit3" : "BEiT-3", "clip" : "OpenCLIP", "siglip2" : "SigLIP2"}
SETS = ["BEiT-3", "OpenCLIP", "SigLIP2", "BEiT-3 + OpenCLIP", "BEiT-3 + SigLIP2", "OpenCLIP + SigLIP2", "All three"]
# core3 codes per text policy, rerank off, in SETS order.
OFF_CODES = {
    "sentence" : ["C09", "C10", "C11", "C12a", "C12b", "C12c", "C08"],
    "keywords" : ["C23", "C24", "C25", "C26", "C27", "C28", "C29"],
    "plain"    : ["C16", "C17", "C18", "C19", "C20", "C21", "C22"],
}
ON_CODES = ["C02", "C03", "C04", "C05", "C06", "C07", "C01"]
TEXT_NAME = {"sentence" : "Expand (sentence)", "keywords" : "Expand (keywords)", "plain" : "Plain translation"}
METRICS = ("H@1", "R@5", "R@10", "MRR")


class Run :
    def __init__(self, folder : Path) :
        self.folder = folder
        self.ranks : dict[str, dict[str, dict[tuple[str, str], int | None]]] = {}   # bench -> config -> query -> rank
        self.task : dict[tuple[str, str], str] = {}
        for bench in ("A", "B") :
            path = folder / f"rank_matrix_{bench}.csv"
            if (not path.exists()) :
                continue
            rows = list(csv.DictReader(path.open(encoding = "utf-8")))
            configs = [c for c in (rows[0].keys() if rows else []) if c not in ("dataset", "query_key", "task_type", "reference_video", "flags") and " flip@" not in c]
            table : dict[str, dict] = {c : {} for c in configs}
            for r in rows :
                q = (r["dataset"], r["query_key"])
                self.task[q] = r["task_type"]
                for c in configs :
                    if (r[c] == "" and c not in table) :
                        continue
                    table[c][q] = int(float(r[c])) if r[c] else None
            self.ranks[bench] = table
        self.by_code = {name.split()[0] : name for table in self.ranks.values() for name in table}

    def ranks_of(self, code : str, bench : str, task : str | None = None) -> list[int | None] :
        name = self.by_code.get(code)
        table = self.ranks.get(bench, {}).get(name or "", {})
        # A configuration restricted to TRAKE queries has blanks elsewhere: keep only the queries it ran on.
        return [rank for q, rank in table.items() if task is None or self.task[q] == task]


def metrics(ranks : list[int | None]) -> dict[str, float] | None :
    if (not ranks) :
        return None
    n = len(ranks)
    hit = lambda k : 100.0 * sum(1 for r in ranks if r is not None and r <= k) / n   # noqa: E731
    return {"H@1" : hit(1), "R@5" : hit(5), "R@10" : hit(10), "MRR" : sum(1.0 / r for r in ranks if r) / n, "n" : n}


def fmt(value : float | None, metric : str, best : bool) -> str :
    if (value is None) :
        return "--"
    text = f"{value:.3f}" if metric == "MRR" else f"{value:.1f}"
    return f"$\\mathbf{{{text}}}$" if best else f"${text}$"


def latex(caption : str, label : str, row_names : list[str], cells : list[list[dict | None]], groups : list[str], wide : bool) -> str :
    """cells[row][group] = metrics dict; bold marks the best value per column (ties all bold)."""
    best = {}
    for g in range(len(groups)) :
        for m in METRICS :
            values = [round(c[g][m], 6) for c in cells if c[g] is not None]
            best[(g, m)] = max(values) if values else None
    cols = "l" + "|cccc" * len(groups)
    head1 = " & " + " & ".join(f"\\multicolumn{{4}}{{c{'|' if i < len(groups) - 1 else ''}}}{{{g}}}" for i, g in enumerate(groups)) + " \\\\"
    head2 = " & " + " & ".join(" & ".join(METRICS) for _ in groups) + " \\\\"
    body = []
    for name, row in zip(row_names, cells) :
        parts = []
        for g, cell in enumerate(row) :
            for m in METRICS :
                value = None if cell is None else cell[m]
                parts.append(fmt(value, m, value is not None and round(value, 6) == best[(g, m)]))
        body.append(f"{name} & " + " & ".join(parts) + " \\\\")
    tabular = "\n".join([f"\\begin{{tabular}}{{{cols}}}", "\\hline", head1, head2, "\\hline", *body, "\\hline", "\\end{tabular}"])
    if (wide) :
        tabular = f"\\resizebox{{\\columnwidth}}{{!}}{{%\n{tabular}\n}}"
    return "\n".join([
        "\\begin{table}[t]", "\\centering", "\\small", "\\renewcommand{\\arraystretch}{1.35}", "\\setlength{\\tabcolsep}{5pt}",
        f"\\caption{{{caption}}}", f"\\label{{{label}}}", tabular, "\\end{table}", "",
    ])


def main() -> int :
    parser = argparse.ArgumentParser(description = __doc__.split("\n")[0])
    parser.add_argument("--run-dir", required = True, help = "the core3 run folder")
    parser.add_argument("--final-dir", default = None, help = "the final_table run folder (components table)")
    parser.add_argument("--visual-text", default = "sentence", choices = tuple(OFF_CODES), help = "text of the visual table")
    parser.add_argument("--out", default = None)
    args = parser.parse_args()
    core = Run(Path(args.run_dir))
    out = Path(args.out) if args.out else core.folder / "paper_tables"
    out.mkdir(parents = True, exist_ok = True)
    sources : list[dict[str, str]] = []

    def grab(run : Run, code : str, bench : str, table : str, row : str, task : str | None = None) -> dict | None :
        value = metrics(run.ranks_of(code, bench, task))
        sources.append({"table" : table, "row" : row, "bench" : bench, "run" : run.folder.name, "config" : run.by_code.get(code, f"MISSING {code}"),
                        "n" : str(value["n"]) if value else "0"})
        return value

    def ab(run : Run, codes : list[str], names : list[str], table : str) -> list[list[dict | None]] :
        return [[grab(run, c, "A", table, n), grab(run, c, "B", table, n)] for c, n in zip(codes, names)]

    groups = ["Benchmark A (dev.)", "Benchmark B (held out)"]
    text = args.visual_text
    (out / "visual.tex").write_text(latex(
        f"Video-level retrieval by encoder set ({TEXT_NAME[text]} text).", "tab:visual",
        SETS, ab(core, OFF_CODES[text], SETS, "visual"), groups, True), encoding = "utf-8")

    names, codes = [], []
    for i in (0, 1, 2, 6) :
        for policy in ("sentence", "keywords", "plain") :
            names.append(f"{SETS[i]}, {TEXT_NAME[policy]}")
            codes.append(OFF_CODES[policy][i])
    (out / "text_step.tex").write_text(latex(
        "Query text: the two Expand outputs against plain translation.", "tab:text", names, ab(core, codes, names, "text_step"), groups, True), encoding = "utf-8")

    trake_rows, trake_cells = [], []
    for policy, (tn, whole) in (("sentence", ("T01", "T02b")), ("plain", ("T01g", "T02g")), ("keywords", ("T01k", "T02k"))) :
        for label, code in (("Whole-description ensemble search", whole), ("TRAKE-N (event-wise search)", tn)) :
            row = f"{label}, {TEXT_NAME[policy]}"
            pooled = core.ranks_of(code, "A", "TRAKE") + core.ranks_of(code, "B", "TRAKE")
            value = metrics(pooled)
            sources.append({"table" : "trake", "row" : row, "bench" : "A+B", "run" : core.folder.name, "config" : core.by_code.get(code, f"MISSING {code}"), "n" : str(len(pooled))})
            trake_rows.append(row)
            trake_cells.append([value])
    (out / "trake.tex").write_text(latex("TRAKE queries (A and B pooled).", "tab:trake", trake_rows, trake_cells, ["TRAKE queries"], False), encoding = "utf-8")

    names = [f"{s}, rerank {state}" for s in SETS for state in ("on", "off")]
    codes = [c for on, off in zip(ON_CODES, OFF_CODES["sentence"]) for c in (on, off)]
    (out / "rerank_onoff.tex").write_text(latex(
        "Supplement: shipped neighbour rerank on and off (Expand sentence).", "tab:rerank-onoff", names, ab(core, codes, names, "rerank_onoff"), groups, True), encoding = "utf-8")

    if (args.final_dir) :
        final = Run(Path(args.final_dir))
        rows = [(code, name.split(" ", 1)[1]) for code, name in sorted(final.by_code.items()) if code.startswith("F")]
        labels = ["Full system" if code == "F01" else label[0].upper() + label[1 :] for code, label in rows]
        (out / "components.tex").write_text(latex(
            "Component ablation: the full system and one component changed at a time.", "tab:components",
            labels, ab(final, [c for c, _ in rows], labels, "components"), groups, True), encoding = "utf-8")

    with (out / "sources.csv").open("w", encoding = "utf-8", newline = "") as handle :
        writer = csv.DictWriter(handle, fieldnames = ["table", "row", "bench", "run", "config", "n"])
        writer.writeheader()
        writer.writerows(sources)
    missing = [s for s in sources if s["config"].startswith("MISSING")]
    print(f"wrote {len(list(out.glob('*.tex')))} tables to {out}; {len(sources)} cells, {len(missing)} missing")
    for s in missing[ : 10] :
        print(f"  MISSING {s['table']} / {s['row']} / {s['bench']}: {s['config']}")
    return 0 if not missing else 1


if (__name__ == "__main__") :
    raise SystemExit(main())
