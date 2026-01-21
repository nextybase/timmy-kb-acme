# SPDX-License-Identifier: GPL-3.0-only
# tests/test_landing_slug_paths.py
from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

import pytest


def test_base_dir_for_prefers_clientcontext(tmp_path: Path, monkeypatch: Any) -> None:
    """_base_dir_for deve preferire ClientContext (che rispetta REPO_ROOT_DIR) rispetto a
    semantic.api.get_paths."""
    repo_root = tmp_path / "repo-root"
    repo_root.mkdir()
    (repo_root / ".git").mkdir()

    monkeypatch.setenv("REPO_ROOT_DIR", str(repo_root))

    mod = importlib.import_module("src.ui.landing_slug")

    # Patch ClientContext.load per restituire un finto contesto con base_dir personalizzato
    class DummyCtx:
        def __init__(self, base_dir: Path) -> None:
            self.base_dir = base_dir
            self.raw_dir = base_dir / "raw"

    dummy_base = repo_root / "dummy-slug"
    dummy_base.mkdir()

    monkeypatch.setattr(
        "pipeline.context.ClientContext.load",
        lambda **kwargs: DummyCtx(dummy_base),
    )

    base_dir = mod._base_dir_for("dummy-slug")
    assert base_dir == dummy_base
    assert str(base_dir).startswith(str(repo_root))


def test_base_dir_for_runtime_error(monkeypatch: Any) -> None:
    """In assenza di ClientContext valido, _base_dir_for deve sollevare RuntimeError segnalando la
    mancanza del contesto."""
    mod = importlib.import_module("src.ui.landing_slug")

    monkeypatch.setattr(
        "pipeline.context.ClientContext.load",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("no ctx")),
    )

    with pytest.raises(RuntimeError) as excinfo:
        mod._base_dir_for("sem-slug")

    assert "ClientContext" in str(excinfo.value)
