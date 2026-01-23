from __future__ import annotations

# SPDX-License-Identifier: GPL-3.0-only
"""
Helper di percorso centrati sulla root del repository.

Obiettivi:
- get_repo_root: trova la root repository usando sentinel (.git/pyproject), opzionale override ENV.
- global_logs_dir / clients_db_paths / preview_logs_dir: percorsi globali path-safe.

Fail-fast: nessuna degradazione silenziosa; in caso di layout incoerente solleva ConfigError.
"""

import os
from pathlib import Path
from typing import Sequence, Tuple

from .constants import LOGS_DIR_NAME
from .env_constants import REPO_ROOT_ENV
from .exceptions import ConfigError, PathTraversalError
from .logging_utils import get_structured_logger
from .path_utils import ensure_within, ensure_within_and_resolve

LOGGER = get_structured_logger("pipeline.paths")
_SENTINELS: tuple[str, ...] = (".git", "pyproject.toml")


def _has_sentinel(path: Path) -> bool:
    return any((path / marker).exists() for marker in _SENTINELS)


def _walk_up_for_repo_root(start: Path) -> Path | None:
    for candidate in (start, *start.parents):
        if _has_sentinel(candidate):
            return candidate
    return None


def _detect_repo_root(candidates: Sequence[Path]) -> Path | None:
    for start in candidates:
        try:
            resolved = start.resolve()
        except Exception:
            continue
        found = _walk_up_for_repo_root(resolved)
        if found:
            return found
    return None


def _validate_repo_root_env(value: str) -> Path:
    """Valida REPO_ROOT_DIR senza applicare override silenziosi."""
    resolved = Path(value).expanduser().resolve()
    if not resolved.exists():
        LOGGER.error(
            "paths.repo_root.env_invalid",
            extra={"repo_root_dir": value, "reason": "not_exists"},
        )
        raise ConfigError(f"{REPO_ROOT_ENV} non esiste: {resolved}")
    if not _has_sentinel(resolved):
        LOGGER.error(
            "paths.repo_root.env_invalid",
            extra={"repo_root_dir": value, "reason": "sentinel_missing"},
        )
        raise ConfigError(f"{REPO_ROOT_ENV} manca di sentinel .git/pyproject: {resolved}")
    return resolved


def get_repo_root(*, allow_env: bool = True) -> Path:
    """
    Determina la root del repository.

    Cerca sentinel (.git/pyproject) risalendo da cwd e da questo file,
    oppure usa REPO_ROOT_DIR se consentito e valido.
    Fail-fast con ConfigError se non trova una root valida.
    """
    if allow_env:
        env_root = os.getenv(REPO_ROOT_ENV)
        if env_root:
            resolved_env = _validate_repo_root_env(env_root)
            LOGGER.debug("paths.repo_root.env", extra={"repo_root": str(resolved_env)})
            return resolved_env

    this_file = Path(__file__).resolve()
    candidates = [Path.cwd(), this_file.parent]

    detected = _detect_repo_root(candidates)
    if detected:
        LOGGER.info("paths.repo_root.detected", extra={"repo_root": str(detected)})
        return detected

    LOGGER.error(
        "paths.repo_root.not_found",
        extra={"candidates": [str(c) for c in candidates]},
    )
    raise ConfigError("Impossibile determinare la root del repository (.git/pyproject non trovati).")


def _ensure_dir(base: Path, target: Path) -> None:
    ensure_within(base, target)
    target.mkdir(parents=True, exist_ok=True)


def global_logs_dir(repo_root: Path) -> Path:
    """Log globali (derivatives) sotto la repo root: solo dev/diagnostica locale; non runtime e non richiesti."""
    path = ensure_within_and_resolve(repo_root, repo_root / ".timmy_kb" / LOGS_DIR_NAME)
    _ensure_dir(repo_root, path)
    return path


def clients_db_paths(repo_root: Path) -> Tuple[Path, Path]:
    """
    Percorso SSoT per il registry clienti.

    Ritorna (dir, file) con path-safety enforced. Non supporta layout multipli.
    """
    dir_path = ensure_within_and_resolve(repo_root, repo_root / "clients_db")
    file_path = ensure_within_and_resolve(dir_path, dir_path / "clients.yaml")
    _ensure_dir(repo_root, dir_path)
    return dir_path, file_path


def preview_logs_dir(repo_root: Path, *, override: Path | None = None) -> Path:
    """
    Restituisce la directory log preview.

    Override opzionale:
    - assoluto: deve essere risolvibile/creabile, altrimenti ConfigError.
    - relativo: interpretato rispetto a repo_root con guardia path-safety.
    """
    if override is not None:
        try:
            if override.is_absolute():
                target = override.expanduser().resolve()
                target.mkdir(parents=True, exist_ok=True)
                return target
            target = ensure_within_and_resolve(repo_root, repo_root / override)
            _ensure_dir(repo_root, target)
            return target
        except (OSError, PathTraversalError, ConfigError) as exc:
            LOGGER.error(
                "paths.preview.invalid_override",
                extra={"override": str(override), "error": str(exc)},
            )
            raise ConfigError(f"Percorso override preview non valido: {override}") from exc

    path = ensure_within_and_resolve(repo_root, repo_root / LOGS_DIR_NAME / "preview")
    _ensure_dir(repo_root, path)
    return path


__all__ = [
    "get_repo_root",
    "global_logs_dir",
    "clients_db_paths",
    "preview_logs_dir",
]
