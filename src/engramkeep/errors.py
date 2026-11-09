"""Exception hierarchy for Engramkeep."""

from __future__ import annotations


class EngramkeepError(Exception):
    """Base class for all expected Engramkeep errors."""


class ConfigError(EngramkeepError):
    """Raised when the memory home cannot be resolved or is invalid."""


class PathSafetyError(EngramkeepError):
    """Raised when a path would escape the memory directory."""


class ValidationError(EngramkeepError):
    """Raised when user input is invalid."""


class CardParseError(EngramkeepError):
    """Raised when a project card cannot be parsed."""


class StoreError(EngramkeepError):
    """Raised when a store operation cannot be completed."""


class InstallerError(EngramkeepError):
    """Raised when an agent integration cannot be planned or applied."""
