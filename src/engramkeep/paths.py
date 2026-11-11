"""Filesystem helpers: strict path jail, atomic writes, private directories."""

from __future__ import annotations

import contextlib
import os
import re
import stat
import sys
import tempfile
import threading
import time
import unicodedata
from collections.abc import Iterator
from pathlib import Path

from .errors import PathSafetyError, ValidationError

if sys.platform == "win32":
    import msvcrt
else:
    import fcntl

_THREAD_LOCKS_GUARD = threading.Lock()
_THREAD_LOCKS: dict[str, threading.RLock] = {}

_WINDOWS_RESERVED = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}
_INVALID_CHARS = set('<>:"/\\|?*')
_MAX_PROJECT_ID = 64
_PROJECT_ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def _validate_component(part: str) -> None:
    """Validate a single path component for cross-platform safety."""
    if not isinstance(part, str):
        raise PathSafetyError("path components must be strings")
    if not part or part in {".", ".."}:
        raise PathSafetyError(f"invalid path component: {part!r}")
    if "\x00" in part or any(ord(char) < 32 for char in part):
        raise PathSafetyError("path component contains control characters")
    if any(char in _INVALID_CHARS for char in part):
        raise PathSafetyError(f"path component contains a separator or invalid character: {part!r}")
    if part != part.strip() or part.endswith("."):
        raise PathSafetyError(f"path component has unsafe leading/trailing characters: {part!r}")
    if len(part) > 255:
        raise PathSafetyError("path component is too long")
    stem = part.split(".", 1)[0].upper()
    if stem in _WINDOWS_RESERVED:
        raise PathSafetyError(f"reserved Windows filename: {part!r}")


def _ensure_within(root: Path, candidate: Path) -> None:
    """Raise when ``candidate`` is not inside ``root``."""
    root_text = os.path.normcase(str(root))
    candidate_text = os.path.normcase(str(candidate))
    try:
        common = os.path.commonpath([root_text, candidate_text])
    except ValueError as exc:
        raise PathSafetyError(f"path escapes the memory directory: {candidate}") from exc
    if common != root_text:
        raise PathSafetyError(f"path escapes the memory directory: {candidate}")


def safe_join(root: Path | str, *parts: str) -> Path:
    """Join validated components to ``root`` and prove the result stays inside.

    The function rejects absolute paths, separators inside a component,
    traversal segments, control characters, and reserved Windows names.
    Symlinks are resolved, so a link pointing outside ``root`` is rejected.
    """
    root_path = Path(root).expanduser().resolve()
    if not parts:
        return root_path

    candidate = root_path
    for part in parts:
        _validate_component(part)
        candidate = candidate / part

    resolved = candidate.resolve()
    _ensure_within(root_path, resolved)
    return resolved


def normalize_project_id(value: str) -> str:
    """Turn a user-supplied project name into a safe file stem."""
    if not isinstance(value, str):
        raise ValidationError("project name must be a string")
    raw = value.strip()
    if not raw:
        raise ValidationError("project name must not be empty")
    if "\x00" in raw or any(ord(char) < 32 for char in raw):
        raise ValidationError("project name contains control characters")
    if any(char in "/\\:" for char in raw) or ".." in raw:
        raise ValidationError(f"invalid project name: {value!r}")

    transliterated = raw.translate(str.maketrans({"ı": "i", "İ": "I"}))
    ascii_text = (
        unicodedata.normalize("NFKD", transliterated).encode("ascii", "ignore").decode("ascii")
    )
    normalized = re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-")
    if not normalized:
        raise ValidationError("project name must contain ASCII letters or digits")
    if len(normalized) > _MAX_PROJECT_ID:
        raise ValidationError(f"project name is longer than {_MAX_PROJECT_ID} characters")
    if not _PROJECT_ID_RE.match(normalized):
        raise ValidationError(f"invalid project name: {value!r}")
    if normalized.split(".", 1)[0].upper() in _WINDOWS_RESERVED:
        raise ValidationError(f"reserved project name: {value!r}")
    return normalized


def display_title(project_id: str) -> str:
    """Return a human-readable title for a project id."""
    words = [word.capitalize() for word in project_id.split("-") if word]
    return " ".join(words) or project_id


def strip_control_chars(text: str, *, preserve_newlines: bool = False) -> str:
    """Remove C0/C1/DEL control and format/bidi (Cf) characters."""
    out: list[str] = []
    for ch in text:
        code = ord(ch)
        if ch in ("\n", "\r", "\t"):
            out.append(ch if preserve_newlines else " ")
        elif (
            code >= 32
            and code != 127
            and not 0x80 <= code <= 0x9F
            and unicodedata.category(ch) != "Cf"
        ):
            out.append(ch)
    return "".join(out)


