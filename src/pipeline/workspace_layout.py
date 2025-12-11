# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

'"""SSoT dei percorsi workspace derivati da uno slug Timmy-KB.""'

from dataclasses import dataclass
from pathlib import Path

from pipeline.constants import LOG_FILE_NAME, LOGS_DIR_NAME
from pipeline.context import ClientContext
from pipeline.exceptions import ConfigError
from pipeline.path_utils import ensure_within, ensure_within_and_resolve, validate_slug

__all__ = ["WorkspaceLayout"]


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

    @classmethod
    def from_context(cls, context: ClientContext) -> "WorkspaceLayout":
        """Crea il layout partendo da un ClientContext già inizializzato."""
        root = getattr(context, "repo_root_dir", None) or getattr(context, "base_dir", None)
        if root is None:
            raise ConfigError("ClientContext privo di repo_root_dir/base_dir", slug=context.slug)
        root = Path(root).resolve()

        raw_dir = getattr(context, "raw_dir", None) or (root / "raw")
        book_dir = getattr(context, "md_dir", None) or (root / "book")
        semantic_dir = getattr(context, "semantic_dir", None) or (root / "semantic")
        log_dir_attr = getattr(context, "logs_dir", None) or getattr(context, "log_dir", None)
        logs_dir = Path(log_dir_attr) if log_dir_attr is not None else root / LOGS_DIR_NAME
        config_path_attr = getattr(context, "config_path", None)
        config_path = config_path_attr or (root / "config" / "config.yaml")
        mapping_path_attr = getattr(context, "mapping_path", None)
        mapping_path = mapping_path_attr or (root / "semantic" / "semantic_mapping.yaml")

        raw_dir = ensure_within_and_resolve(root, raw_dir)
        semantic_dir = ensure_within_and_resolve(root, semantic_dir)
        book_dir = ensure_within_and_resolve(root, book_dir)
        logs_dir = ensure_within_and_resolve(root, logs_dir)
        ensure_within(root, config_path)
        config_path = ensure_within_and_resolve(root, config_path)
        mapping_path = ensure_within_and_resolve(root, mapping_path)

        log_file = ensure_within_and_resolve(logs_dir, logs_dir / LOG_FILE_NAME)

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
        )

    @classmethod
    def from_slug(cls, *, slug: str, require_env: bool = True, run_id: str | None = None) -> "WorkspaceLayout":
        """Valida lo slug e costruisce il layout grazie a ClientContext.load."""
        validate_slug(slug)
        context = ClientContext.load(slug=slug, require_env=require_env, run_id=run_id)
        return cls.from_context(context)

    @classmethod
    def from_workspace(
        cls,
        workspace: Path,
        *,
        slug: str | None = None,
        run_id: str | None = None,
    ) -> "WorkspaceLayout":
        """Costruisce il layout quando viene passato un workspace già esistente."""
        repo_root = workspace.resolve()
        resolved_slug = slug or repo_root.name
        validate_slug(resolved_slug)

        raw_dir = repo_root / "raw"
        book_dir = repo_root / "book"
        semantic_dir = repo_root / "semantic"
        logs_dir = repo_root / LOGS_DIR_NAME
        config_path = repo_root / "config" / "config.yaml"
        mapping_path = repo_root / "semantic" / "semantic_mapping.yaml"

        raw_dir = ensure_within_and_resolve(repo_root, raw_dir)
        semantic_dir = ensure_within_and_resolve(repo_root, semantic_dir)
        book_dir = ensure_within_and_resolve(repo_root, book_dir)
        logs_dir = ensure_within_and_resolve(repo_root, logs_dir)
        ensure_within(repo_root, config_path)
        config_path = ensure_within_and_resolve(repo_root, config_path)
        mapping_path = ensure_within_and_resolve(repo_root, mapping_path)

        log_file = ensure_within_and_resolve(logs_dir, logs_dir / LOG_FILE_NAME)

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
        )
