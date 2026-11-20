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


def test_check_parity_catches_changelog_and_security_drift(tmp_path: Path) -> None:
    module = _load_hygiene()
    (tmp_path / "src" / "engramkeep" / "data").mkdir(parents=True)
    (tmp_path / "skills" / "engramkeep").mkdir(parents=True)
    (tmp_path / "pyproject.toml").write_text('[project]\nversion = "2.3.1"\n', encoding="utf-8")
    (tmp_path / "src" / "engramkeep" / "__init__.py").write_text(
        '__version__ = "2.3.1"\n', encoding="utf-8"
    )
    (tmp_path / "skills" / "engramkeep" / "SKILL.md").write_text("same\n", encoding="utf-8")
    (tmp_path / "src" / "engramkeep" / "data" / "SKILL.md").write_text("same\n", encoding="utf-8")
    (tmp_path / "CHANGELOG.md").write_text("## [2.3.0] - 2026-01-01\n", encoding="utf-8")
    (tmp_path / "SECURITY.md").write_text("| 1.0.x | Yes |\n", encoding="utf-8")

    failures: list[str] = []
    module.check_parity(tmp_path, failures)
    assert any("CHANGELOG.md" in item for item in failures)
    assert any("SECURITY.md" in item for item in failures)

    (tmp_path / "CHANGELOG.md").write_text("## [2.3.1] - 2026-01-02\n", encoding="utf-8")
    (tmp_path / "SECURITY.md").write_text("| 2.3.x | Yes |\n", encoding="utf-8")
    ok_failures: list[str] = []
    module.check_parity(tmp_path, ok_failures)
    assert ok_failures == []
