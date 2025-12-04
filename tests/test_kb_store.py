# SPDX-License-Identifier: GPL-3.0-only
# tests/test_kb_store.py
from pathlib import Path

from storage.kb_store import KbStore


def test_effective_path_derives_slug_relative() -> None:
    store = KbStore.for_slug("acme")
    assert store.effective_db_path() == Path("kb-acme.sqlite")


def test_effective_path_respects_override(tmp_path: Path) -> None:
    override = tmp_path / "custom.sqlite"
    store = KbStore.for_slug("x", db_path=override)
    assert store.effective_db_path() == override


def test_effective_path_none_on_empty_slug() -> None:
    store = KbStore.for_slug("")
    assert store.effective_db_path() is None
