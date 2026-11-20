"""Optional encryption at rest for Engramkeep (``pip install 'engramkeep[crypto]'``).

Core Engramkeep keeps zero required runtime dependencies. When a user installs
the optional ``crypto`` extra (``cryptography``), this module provides AEAD
encryption (Scrypt KDF + AES-256-GCM) for project cards and the troubleshooting
registry using a UTF-8 JSON envelope format.

Passphrases are read from ``ENGRAMKEEP_PASSPHRASE`` or an interactive prompt —
never passed as plain CLI flags that leak into shell history or process lists.
"""

from __future__ import annotations

import base64
import getpass
import importlib
import importlib.util
import json
import os
import secrets
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .errors import CryptoError
from .models import utc_now_iso
from .paths import atomic_write_text, ensure_private_dir, file_lock, is_link_or_junction, safe_join

ENVELOPE_FORMAT = "engramkeep-enc-v1"
ENVELOPE_HEADER = "<!-- engramkeep:encrypted:v1 -->"
ENV_PASSPHRASE = "ENGRAMKEEP_PASSPHRASE"  # noqa: S105
_AAD = b"engramkeep-enc-v1"
_SCRYPT_N = 2**15
_SCRYPT_R = 8
_SCRYPT_P = 1
_MIN_SCRYPT_N = 2**10
_MAX_SCRYPT_N = 2**20
_MAX_SCRYPT_R = 32
_MAX_SCRYPT_P = 16
_KEY_BYTES = 32
_SALT_BYTES = 16
_NONCE_BYTES = 12


