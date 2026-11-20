"""Static assets for the hardened local Engramkeep dashboard."""

from __future__ import annotations

import importlib.resources


def load_asset(name: str) -> str:
    """Read a UTF-8 dashboard asset from the installed package."""
    return importlib.resources.files(__name__).joinpath(name).read_text(encoding="utf-8")