def ensure_private_dir(path: Path | str) -> Path:
    """Create a directory tree and best-effort restrict it to the current user."""
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    with contextlib.suppress(OSError):
        os.chmod(path, 0o700)
    return path


def replace_file(src: Path | str, dst: Path | str, *, retries: int = 10) -> None:
    """Atomically replace ``dst`` with ``src``, retrying transient Windows locks."""
    src_path = Path(src)
    dst_path = Path(dst)
    for attempt in range(retries):
        try:
            os.replace(src_path, dst_path)
            return
        except PermissionError:
            if attempt >= retries - 1:
                raise
            time.sleep(min(0.05, 0.005 * (attempt + 1)))


def _thread_lock_for(key: str) -> threading.RLock:
    with _THREAD_LOCKS_GUARD:
        lock = _THREAD_LOCKS.get(key)
        if lock is None:
            lock = threading.RLock()
            _THREAD_LOCKS[key] = lock
        return lock


_LOCK_STATE = threading.local()


@contextlib.contextmanager
def file_lock(lock_path: Path | str, *, timeout: float = 10.0) -> Iterator[None]:
    """Serialize mutations across threads and processes using an advisory lock."""
    path = Path(lock_path)
    if path.is_symlink():
        raise PathSafetyError(f"refusing to lock through a symlink: {path}")
    key = os.path.normcase(str(path.resolve()))
    rlock = _thread_lock_for(key)

    depths: dict[str, int] = getattr(_LOCK_STATE, "depths", {})
    if not hasattr(_LOCK_STATE, "depths"):
        _LOCK_STATE.depths = depths

    with rlock:
        depth = depths.get(key, 0)
        if depth > 0:
            depths[key] = depth + 1
            try:
                yield
            finally:
                depths[key] = depth
            return

        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a+b") as handle:
            if sys.platform == "win32":
                handle.seek(0, os.SEEK_END)
                if handle.tell() == 0:
                    handle.write(b"\0")
                    handle.flush()
                deadline = time.monotonic() + timeout
                while True:
                    handle.seek(0)
                    try:
                        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                        break
                    except OSError:
                        if time.monotonic() >= deadline:
                            raise
                        time.sleep(0.01)
            else:
                deadline = time.monotonic() + timeout
                while True:
                    try:
                        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                        break
                    except BlockingIOError:
                        if time.monotonic() >= deadline:
                            raise TimeoutError(f"timed out waiting for lock: {path}") from None
                        time.sleep(0.01)

            depths[key] = 1
            try:
                yield
            finally:
                depths.pop(key, None)
                if sys.platform == "win32":
                    with contextlib.suppress(OSError):
                        handle.seek(0)
                        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    with contextlib.suppress(OSError):
                        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def atomic_write_text(
    path: Path | str,
    text: str,
    *,
    mode: int | None = 0o600,
    private_parent: bool = False,
) -> Path:
    """Write UTF-8 text atomically using a temporary file and ``os.replace``."""
    path = Path(path)
    if not path.name:
        raise PathSafetyError(f"invalid output path: {path}")
    if private_parent:
        ensure_private_dir(path.parent)
    else:
        path.parent.mkdir(parents=True, exist_ok=True)

    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent)
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        if mode is not None:
            with contextlib.suppress(OSError):
                os.chmod(temporary, mode)
        replace_file(temporary, path)
        if mode is not None:
            with contextlib.suppress(OSError):
                os.chmod(path, mode)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(temporary)
        raise
    return path


def append_text(
    path: Path | str,
    text: str,
    *,
    mode: int | None = 0o600,
    private_parent: bool = True,
) -> Path:
    """Append UTF-8 text to a regular file, rejecting symlinks."""
    path = Path(path)
    if path.is_symlink():
        raise PathSafetyError(f"refusing to append through a symlink: {path}")
    if private_parent:
        ensure_private_dir(path.parent)
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())
    if mode is not None:
        with contextlib.suppress(OSError):
            os.chmod(path, mode)
    return path


def is_private_path(path: Path | str) -> bool:
    """Return True when a path is not group/world accessible.

    Windows ACLs are not represented by POSIX mode bits, so this check is
    treated as satisfied there.
    """
    if os.name == "nt":
        return True
    try:
        mode = stat.S_IMODE(Path(path).stat().st_mode)
    except OSError:
        return False
    return (mode & 0o077) == 0