@dataclass
class CryptoStoreResult:
    """Outcome of encrypting or decrypting store files."""

    mode: str
    operation: str
    files_processed: list[str] = field(default_factory=list)
    files_skipped: list[str] = field(default_factory=list)
    backup_dir: Path | None = None

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable representation."""
        return {
            "mode": self.mode,
            "operation": self.operation,
            "files_processed": list(self.files_processed),
            "files_skipped": list(self.files_skipped),
            "backup_dir": str(self.backup_dir) if self.backup_dir else None,
        }


def crypto_available() -> bool:
    """Return True when the optional ``cryptography`` package is installed."""
    return importlib.util.find_spec("cryptography") is not None


def _require_crypto() -> tuple[Any, Any]:
    if not crypto_available():
        raise CryptoError(
            "optional encryption requires the 'crypto' extra; "
            "install with: pip install 'engramkeep[crypto]'"
        )
    aead = importlib.import_module("cryptography.hazmat.primitives.ciphers.aead")
    scrypt_mod = importlib.import_module("cryptography.hazmat.primitives.kdf.scrypt")
    return aead.AESGCM, scrypt_mod.Scrypt


def is_encrypted_text(text: str) -> bool:
    """Return True when ``text`` is an Engramkeep encrypted envelope."""
    return text.lstrip("\ufeff").startswith(ENVELOPE_HEADER)


def resolve_passphrase(
    passphrase: str | None = None,
    *,
    prompt: bool = False,
    confirm: bool = False,
) -> str:
    """Resolve a non-empty passphrase from argument, environment, or interactive prompt."""
    value = passphrase if passphrase is not None else os.environ.get(ENV_PASSPHRASE)
    if (value is None or not value) and prompt:
        first = getpass.getpass("Engramkeep passphrase: ")
        if confirm:
            second = getpass.getpass("Confirm passphrase: ")
            if first != second:
                raise CryptoError("passphrases do not match")
        value = first
    if not value or not value.strip():
        raise CryptoError(f"passphrase required; set {ENV_PASSPHRASE} or enter it interactively")
    return value


def _is_strict_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _validate_kdf_params(raw_params: object) -> tuple[int, int, int]:
    """Validate optional Scrypt KDF parameters from an envelope, falling back to v1 defaults."""
    if raw_params is None:
        return _SCRYPT_N, _SCRYPT_R, _SCRYPT_P
    if not isinstance(raw_params, dict):
        raise CryptoError("invalid KDF parameters in encryption envelope")
    n = raw_params.get("n")
    r = raw_params.get("r")
    p = raw_params.get("p")
    if not (_is_strict_int(n) and _is_strict_int(r) and _is_strict_int(p)):
        raise CryptoError("KDF parameters must be integers")
    assert isinstance(n, int) and isinstance(r, int) and isinstance(p, int)
    if n < _MIN_SCRYPT_N or n > _MAX_SCRYPT_N or (n & (n - 1)) != 0:
        raise CryptoError(
            f"unsupported Scrypt cost parameter n={n} (expected power of two in "
            f"[{_MIN_SCRYPT_N}, {_MAX_SCRYPT_N}])"
        )
    if not (1 <= r <= _MAX_SCRYPT_R):
        raise CryptoError(f"unsupported Scrypt block size r={r}")
    if not (1 <= p <= _MAX_SCRYPT_P):
        raise CryptoError(f"unsupported Scrypt parallelization p={p}")
    return n, r, p


def _derive_key(
    passphrase: str,
    salt: bytes,
    *,
    n: int = _SCRYPT_N,
    r: int = _SCRYPT_R,
    p: int = _SCRYPT_P,
) -> bytes:
    _, scrypt_cls = _require_crypto()
    kdf = scrypt_cls(salt=salt, length=_KEY_BYTES, n=n, r=r, p=p)
    derived: bytes = kdf.derive(passphrase.encode("utf-8"))
    return derived


def encrypt_text(plaintext: str, passphrase: str) -> str:
    """Encrypt UTF-8 text into a self-describing AEAD envelope."""
    if not passphrase:
        raise CryptoError("passphrase must not be empty")
    aesgcm_cls, _ = _require_crypto()
    salt = secrets.token_bytes(_SALT_BYTES)
    nonce = secrets.token_bytes(_NONCE_BYTES)
    key = _derive_key(passphrase, salt)
    ciphertext: bytes = aesgcm_cls(key).encrypt(nonce, plaintext.encode("utf-8"), _AAD)
    envelope = {
        "format": ENVELOPE_FORMAT,
        "kdf": "scrypt",
        "kdf_params": {"n": _SCRYPT_N, "r": _SCRYPT_R, "p": _SCRYPT_P},
        "salt": base64.b64encode(salt).decode("ascii"),
        "nonce": base64.b64encode(nonce).decode("ascii"),
        "ciphertext": base64.b64encode(ciphertext).decode("ascii"),
    }
    return f"{ENVELOPE_HEADER}\n{json.dumps(envelope, indent=2, sort_keys=True)}\n"


def decrypt_text(envelope_text: str, passphrase: str) -> str:
    """Decrypt an Engramkeep AEAD envelope back into UTF-8 plaintext."""
    if not is_encrypted_text(envelope_text):
        raise CryptoError("input is not an Engramkeep encrypted envelope")
    aesgcm_cls, _ = _require_crypto()
    lines = envelope_text.lstrip("\ufeff").splitlines()
    raw_json = "\n".join(lines[1:]).strip()
    try:
        envelope = json.loads(raw_json)
        if not isinstance(envelope, dict) or envelope.get("format") != ENVELOPE_FORMAT:
            raise CryptoError("unsupported encryption envelope format")
        if envelope.get("kdf", "scrypt") != "scrypt":
            raise CryptoError(f"unsupported KDF: {envelope.get('kdf')!r}")
        kdf_n, kdf_r, kdf_p = _validate_kdf_params(envelope.get("kdf_params"))
        salt = base64.b64decode(str(envelope["salt"]), validate=True)
        nonce = base64.b64decode(str(envelope["nonce"]), validate=True)
        ciphertext = base64.b64decode(str(envelope["ciphertext"]), validate=True)
    except CryptoError:
        raise
    except Exception as exc:
        raise CryptoError(f"corrupted encryption envelope: {exc}") from exc

    key = _derive_key(passphrase, salt, n=kdf_n, r=kdf_r, p=kdf_p)
    try:
        plaintext: bytes = aesgcm_cls(key).decrypt(nonce, ciphertext, _AAD)
    except Exception as exc:
        raise CryptoError("decryption failed: invalid passphrase or tampered data") from exc
    return plaintext.decode("utf-8")


def _collect_target_files(home: Path) -> list[tuple[str, Path]]:
    targets: list[tuple[str, Path]] = []
    projects_dir = home / "projects"
    if projects_dir.is_dir() and not is_link_or_junction(projects_dir):
        for card in sorted(projects_dir.glob("*.md")):
            if card.is_file() and not is_link_or_junction(card):
                targets.append((f"projects/{card.name}", safe_join(projects_dir, card.name)))
    registry = home / "TROUBLESHOOTING.md"
    if registry.is_file() and not is_link_or_junction(registry):
        targets.append(("TROUBLESHOOTING.md", safe_join(home, "TROUBLESHOOTING.md")))
    return targets


def _create_crypto_backup(home: Path, targets: list[tuple[str, Path]], op: str) -> Path:
    stamp = utc_now_iso().replace("-", "").replace(":", "")
    candidate = home / "backups" / "crypto" / f"{op}-{stamp}-{os.getpid()}"
    counter = 1
    while candidate.exists():
        candidate = home / "backups" / "crypto" / f"{op}-{stamp}-{os.getpid()}-{counter}"
        counter += 1
    backup_dir = ensure_private_dir(candidate)
    for rel, src in targets:
        dst = backup_dir / rel
        ensure_private_dir(dst.parent)
        shutil.copy2(src, dst)
    return backup_dir


def _transform_store(
    home: Path | str,
    passphrase: str,
    *,
    operation: str,
    apply: bool = False,
) -> CryptoStoreResult:
    resolved = Path(home).expanduser().resolve()
    meta_path = resolved / "meta.json"
    if not meta_path.is_file() or is_link_or_junction(meta_path):
        raise CryptoError(f"no Engramkeep store at {resolved}; run 'engramkeep init' first")

    targets = _collect_target_files(resolved)
    processed: list[str] = []
    skipped: list[str] = []

    if not apply:
        for rel, path in targets:
            text = path.read_text(encoding="utf-8")
            already = is_encrypted_text(text)
            if (operation == "encrypt" and already) or (operation == "decrypt" and not already):
                skipped.append(rel)
            else:
                processed.append(rel)
        return CryptoStoreResult(
            mode="dry-run",
            operation=operation,
            files_processed=processed,
            files_skipped=skipped,
        )

    _require_crypto()
    with file_lock(resolved / ".engramkeep.lock"):
        backup_dir = _create_crypto_backup(resolved, targets, operation) if targets else None
        for rel, path in targets:
            text = path.read_text(encoding="utf-8")
            already = is_encrypted_text(text)
            if operation == "encrypt":
                if already:
                    skipped.append(rel)
                    continue
                atomic_write_text(path, encrypt_text(text, passphrase), private_parent=True)
                processed.append(rel)
            else:
                if not already:
                    skipped.append(rel)
                    continue
                atomic_write_text(path, decrypt_text(text, passphrase), private_parent=True)
                processed.append(rel)

        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        if isinstance(meta, dict):
            meta["encrypted"] = operation == "encrypt"
            atomic_write_text(meta_path, json.dumps(meta, indent=2) + "\n", private_parent=True)

        return CryptoStoreResult(
            mode="applied",
            operation=operation,
            files_processed=processed,
            files_skipped=skipped,
            backup_dir=backup_dir,
        )


def encrypt_store(
    home: Path | str,
    passphrase: str,
    *,
    apply: bool = False,
) -> CryptoStoreResult:
    """Encrypt project cards and troubleshooting registry in ``home`` (dry-run default)."""
    return _transform_store(home, passphrase, operation="encrypt", apply=apply)


def decrypt_store(
    home: Path | str,
    passphrase: str,
    *,
    apply: bool = False,
) -> CryptoStoreResult:
    """Decrypt encrypted cards and registry in ``home`` back to plain Markdown."""
    return _transform_store(home, passphrase, operation="decrypt", apply=apply)
