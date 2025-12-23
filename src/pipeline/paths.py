from __future__ import annotations

# SPDX-License-Identifier: GPL-3.0-only
"""
SSoT per la gestione dei percorsi del repository e dei workspace cliente.

Funzioni chiave:
- get_repo_root: determina la root del repository (env REPO_ROOT_DIR valida o sentinel .git/pyproject).
- workspace_paths: costruisce i percorsi canonici del workspace output/timmy-kb-<slug>/.
- global_logs_dir / clients_db_paths / preview_logs_dir: percorsi globali centralizzati.
- ensure_src_on_sys_path: bootstrap sicuro di <repo_root>/src in sys.path.

Fail-fast: in caso di layout o env incoerente solleva ConfigError invece di applicare fallback legacy.
"""

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence, Tuple

from .constants import (
    BOOK_DIR_NAME,
    CONFIG_DIR_NAME,
    CONFIG_FILE_NAME,
    LOGS_DIR_NAME,
    OUTPUT_DIR_NAME,
    RAW_DIR_NAME,
    REPO_NAME_PREFIX,
    SEMANTIC_DIR_NAME,
)
from .exceptions import ConfigError, PathTraversalError
from .logging_utils import get_structured_logger
from .path_utils import ensure_within, ensure_within_and_resolve, validate_slug

LOGGER = get_structured_logger("pipeline.paths")
_SENTINELS: tuple[str, ...] = (".git", "pyproject.toml")


@dataclass(frozen=True, slots=True)
class WorkspacePaths:
    """Percorsi canonici per uno slug cliente."""

    slug: str
    repo_root: Path
    workspace_root: Path
    raw_dir: Path
    book_dir: Path
    semantic_dir: Path
    config_dir: Path
    config_file: Path
    logs_dir: Path
    dot_timmy_logs_dir: Path
    clients_db_dir: Path
    preview_logs_dir: Path


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


def _validate_repo_root_env(raw: str) -> Path:
    candidate = Path(raw).expanduser()
    if not candidate.is_absolute():
        LOGGER.error(
            "paths.repo_root.invalid_env",
            extra={"repo_root_dir": raw, "reason": "not_absolute"},
        )
        raise ConfigError(f"REPO_ROOT_DIR deve essere un path assoluto: {raw}")

    resolved = candidate.resolve()
    if not resolved.exists():
        LOGGER.error(
            "paths.repo_root.invalid_env",
            extra={"repo_root_dir": raw, "reason": "not_found"},
        )
        raise ConfigError(f"REPO_ROOT_DIR non esiste: {resolved}")

    if not _has_sentinel(resolved):
        LOGGER.error(
            "paths.repo_root.invalid_env",
            extra={"repo_root_dir": raw, "reason": "sentinel_missing"},
        )
        raise ConfigError("REPO_ROOT_DIR non sembra la root del repo " f"(manca .git/pyproject): {resolved}")

    return resolved


def get_repo_root(*, allow_env: bool = True) -> Path:
    """
    Determina la root del repository.

    Se allow_env è True e REPO_ROOT_DIR è impostato, valida il path
    (assoluto, esistente, con sentinel).
    Altrimenti cerca sentinel (.git/pyproject) risalendo da cwd e da questo file.
    Fail-fast con ConfigError se non trova una root valida.
    """
    env_root = os.getenv("REPO_ROOT_DIR") if allow_env else None
    if env_root:
        resolved = _validate_repo_root_env(env_root)
        LOGGER.info("paths.repo_root.env", extra={"repo_root": str(resolved)})
        return resolved

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
    raise ConfigError("Impossibile determinare la root del repository " "(.git/pyproject non trovati).")


def _ensure_dir(base: Path, target: Path) -> None:
    ensure_within(base, target)
    target.mkdir(parents=True, exist_ok=True)


