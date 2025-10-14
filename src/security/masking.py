# src/security/masking.py
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Dict

__all__ = ["hash_identifier", "sha256_path", "mask_paths"]


def hash_identifier(value: str) -> str:
    """Hash deterministico di stringhe sensibili (slug, client_name)."""
    digest = hashlib.sha256(value.strip().encode("utf-8"))
    return digest.hexdigest()[:12]


def sha256_path(path: Path) -> str:
    """Hash SHA256 di un percorso (path) serializzato come stringa."""
    norm = str(Path(path))
    digest = hashlib.sha256(norm.encode("utf-8"))
    return digest.hexdigest()[:12]


def mask_paths(*paths: Path) -> Dict[str, str]:
    """Restituisce dict {basename: <hash>} per i path forniti."""
    masked: Dict[str, str] = {}
    for p in paths:
        path = Path(p)
        masked[path.name] = sha256_path(path)
    return masked
