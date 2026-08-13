from __future__ import annotations

import os
from pathlib import Path
from tempfile import gettempdir


BACKEND_ROOT = Path(__file__).resolve().parents[2]
VERCEL_CACHE_ROOT = Path(gettempdir()) / "valuator"


def runtime_cache_path(*parts: str) -> Path:
    """Return a writable cache path for the current runtime.

    Vercel Functions ship an immutable source bundle and only permit writes
    beneath /tmp. Local and container deployments keep the existing project
    cache layout.
    """

    root = VERCEL_CACHE_ROOT if os.getenv("VERCEL") == "1" else BACKEND_ROOT / ".cache"
    return root.joinpath(*parts)