def workspace_paths(slug: str, *, repo_root: Path | None = None, create: bool = False) -> WorkspacePaths:
    """
    Costruisce i percorsi canonici del workspace output/timmy-kb-<slug>/.

    Args:
        slug: identificativo cliente (validato).
        repo_root: root del repository; se None viene rilevata.
        create: se True crea le directory mancanti in modo path-safe.
    """
    root = repo_root or get_repo_root()
    try:
        safe_slug = validate_slug(slug)
    except Exception as exc:  # InvalidSlug o simile
        LOGGER.error(
            "paths.workspace.invalid_slug",
            extra={"slug": slug, "error": str(exc)},
        )
        raise ConfigError(f"Slug non valido: {slug}") from exc

    workspace_root = ensure_within_and_resolve(root, root / OUTPUT_DIR_NAME / f"{REPO_NAME_PREFIX}{safe_slug}")
    raw_dir = ensure_within_and_resolve(workspace_root, workspace_root / RAW_DIR_NAME)
    book_dir = ensure_within_and_resolve(workspace_root, workspace_root / BOOK_DIR_NAME)
    semantic_dir = ensure_within_and_resolve(workspace_root, workspace_root / SEMANTIC_DIR_NAME)
    config_dir = ensure_within_and_resolve(workspace_root, workspace_root / CONFIG_DIR_NAME)
    config_file = ensure_within_and_resolve(config_dir, config_dir / CONFIG_FILE_NAME)
    logs_dir = ensure_within_and_resolve(workspace_root, workspace_root / LOGS_DIR_NAME)
    dot_timmy_logs_dir = ensure_within_and_resolve(root, root / ".timmy_kb" / LOGS_DIR_NAME)
    clients_db_dir = ensure_within_and_resolve(root, root / "clients_db")
    preview_logs_dir = ensure_within_and_resolve(root, root / LOGS_DIR_NAME / "preview")

    if create:
        for base, path in (
            (root, workspace_root),
            (workspace_root, raw_dir),
            (workspace_root, book_dir),
            (workspace_root, semantic_dir),
            (workspace_root, config_dir),
            (workspace_root, logs_dir),
            (root, dot_timmy_logs_dir),
            (root, clients_db_dir),
            (root, preview_logs_dir),
        ):
            _ensure_dir(base, path)
        # config_file non viene creato qui: la responsabilità resta al bootstrap config.

    return WorkspacePaths(
        slug=safe_slug,
        repo_root=root,
        workspace_root=workspace_root,
        raw_dir=raw_dir,
        book_dir=book_dir,
        semantic_dir=semantic_dir,
        config_dir=config_dir,
        config_file=config_file,
        logs_dir=logs_dir,
        dot_timmy_logs_dir=dot_timmy_logs_dir,
        clients_db_dir=clients_db_dir,
        preview_logs_dir=preview_logs_dir,
    )


def global_logs_dir(repo_root: Path) -> Path:
    """Restituisce .timmy_kb/logs sotto la repo root, creandolo se mancante."""
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


def ensure_src_on_sys_path(repo_root: Path) -> None:
    """
    Inserisce <repo_root>/src in sys.path in modo idempotente.

    Solleva ConfigError se il path non esiste o non è una directory.
    """
    try:
        src_dir = ensure_within_and_resolve(repo_root, repo_root / "src")
    except Exception as exc:
        LOGGER.error(
            "paths.sys_path.invalid",
            extra={"repo_root": str(repo_root), "error": str(exc)},
        )
        raise ConfigError(f"Percorso src non valido sotto {repo_root}") from exc

    if not src_dir.exists() or not src_dir.is_dir():
        LOGGER.error(
            "paths.sys_path.missing",
            extra={"repo_root": str(repo_root), "src_dir": str(src_dir)},
        )
        raise ConfigError(f"Directory src non trovata in {repo_root}")

    src_str = str(src_dir)
    if src_str not in sys.path:
        try:
            sys.path.insert(0, src_str)
        except Exception as exc:
            LOGGER.error(
                "paths.sys_path.bootstrap_failed",
                extra={"repo_root": str(repo_root), "src_dir": src_str, "error": str(exc)},
            )
            raise ConfigError(f"Impossibile aggiungere {src_str} a sys.path") from exc
        LOGGER.info("paths.sys_path.added", extra={"src_dir": src_str})


__all__ = [
    "WorkspacePaths",
    "get_repo_root",
    "workspace_paths",
    "global_logs_dir",
    "clients_db_paths",
    "preview_logs_dir",
    "ensure_src_on_sys_path",
]
