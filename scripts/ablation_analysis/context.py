# scripts/ablation_analysis/context.py
"""What every table and figure builder receives: the run data, optional features, labels and facts."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ablation_analysis.data import ConfigInfo, RunData
from ablation_analysis.features import Features


def natural_key(code : str) -> tuple[str, int, str] :
    match = re.match(r"^([A-Z]+)(\d+)([a-z]?)", code)
    return (match.group(1), int(match.group(2)), match.group(3)) if match else (code, 0, "")


@dataclass
class Ctx :
    data : RunData
    features : Features | None
    labels : list[dict[str, str]] | None
    facts : dict[str, Any]
    out : Path
    images_dir : Path | None = None
    skipped : list[str] = field(default_factory = list)    # analyses that could not run, and why

    @property
    def stamp(self) -> str :
        return self.data.stamp

    @property
    def base(self) -> str :
        code = self.data.code_for("base")
        if (code is None) :
            raise ValueError("no baseline configuration (all three encoders, rerank per_model, the text policy of C01) in this run folder")
        return code

    def codes(self, *prefixes : str) -> list[str] :
        """Configuration codes whose role starts with one of the prefixes, in code order."""
        picked = [c for c, info in self.data.configs.items() if not prefixes or info.role.startswith(prefixes)]
        return sorted(picked, key = natural_key)

    def retrieval_codes(self) -> list[str] :
        """Every ablation arm that searched the whole query text: everything except the TRAKE task modes and the
        sanity checks (raw Vietnamese), which are shown in their own small table."""
        return sorted((c for c, info in self.data.configs.items() if not info.role.startswith("trake") and not info.sanity), key = natural_key)

    def sanity_codes(self) -> list[str] :
        return sorted((c for c, info in self.data.configs.items() if info.sanity), key = natural_key)

    def info(self, code : str) -> ConfigInfo :
        return self.data.configs[code]

    def name(self, code : str) -> str :
        return self.data.configs[code].name

    def skip(self, what : str, why : str) -> None :
        self.skipped.append(f"{what}: {why}")
