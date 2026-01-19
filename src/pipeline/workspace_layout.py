# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

"""SSoT dei percorsi workspace derivati da uno slug Timmy-KB.

La Workspace Layout Resolution Policy è fail-fast: il resolver solleva
`WorkspaceNotFound` se lo slug non è mappato o non esiste una radice valida,
`WorkspaceLayoutInvalid` se il layout manca di asset minimi obbligatori e
`WorkspaceLayoutInconsistent` per discrepanze non banali (config/versione/semantic)
anche quando la struttura fisica è presente."""

import os
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from pipeline.constants import LOG_FILE_NAME, LOGS_DIR_NAME
from pipeline.context import ClientContext
from pipeline.exceptions import WorkspaceLayoutInconsistent, WorkspaceLayoutInvalid, WorkspaceNotFound
from pipeline.path_utils import ensure_within, ensure_within_and_resolve, validate_slug

__all__ = ["WorkspaceLayout", "get_workspace_layout"]

_SKIP_VALIDATION = False


@contextmanager
def workspace_validation_policy(*, skip_validation: bool = False):
    """
    Policy di validazione.
    - skip_validation: solo per bootstrap/test controllati (nessun silent fix).
    """
    global _SKIP_VALIDATION
    prev_skip = _SKIP_VALIDATION
    _SKIP_VALIDATION = skip_validation
    try:
        yield
    finally:
        _SKIP_VALIDATION = prev_skip


def _to_path(value: Any, fallback: Path) -> Path:
    if isinstance(value, Path):
        return value
    if isinstance(value, (str, os.PathLike)):
        return Path(value)
    return fallback


