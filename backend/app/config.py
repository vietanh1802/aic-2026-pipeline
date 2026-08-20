# -*- coding: utf-8 -*-
"""The two settings the collaboration layer needs.

dev's config.py carries production guards, demo forcing and cache limits that
this branch has no use for. Everything else on this branch still reads
os.environ directly; adding a settings object for the whole app would be a
refactor, not a feature.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent


@dataclass(frozen=True)
class Settings:
    db_path: Path
    session_ttl_days: int


def load_settings() -> Settings:
    return Settings(
        db_path=Path(os.environ.get("AIC_DB_PATH", BASE_DIR / "data" / "app.db")),
        # Long on purpose: a round runs for hours and a token that dies in the
        # middle of one is a live failure. Revocation is by deleting rows.
        session_ttl_days=int(os.environ.get("AIC_SESSION_TTL_DAYS", "30")),
    )
