"""Resolve the local Engramkeep data directory.

Precedence is intentionally simple and explicit:

1. the ``--home`` command-line value,
2. the ``ENGRAMKEEP_HOME`` environment variable,
3. a platform-specific default.
"""

from __future__ import annotations

import os
import platform
from collections.abc import Mapping
from pathlib import Path

from .errors import ConfigError

APP_NAME = "engramkeep"
DISPLAY_NAME = "Engramkeep"
ENV_HOME = "ENGRAMKEEP_HOME"
SCHEMA_VERSION = 1


def platform_default_home(
    *,
    system: str | None = None,
    env: Mapping[str, str] | None = None,
    user_home: Path | None = None,
) -> Path:
    """Return the platform-specific default data directory."""
    system = system or platform.system()
    env = os.environ if env is None else env
    user_home = Path.home() if user_home is None else Path(user_home)

    if system == "Windows":
        base = env.get("LOCALAPPDATA")
        root = Path(base) if base else user_home / "AppData" / "Local"
        return (root / DISPLAY_NAME).resolve()
    if system == "Darwin":
        return (user_home / "Library" / "Application Support" / DISPLAY_NAME).resolve()
    base = env.get("XDG_DATA_HOME")
    root = Path(base) if base else user_home / ".local" / "share"
    return (root / APP_NAME).resolve()


def resolve_home(
    cli_home: str | os.PathLike[str] | None = None,
    *,
    env: Mapping[str, str] | None = None,
    system: str | None = None,
    user_home: Path | None = None,
) -> Path:
    """Resolve the active memory home.

    An explicit command-line value wins over ``ENGRAMKEEP_HOME``, which wins
    over the platform default. Empty values are ignored.
    """
    env = os.environ if env is None else env
    raw: str | os.PathLike[str] | None = cli_home
    source = "command line"

    if raw is None or str(raw).strip() == "":
        raw = env.get(ENV_HOME)
        source = ENV_HOME
    if raw is None or str(raw).strip() == "":
        return platform_default_home(system=system, env=env, user_home=user_home)

    path = Path(raw).expanduser()
    try:
        resolved = path.resolve()
    except OSError as exc:
        raise ConfigError(f"cannot resolve {source} path: {path}") from exc

    if resolved == Path(resolved.anchor):
        raise ConfigError(f"{source} must not point at a filesystem root: {resolved}")
    if resolved.exists() and not resolved.is_dir():
        raise ConfigError(f"{source} is not a directory: {resolved}")
    return resolved
