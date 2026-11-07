"""Repository hygiene regression test."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[1]


def _load_hygiene() -> ModuleType:
    path = ROOT / "scripts" / "check_repo_hygiene.py"
    spec = importlib.util.spec_from_file_location("engramkeep_hygiene", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_repository_hygiene() -> None:
    module = _load_hygiene()
    failures = module.run(ROOT)
    assert failures == [], "\n".join(failures)
