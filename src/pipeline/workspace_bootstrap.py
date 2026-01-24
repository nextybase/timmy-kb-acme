# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

"""SSoT for workspace bootstrap/migration APIs.

This module exposes the only authorized entry points that may create or repair
workspace layouts (default locale: `output/timmy-kb-<slug>/...`) for NEW_CLIENT,
DUMMY_BOOTSTRAP, and MIGRATION/Maintenance. Runtime modules must keep using
`WorkspaceLayout` in fail-fast mode and never call these functions directly.
"""

import os
from pathlib import Path
from typing import cast

from pipeline.constants import LOGS_DIR_NAME
from pipeline.context import ClientContext
from pipeline.exceptions import ConfigError, WorkspaceNotFound
from pipeline.file_utils import safe_write_text
from pipeline.path_utils import ensure_within, ensure_within_and_resolve, read_text_safe, validate_slug
from pipeline.workspace_layout import WorkspaceLayout

__all__ = [
    "bootstrap_client_workspace",
    "bootstrap_dummy_workspace",
    "migrate_or_repair_workspace",
]


def bootstrap_client_workspace(context: ClientContext) -> WorkspaceLayout:
    """SSoT entry for NEW_CLIENT bootstrap flows.

    This function is responsible for creating or completing the layout for a new
    customer workspace, writing the minimal assets (config/book/raw/semantic/logs)
    and letting `WorkspaceLayout` validate the result. Runtime/UI code must not
    call this helper directly; onboarding tooling is the only authorized caller.
    """

    validate_slug(context.slug)
    workspace_root = _workspace_root_from_context(context)
    workspace_root.mkdir(parents=True, exist_ok=True)

    context.repo_root_dir = workspace_root

    raw_dir = _assert_within(workspace_root, workspace_root / "raw")
    raw_dir.mkdir(parents=True, exist_ok=True)
    normalized_dir = _assert_within(workspace_root, workspace_root / "normalized")
    normalized_dir.mkdir(parents=True, exist_ok=True)
    semantic_dir = _assert_within(workspace_root, workspace_root / "semantic")
    semantic_dir.mkdir(parents=True, exist_ok=True)
    book_dir = _assert_within(workspace_root, workspace_root / "book")
    book_dir.mkdir(parents=True, exist_ok=True)
    logs_dir = _assert_within(workspace_root, workspace_root / LOGS_DIR_NAME)
    logs_dir.mkdir(parents=True, exist_ok=True)
    config_dir = _assert_within(workspace_root, workspace_root / "config")
    config_dir.mkdir(parents=True, exist_ok=True)

    config_path = _assert_within(workspace_root, config_dir / "config.yaml")
    if not config_path.exists():
        _write_minimal_file(config_path, _template_config_content())
    _write_minimal_file(book_dir / "README.md", "# Client book\n")
    _write_minimal_file(book_dir / "SUMMARY.md", "# Summary\n")

    return WorkspaceLayout.from_context(context)


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _assert_within(base: Path, candidate: Path) -> Path:
    ensure_within(base, candidate)
    return cast(Path, ensure_within_and_resolve(base, candidate))


def _write_minimal_file(path: Path, content: str) -> None:
    safe_write_text(path, content, encoding="utf-8", atomic=True)


def _template_config_content() -> str:
    template = _project_root() / "config" / "config.yaml"
    if template.exists():
        safe_template = ensure_within_and_resolve(_project_root(), template)
        return cast(str, read_text_safe(safe_template.parent, safe_template, encoding="utf-8"))
    raise ConfigError(f"Template config.yaml globale non trovato: {template}", file_path=template)


def _dummy_output_root() -> Path:
    env_value = os.environ.get("TIMMY_KB_DUMMY_OUTPUT_ROOT")
    if env_value:
        return Path(env_value).resolve()
    return _project_root()


def _workspace_root_from_context(context: ClientContext) -> Path:
    """Determina la directory workspace del cliente partendo dal contract Beta."""
    validate_slug(context.slug)
    if context.repo_root_dir is None:
        raise WorkspaceNotFound("repo_root_dir obbligatorio (contract Beta)", slug=context.slug)
    return Path(context.repo_root_dir).resolve()


def bootstrap_dummy_workspace(slug: str) -> WorkspaceLayout:
    """Create or refresh a dummy workspace layout.

    Args:
        slug: Identifier of the dummy client; it drives the workspace directory name.
    """

    validate_slug(slug)
    output_root = _dummy_output_root()
    output_root.mkdir(parents=True, exist_ok=True)

    output_parent = _assert_within(output_root, output_root / "output")
    output_parent.mkdir(parents=True, exist_ok=True)

    workspace_dir = _assert_within(output_parent, output_parent / f"timmy-kb-{slug}")
    workspace_dir.mkdir(parents=True, exist_ok=True)

    raw_dir = _assert_within(workspace_dir, workspace_dir / "raw")
    raw_dir.mkdir(parents=True, exist_ok=True)
    normalized_dir = _assert_within(workspace_dir, workspace_dir / "normalized")
    normalized_dir.mkdir(parents=True, exist_ok=True)
    semantic_dir = _assert_within(workspace_dir, workspace_dir / "semantic")
    semantic_dir.mkdir(parents=True, exist_ok=True)
    book_dir = _assert_within(workspace_dir, workspace_dir / "book")
    book_dir.mkdir(parents=True, exist_ok=True)
    logs_dir = _assert_within(workspace_dir, workspace_dir / LOGS_DIR_NAME)
    logs_dir.mkdir(parents=True, exist_ok=True)
    config_dir = _assert_within(workspace_dir, workspace_dir / "config")
    config_dir.mkdir(parents=True, exist_ok=True)

    _write_minimal_file(config_dir / "config.yaml", _template_config_content())
    _write_minimal_file(book_dir / "README.md", "# Dummy KB")
    _write_minimal_file(book_dir / "SUMMARY.md", "# Summary")

    return WorkspaceLayout.from_workspace(workspace_dir, slug=slug)


def migrate_or_repair_workspace(context: ClientContext) -> WorkspaceLayout:
    """SSoT entry for MIGRATION / MAINTENANCE workflows.

    This helper expects an existing workspace and can repair missing minimal assets
    (`config/config.yaml`, README/SUMMARY, raw/semantic/logs directories) before
    delegating validation to `WorkspaceLayout`. It never creates a brand-new workspace
    from scratch; missing roots raise `WorkspaceNotFound`.
    """

    validate_slug(context.slug)
    workspace_root = _workspace_root_from_context(context)
    if not workspace_root.exists():
        raise WorkspaceNotFound("Workspace root missing", slug=context.slug, file_path=workspace_root)

    context.repo_root_dir = workspace_root

    dirs = {
        "raw": workspace_root / "raw",
        "normalized": workspace_root / "normalized",
        "semantic": workspace_root / "semantic",
        "book": workspace_root / "book",
        "logs": workspace_root / LOGS_DIR_NAME,
        "config": workspace_root / "config",
    }
    for _, path in dirs.items():
        safe_path = _assert_within(workspace_root, path)
        safe_path.mkdir(parents=True, exist_ok=True)

    config_path = _assert_within(workspace_root, dirs["config"] / "config.yaml")
    if not config_path.exists():
        _write_minimal_file(config_path, _template_config_content())

    book_dir = dirs["book"]
    _write_minimal_file(_assert_within(workspace_root, book_dir / "README.md"), "# Client book\n")
    _write_minimal_file(_assert_within(workspace_root, book_dir / "SUMMARY.md"), "# Summary\n")

    return WorkspaceLayout.from_context(context)
