# SPDX-License-Identifier: GPL-3.0-only
# tests/test_kb_store.py
from pathlib import Path

from kb_db import get_db_path
from storage.kb_store import KbStore


def test_default_uses_global_db() -> None:
    store = KbStore.default()
    assert store.effective_db_path() == get_db_path()


def test_workspace_path_semantic_dir(tmp_path: Path) -> None:
    workspace = tmp_path / "output" / "timmy-kb-dummy"
    workspace.mkdir(parents=True, exist_ok=True)
    store = KbStore.for_slug("dummy", base_dir=workspace)
    expected = (workspace / "semantic" / "kb.sqlite").resolve()
    assert store.effective_db_path() == expected


def test_override_absolute_and_relative(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)

    absolute = tmp_path / "custom.sqlite"
    store_abs = KbStore.for_slug("x", base_dir=workspace, db_path=absolute)
    assert store_abs.effective_db_path() == absolute.resolve()

    relative = Path("dbs") / "kb.sqlite"
    store_rel = KbStore.for_slug("x", base_dir=workspace, db_path=relative)
    assert store_rel.effective_db_path() == (workspace / relative).resolve()


def test_override_relative_without_base_dir(tmp_path: Path) -> None:
    relative = Path("kb-alt.sqlite")
    store = KbStore.for_slug("x", base_dir=None, db_path=relative)
    assert store.effective_db_path() == relative
