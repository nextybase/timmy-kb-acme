# SPDX-License-Identifier: GPL-3.0-or-later
# src/security/masking.py
from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Dict

__all__ = ["hash_identifier", "sha256_path", "mask_paths"]

_DEFAULT_HASH_LENGTH = 32


def _salt_value(value: str, *, salt: str | None = None) -> str:
    payload = value.strip()
    configured = salt if salt is not None else os.getenv("TIMMY_HASH_SALT", "")
    return f"{configured}:{payload}" if configured else payload


def _digest(payload: str, *, salt: str | None = None) -> str:
    salted = _salt_value(payload, salt=salt)
    return hashlib.sha256(salted.encode("utf-8")).hexdigest()


def hash_identifier(value: str, *, length: int = _DEFAULT_HASH_LENGTH, salt: str | None = None) -> str:
    """Hash deterministico di stringhe sensibili (slug, client_name)."""
    if not value:
        return ""
    digest = _digest(value, salt=salt)
    return digest[: max(1, length)]


def sha256_path(path: Path, *, length: int = _DEFAULT_HASH_LENGTH, salt: str | None = None) -> str:
    """Hash SHA256 di un percorso (path) serializzato come stringa."""
    norm = str(Path(path))
    digest = _digest(norm, salt=salt)
    return digest[: max(1, length)]


def mask_paths(*paths: Path) -> Dict[str, str]:
    """Restituisce dict {basename: <hash>} per i path forniti."""
    masked: Dict[str, str] = {}
    for p in paths:
        path = Path(p)
        masked[path.name] = sha256_path(path)
    return masked