@dataclass(frozen=True)
class WorkspaceLayout:
    """Raccoglie i path core del workspace slug-based."""

    slug: str
    repo_root_dir: Path
    base_dir: Path
    raw_dir: Path
    semantic_dir: Path
    book_dir: Path
    logs_dir: Path
    log_file: Path
    config_path: Path
    mapping_path: Path
    tags_db: Path | None = None
    vision_pdf: Path | None = None
    client_name: str | None = None
    env: str | None = None

    @classmethod
    def from_context(cls, context: ClientContext) -> "WorkspaceLayout":
        """Costruisce il layout dal ClientContext e applica la policy fail-fast.

        Solleva WorkspaceNotFound quando la radice non può essere risolta e
        WorkspaceLayoutInvalid/WorkspaceLayoutInconsistent quando il layout disponibile
        è carente o incoerente; in runtime non viene mai creata o riparata alcuna
        directory o asset."""
        if not hasattr(context, "repo_root_dir") or context.repo_root_dir is None:
            raise WorkspaceNotFound("ClientContext privo di repo_root_dir", slug=context.slug)

        root = Path(context.repo_root_dir).resolve()

        raw_dir = root / "raw"
        book_dir = root / "book"
        semantic_dir = root / "semantic"
        logs_dir = root / LOGS_DIR_NAME
        config_path = root / "config" / "config.yaml"
        mapping_path = semantic_dir / "semantic_mapping.yaml"
        config_dir = config_path.parent

        raw_dir = ensure_within_and_resolve(root, raw_dir)
        semantic_dir = ensure_within_and_resolve(root, semantic_dir)
        book_dir = ensure_within_and_resolve(root, book_dir)
        logs_dir = ensure_within_and_resolve(root, logs_dir)
        ensure_within(root, config_path)
        config_path = ensure_within_and_resolve(root, config_path)
        mapping_path = ensure_within_and_resolve(root, mapping_path)

        _validate_layout_assets(
            slug=context.slug,
            workspace_root=root,
            raw_dir=raw_dir,
            book_dir=book_dir,
            logs_dir=logs_dir,
            config_path=config_path,
            semantic_dir=semantic_dir,
            mapping_path=mapping_path,
            skip_validation=_SKIP_VALIDATION,
        )

        log_file = ensure_within_and_resolve(logs_dir, logs_dir / LOG_FILE_NAME)
        tags_db = _derive_child_path(semantic_dir, "tags.db")
        vision_pdf = _derive_child_path(config_dir, "VisionStatement.pdf")
        client_name = getattr(context, "client_name", None)
        env_value = _extract_env_from_context(context)

        return cls(
            slug=context.slug,
            repo_root_dir=root,
            base_dir=root,
            raw_dir=raw_dir,
            semantic_dir=semantic_dir,
            book_dir=book_dir,
            logs_dir=logs_dir,
            log_file=log_file,
            config_path=config_path,
            mapping_path=mapping_path,
            tags_db=tags_db,
            vision_pdf=vision_pdf,
            client_name=client_name,
            env=env_value,
        )

    @classmethod
    def from_slug(cls, *, slug: str, require_env: bool = True, run_id: str | None = None) -> "WorkspaceLayout":
        """Valida lo slug, costruisce il ClientContext e applica la policy fail-fast."""
        validate_slug(slug)
        context = ClientContext.load(
            slug=slug,
            require_env=require_env,
            run_id=run_id,
            bootstrap_config=False,
        )
        return cls.from_context(context)

    @classmethod
    def from_workspace(
        cls,
        workspace: Path,
        *,
        slug: str | None = None,
        _run_id: str | None = None,
        skip_validation: bool = False,
    ) -> "WorkspaceLayout":
        """Costruisce il layout da una directory workspace già esistente in modo fail-fast.

        Non vengono creati né modificati asset: in caso di mancanza viene
        sollevato WorkspaceNotFound o WorkspaceLayoutInvalid e le riparazioni
        restano responsabilità dei flussi bootstrap/migrazione."""
        if not workspace.exists():
            raise WorkspaceNotFound("Workspace esplicito non esiste", file_path=workspace)
        repo_root = workspace.resolve()
        resolved_slug = slug or repo_root.name
        validate_slug(resolved_slug)

        raw_dir = repo_root / "raw"
        book_dir = repo_root / "book"
        semantic_dir = repo_root / "semantic"
        logs_dir = repo_root / LOGS_DIR_NAME
        config_path = repo_root / "config" / "config.yaml"
        mapping_path = semantic_dir / "semantic_mapping.yaml"

        raw_dir = ensure_within_and_resolve(repo_root, raw_dir)
        semantic_dir = ensure_within_and_resolve(repo_root, semantic_dir)
        book_dir = ensure_within_and_resolve(repo_root, book_dir)
        logs_dir = ensure_within_and_resolve(repo_root, logs_dir)
        ensure_within(repo_root, config_path)
        config_path = ensure_within_and_resolve(repo_root, config_path)
        mapping_path = ensure_within_and_resolve(repo_root, mapping_path)
        config_dir = config_path.parent

        _validate_layout_assets(
            slug=resolved_slug,
            workspace_root=repo_root,
            raw_dir=raw_dir,
            book_dir=book_dir,
            logs_dir=logs_dir,
            config_path=config_path,
            semantic_dir=semantic_dir,
            mapping_path=mapping_path,
            skip_validation=skip_validation or _SKIP_VALIDATION,
        )

        log_file = ensure_within_and_resolve(logs_dir, logs_dir / LOG_FILE_NAME)
        tags_db = _derive_child_path(semantic_dir, "tags.db")
        vision_pdf = _derive_child_path(config_dir, "VisionStatement.pdf")

        return cls(
            slug=resolved_slug,
            repo_root_dir=repo_root,
            base_dir=repo_root,
            raw_dir=raw_dir,
            semantic_dir=semantic_dir,
            book_dir=book_dir,
            logs_dir=logs_dir,
            log_file=log_file,
            config_path=config_path,
            mapping_path=mapping_path,
            tags_db=tags_db,
            vision_pdf=vision_pdf,
            client_name=None,
            env=None,
        )


