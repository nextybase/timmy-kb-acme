# SPDX-License-Identifier: GPL-3.0-or-later
from pathlib import Path

import pytest

import pipeline.workspace_layout as workspace_layout
from pipeline.context import ClientContext
from pipeline.exceptions import ConfigError, WorkspaceLayoutInconsistent, WorkspaceLayoutInvalid, WorkspaceNotFound
from pipeline.workspace_layout import WorkspaceLayout


def test_workspace_exceptions_are_config_errors() -> None:
    assert issubclass(WorkspaceNotFound, ConfigError)
    assert issubclass(WorkspaceLayoutInvalid, ConfigError)
    assert issubclass(WorkspaceLayoutInconsistent, ConfigError)


def test_workspace_exception_str_contains_context() -> None:
    exc = WorkspaceNotFound(
        "workspace root mancante",
        slug="dummy",
        file_path=Path("config/config.yaml"),
    )
    text = str(exc)
    assert "slug=dummy" in text
    assert "file=config.yaml" in text


def test_workspace_layout_missing_root_raises_workspace_not_found() -> None:
    ctx = ClientContext(slug="dummy")
    ctx.repo_root_dir = None
    with pytest.raises(WorkspaceNotFound):
        WorkspaceLayout.from_context(ctx)


def test_workspace_layout_missing_repo_root_dir_raises(tmp_path: Path) -> None:
    ctx = ClientContext(slug="dummy")
    ctx.repo_root_dir = None
    with pytest.raises(WorkspaceNotFound):
        WorkspaceLayout.from_context(ctx)


def test_ensure_layout_consistency_propagates_unexpected_typeerror(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "ws"
    semantic_dir = root / "semantic"
    mapping_path = semantic_dir / "semantic_mapping.yaml"
    monkeypatch.setattr(workspace_layout, "ensure_within", lambda *_a, **_k: (_ for _ in ()).throw(TypeError("boom")))

    with pytest.raises(TypeError, match="boom"):
        workspace_layout._ensure_layout_consistency(
            slug="dummy",
            workspace_root=root,
            raw_dir=root / "raw",
            normalized_dir=root / "normalized",
            config_path=root / "config" / "config.yaml",
            book_dir=root / "book",
            logs_dir=root / "logs",
            semantic_dir=semantic_dir,
            mapping_path=mapping_path,
        )


def test_ensure_layout_consistency_wraps_valueerror_as_inconsistent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "ws"
    semantic_dir = root / "semantic"
    mapping_path = semantic_dir / "semantic_mapping.yaml"
    monkeypatch.setattr(workspace_layout, "ensure_within", lambda *_a, **_k: (_ for _ in ()).throw(ValueError("bad")))

    with pytest.raises(WorkspaceLayoutInconsistent, match="Layout incoerente: path fuori perimetro"):
        workspace_layout._ensure_layout_consistency(
            slug="dummy",
            workspace_root=root,
            raw_dir=root / "raw",
            normalized_dir=root / "normalized",
            config_path=root / "config" / "config.yaml",
            book_dir=root / "book",
            logs_dir=root / "logs",
            semantic_dir=semantic_dir,
            mapping_path=mapping_path,
        )
