"""Which build is running.

The VERSION file at the repo root is the single source of truth. The image only
copies backend/app, so CI bakes the value in as AIC_VERSION at build time and
reading the file is the local-development fallback.
"""

import os
from pathlib import Path

_FALLBACK = "0.0.0-dev"


def _from_repo_file():
    # backend/app/version.py -> backend/app -> backend -> repo root
    candidate = Path(__file__).resolve().parents[2] / "VERSION"
    try:
        text = candidate.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return text or None


VERSION = os.environ.get("AIC_VERSION") or _from_repo_file() or _FALLBACK
COMMIT = os.environ.get("AIC_COMMIT", "unknown")
SHORT_COMMIT = COMMIT[:7] if COMMIT != "unknown" else COMMIT