def get_workspace_layout(*, slug: str, require_env: bool = True, run_id: str | None = None) -> WorkspaceLayout:
    """Entrypoint canonico: slug validato → WorkspaceLayout con ClientContext."""
    return WorkspaceLayout.from_slug(slug=slug, require_env=require_env, run_id=run_id)


def _derive_child_path(base: Path | None, relative: str) -> Path | None:
    """Ritorna il path risolto di `relative` dentro `base`, se possibile."""
    if base is None:
        return None
    return cast(Path, ensure_within_and_resolve(base, base / relative))


def _extract_env_from_context(context: ClientContext) -> str | None:
    """Legge il flag ENV/TIMMY_ENV memorizzato dentro il ClientContext."""
    env_data = getattr(context, "env", None)
    if not isinstance(env_data, dict):
        return None
    for key in ("ENV", "TIMMY_ENV"):
        value = env_data.get(key)
        if isinstance(value, str):
            cleaned = value.strip()
            if cleaned:
                return cleaned
    return None


def _validate_layout_assets(
    *,
    slug: str,
    workspace_root: Path,
    raw_dir: Path,
    book_dir: Path,
    logs_dir: Path,
    config_path: Path,
    semantic_dir: Path,
    mapping_path: Path | None = None,
    skip_validation: bool = False,
) -> None:
    """Fail-fast se gli asset minimi del layout non esistono.

    In futuro la logica di validazione di config/version/mapping solleverà
    WorkspaceLayoutInconsistent tramite `_ensure_layout_consistency`.
    La validazione può essere disattivata solo se esplicitamente richiesto
    (es. bootstrap/test controllati)."""
    if skip_validation or _SKIP_VALIDATION:
        return
    _ensure_directory(workspace_root, slug, description="workspace root")
    _ensure_file(config_path, slug, description="config/config.yaml")
    _ensure_directory(raw_dir, slug, description="raw directory")
    _ensure_directory(book_dir, slug, description="book directory")
    _ensure_file(book_dir / "README.md", slug, description="book/README.md")
    _ensure_file(book_dir / "SUMMARY.md", slug, description="book/SUMMARY.md")
    _ensure_directory(semantic_dir, slug, description="semantic directory")
    _ensure_directory(logs_dir, slug, description="logs directory")
    _ensure_layout_consistency(
        slug=slug,
        workspace_root=workspace_root,
        raw_dir=raw_dir,
        config_path=config_path,
        book_dir=book_dir,
        logs_dir=logs_dir,
        semantic_dir=semantic_dir,
        mapping_path=mapping_path,
    )


def _ensure_directory(path: Path, slug: str, *, description: str) -> None:
    if not path.exists() or not path.is_dir():
        raise WorkspaceLayoutInvalid(
            f"{description} mancante o non valida per il workspace {slug}",
            slug=slug,
            file_path=path,
        )


def _ensure_file(path: Path, slug: str, *, description: str) -> None:
    if not path.exists() or not path.is_file():
        raise WorkspaceLayoutInvalid(
            f"{description} mancante o non valida per il workspace {slug}",
            slug=slug,
            file_path=path,
        )


def _ensure_layout_consistency(
    *,
    slug: str,
    workspace_root: Path,
    raw_dir: Path,
    config_path: Path,
    book_dir: Path,
    logs_dir: Path,
    semantic_dir: Path,
    mapping_path: Path | None = None,
) -> None:
    """Fail-fast se il layout contiene path fuori perimetro o incoerenti."""
    try:
        ensure_within(workspace_root, raw_dir)
        ensure_within(workspace_root, book_dir)
        ensure_within(workspace_root, semantic_dir)
        ensure_within(workspace_root, logs_dir)
        ensure_within(workspace_root, config_path)
        if mapping_path is not None:
            ensure_within(workspace_root, mapping_path)
            ensure_within(semantic_dir, mapping_path)
    except Exception as exc:
        raise WorkspaceLayoutInconsistent(
            f"Layout incoerente: path fuori perimetro per workspace {slug}: {exc}",
            slug=slug,
            file_path=mapping_path or config_path,
        ) from exc
