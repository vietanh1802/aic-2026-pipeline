# scripts/ablation_analysis/tablefmt.py
"""One Table object written three ways: CSV (numbers), LaTeX (the paper) and Markdown (reading).

LaTeX follows backend/app/evaluation/report.latex_table: tabular with \\hline, no booktabs, a caption above
the table as in the paper's LNCS tables, best value in bold. A SYNTHETIC or SMOKE stamp goes into the
caption, the Markdown title and the first line of the CSV, so such a table cannot be mistaken for a result.
"""
from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_LATEX_SPECIAL = {"&" : r"\&", "%" : r"\%", "$" : r"\$", "#" : r"\#", "_" : r"\_", "{" : r"\{", "}" : r"\}",
                  "~" : r"\textasciitilde{}", "^" : r"\textasciicircum{}", "\\" : r"\textbackslash{}"}


def latex_escape(text : str) -> str :
    return re.sub(r"[&%$#_{}~^\\]", lambda m : _LATEX_SPECIAL[m.group(0)], str(text))


def pct(x : float | None, digits : int = 1) -> str :
    return "" if x is None or x != x else f"{100 * x:.{digits}f}"


def num(x : float | None, digits : int = 3) -> str :
    return "" if x is None or x != x else f"{x:.{digits}f}"


def interval(low : float | None, high : float | None, scale : float = 100.0, digits : int = 1) -> str :
    if (low is None or high is None or low != low or high != high) :
        return ""
    return f"[{low * scale:.{digits}f}, {high * scale:.{digits}f}]"


def fmt_p(p : float | None) -> str :
    if (p is None or p != p) :
        return ""
    return "<0.001" if p < 0.001 else f"{p:.3f}"


@dataclass
class Table :
    id : str                              # "T3"
    slug : str                            # file stem, "T3_encoder_grid"
    caption : str
    columns : list[str]
    rows : list[list[str]]
    align : str = ""                      # tabular column spec, default l then r
    notes : list[str] = field(default_factory = list)
    bold : set[tuple[int, int]] = field(default_factory = set)   # (row, column) cells to bold in LaTeX and Markdown
    group_header : list[tuple[str, int]] | None = None           # first header row, (label, columns spanned)
    records : list[dict[str, Any]] | None = None                 # numeric rows for the CSV; default: the displayed rows
    small : bool = False                  # \scriptsize for wide tables

    @property
    def label(self) -> str :
        return "tab:" + self.slug.lower().replace("-", "_")

    def _caption(self, stamp : str) -> str :
        return (f"[{stamp}] " if stamp else "") + self.caption

    def to_latex(self, stamp : str = "") -> str :
        spec = self.align or ("l" + "r" * (len(self.columns) - 1))
        lines = []
        if (stamp) :
            lines.append(f"% {stamp}: these numbers are not results")
        lines += [r"\begin{table}[t]", rf"\caption{{{latex_escape(self._caption(stamp))}}}", rf"\label{{{self.label}}}", r"\centering"]
        if (self.small) :
            lines += [r"\scriptsize", r"\setlength{\tabcolsep}{3pt}"]
        lines += [rf"\begin{{tabular}}{{{spec}}}", r"\hline"]
        if (self.group_header) :
            cells = [rf"\multicolumn{{{span}}}{{c}}{{{latex_escape(label)}}}" if label or span > 1 else "" for label, span in self.group_header]
            lines += [" & ".join(cells) + r" \\", r"\hline"]
        lines += [" & ".join(latex_escape(c) for c in self.columns) + r" \\", r"\hline"]
        for r, row in enumerate(self.rows) :
            cells = [rf"\textbf{{{latex_escape(c)}}}" if (r, i) in self.bold else latex_escape(c) for i, c in enumerate(row)]
            lines.append(" & ".join(cells) + r" \\")
        lines += [r"\hline", r"\end{tabular}"]
        if (self.notes) :
            lines.append(r"\par\smallskip{\footnotesize " + latex_escape(" ".join(self.notes)) + "}")
        lines.append(r"\end{table}")
        return "\n".join(lines) + "\n"

    def to_markdown(self, stamp : str = "") -> str :
        def cell(r : int, i : int, text : str) -> str :
            text = str(text).replace("|", "/")
            return f"**{text}**" if (r, i) in self.bold and text else text
        out = [f"### {self.id}. {self._caption(stamp)}", ""]
        if (self.group_header) :
            out.append("| " + " | ".join(cell for label, span in self.group_header for cell in [label, *[""] * (span - 1)]) + " |")
        out.append("| " + " | ".join(self.columns) + " |")
        out.append("|" + "|".join("---" for _ in self.columns) + "|")
        out += ["| " + " | ".join(cell(r, i, c) for i, c in enumerate(row)) + " |" for r, row in enumerate(self.rows)]
        if (self.notes) :
            out += ["", *[f"- {n}" for n in self.notes]]
        return "\n".join(out) + "\n"

    def to_csv(self, stamp : str = "") -> str :
        buffer = io.StringIO()
        if (stamp) :
            buffer.write(f"# {stamp}: these numbers are not results\n")
        if (self.records is not None) :
            fields = list(self.records[0]) if self.records else self.columns
            writer = csv.DictWriter(buffer, fieldnames = fields, lineterminator = "\n", extrasaction = "ignore")
            writer.writeheader()
            for rec in self.records :
                writer.writerow({f : ("" if rec.get(f) is None else rec[f]) for f in fields})
        else :
            writer = csv.writer(buffer, lineterminator = "\n")
            writer.writerow(self.columns)
            writer.writerows(self.rows)
        return buffer.getvalue()

    def write(self, folder : Path, stamp : str = "") -> None :
        folder.mkdir(parents = True, exist_ok = True)
        (folder / f"{self.slug}.csv").write_text(self.to_csv(stamp), encoding = "utf-8")
        (folder / f"{self.slug}.tex").write_text(self.to_latex(stamp), encoding = "utf-8")
        (folder / f"{self.slug}.md").write_text(self.to_markdown(stamp), encoding = "utf-8")


def best_cells(rows : list[list[str]], columns : list[int], values : list[list[float | None]], higher_is_better : bool = True) -> set[tuple[int, int]] :
    """(row, column) of the best value of each listed column, every tie included. values[r][c] is numeric."""
    bold : set[tuple[int, int]] = set()
    for c in columns :
        column = [v[c] for v in values if v[c] is not None and v[c] == v[c]]
        if (not column) :
            continue
        target = max(column) if higher_is_better else min(column)
        bold |= {(r, c) for r, v in enumerate(values) if v[c] is not None and v[c] == v[c] and round(v[c], 6) == round(target, 6)}
    return bold
