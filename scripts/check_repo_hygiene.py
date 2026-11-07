#!/usr/bin/env python3
"""Repository hygiene checks for Engramkeep.

This is a guardrail, not a security boundary. It catches common mistakes:
personal paths, forbidden names, high-confidence secrets, unsafe artifacts,
symlinks, and dangerous runtime calls.
"""

from __future__ import annotations

import argparse
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

SKIP_DIRS = {
    ".git",
    ".venv",
    "venv",
    "build",
    "dist",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
    ".idea",
    ".vscode",
}

REQUIRED_FILES = [
    "LICENSE",
    "README.md",
    "README.tr.md",
    "AGENTS.md",
    "pyproject.toml",
    "CONTRIBUTING.md",
    "CODE_OF_CONDUCT.md",
    "SECURITY.md",
    "CHANGELOG.md",
    "TRADEMARKS.md",
    ".gitignore",
    ".gitattributes",
    ".editorconfig",
    "docs/ARCHITECTURE.md",
    "docs/PRIVACY.md",
    "docs/THREAT_MODEL.md",
    "docs/COMPATIBILITY.md",
    "docs/ROADMAP.md",
    "skills/engramkeep/SKILL.md",
    "templates/agents/AGENTS.md",
    "examples/brain/meta.json",
    "examples/brain/projects/example-project.md",
    "scripts/check_repo_hygiene.py",
    ".github/workflows/ci.yml",
]

FORBIDDEN_NAMES = [
    "KEN" + "AN",
    "universal-" + "agent-" + "brain",
]

USER_PATH_PATTERNS = [
    ("Windows user path", re.compile(r"C:[\\/]+Users[\\/]+([A-Za-z0-9._-]+)", re.IGNORECASE)),
    ("macOS user path", re.compile(r"/Users/([A-Za-z0-9._-]+)")),
    ("Linux home path", re.compile(r"/home/([A-Za-z0-9._-]+)")),
]
ALLOWED_USER_NAMES = {
    "example",
    "user",
    "test",
    "public",
    "shared",
    "runner",
    "username",
    "<username>",
    "%username%",
}

SECRET_PATTERNS = [
    ("OpenAI-style key", re.compile(r"\bsk-[A-Za-z0-9_-]{32,}\b")),
    ("Anthropic-style key", re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}\b")),
    ("GitHub token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b")),
    ("Google API key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")),
    ("AWS access key id", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("Slack token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b")),
    ("JWT", re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b")),
    ("private key block", re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----")),
]

PRIVATE_SUFFIXES = {
    ".pem",
    ".key",
    ".p12",
    ".pfx",
    ".sqlite",
    ".sqlite3",
    ".db",
    ".zip",
    ".tar",
    ".gz",
    ".7z",
    ".rar",
    ".log",
}
PRIVATE_NAMES = {"id_rsa", "id_ed25519", "credentials", "secrets.json", ".env"}
ALLOWED_PRIVATE_FILES = {"examples/brain/audit.log"}

DANGEROUS_CODE = [
    (r"\beval\s*\(", "eval"),
    (r"\bexec\s*\(", "exec"),
    (r"\bpickle\.", "pickle"),
    (r"shell\s*=\s*True", "shell=True"),
    (r"\bos\.system\s*\(", "os.system"),
]


def iter_files(root: Path) -> list[Path]:
    """Return regular files, skipping generated and vendor directories."""
    files: list[Path] = []
    for path in root.rglob("*"):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.is_symlink():
            continue
        if path.is_file():
            files.append(path)
    return files


def relative(root: Path, path: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def read_text(path: Path) -> str | None:
    try:
        raw = path.read_bytes()
    except OSError:
        return None
    if b"\x00" in raw:
        return None
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return None


def check_required(root: Path, failures: list[str]) -> None:
    for name in REQUIRED_FILES:
        if not (root / name).is_file():
            failures.append(f"missing required file: {name}")


def check_license(root: Path, failures: list[str]) -> None:
    text = (root / "LICENSE").read_text(encoding="utf-8")
    if "MIT License" not in text:
        failures.append("LICENSE does not contain 'MIT License'")
    if "The Engramkeep Contributors" not in text:
        failures.append("LICENSE does not name 'The Engramkeep Contributors'")


def check_gitignore(root: Path, failures: list[str]) -> None:
    text = (root / ".gitignore").read_text(encoding="utf-8")
    for needle in ("__pycache__/", ".env", "*.pem", "brain/"):
        if needle not in text:
            failures.append(f".gitignore is missing {needle!r}")


def check_private_artifacts(root: Path, files: list[Path], failures: list[str]) -> None:
    for path in files:
        rel = relative(root, path).replace("\\", "/")
        if rel in ALLOWED_PRIVATE_FILES:
            continue
        name = path.name.lower()
        if name in PRIVATE_NAMES or name.startswith(".env."):
            failures.append(f"private artifact: {rel}")
            continue
        if path.suffix.lower() in PRIVATE_SUFFIXES:
            failures.append(f"private artifact: {rel}")


def check_symlinks(root: Path, failures: list[str]) -> None:
    for path in root.rglob("*"):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.is_symlink():
            failures.append(f"symlink is not allowed: {relative(root, path)}")
        elif hasattr(os.path, "isjunction") and os.path.isjunction(path):
            failures.append(f"junction is not allowed: {relative(root, path)}")


def check_text(root: Path, files: list[Path], failures: list[str]) -> None:
    for path in files:
        text = read_text(path)
        if text is None:
            continue
        rel = relative(root, path)
        lowered = text.lower()
        for name in FORBIDDEN_NAMES:
            if name.lower() in lowered:
                failures.append(f"forbidden name {name!r} in {rel}")
        for label, pattern in USER_PATH_PATTERNS:
            for match in pattern.finditer(text):
                user = match.group(1)
                if user.lower() not in ALLOWED_USER_NAMES:
                    failures.append(f"{label} in {rel}")
        for label, pattern in SECRET_PATTERNS:
            if pattern.search(text):
                failures.append(f"possible {label} in {rel}")


def check_source_code(root: Path, failures: list[str]) -> None:
    source = root / "src" / "engramkeep"
    if not source.is_dir():
        failures.append("missing src/engramkeep")
        return
    for path in source.rglob("*.py"):
        text = read_text(path)
        if text is None:
            continue
        rel = relative(root, path)
        for pattern, label in DANGEROUS_CODE:
            if re.search(pattern, text):
                failures.append(f"dangerous call {label!r} in {rel}")


def run(root: Path) -> list[str]:
    failures: list[str] = []
    files = iter_files(root)
    check_required(root, failures)
    check_license(root, failures)
    check_gitignore(root, failures)
    check_private_artifacts(root, files, failures)
    check_symlinks(root, failures)
    check_text(root, files, failures)
    check_source_code(root, failures)
    return failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check repository hygiene.")
    parser.add_argument("--root", type=Path, default=ROOT, help="repository root")
    args = parser.parse_args(argv)
    root = args.root.expanduser().resolve()

    print("Engramkeep repository hygiene check")
    print(f"Root: {root}")
    failures = run(root)
    if failures:
        for failure in failures:
            print(f"[fail] {failure}")
        print(f"FAILED: {len(failures)} issue(s)")
        return 1
    print("OK: no issues found")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
