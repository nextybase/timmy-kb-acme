# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

import re
import types
from pathlib import Path

import pytest

import pipeline.path_utils as path_utils


def test_sanitize_filename_non_strict_empty_returns_hashed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TIMMY_BETA_STRICT", raising=False)
    value = path_utils.sanitize_filename("")
    assert value != "file"
    assert re.fullmatch(r"file-[0-9a-f]{12}", value)


def test_sanitize_filename_non_strict_whitespace_returns_hashed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TIMMY_BETA_STRICT", raising=False)
    value = path_utils.sanitize_filename("   ")
    assert value != "file"
    assert re.fullmatch(r"file-[0-9a-f]{12}", value)


def test_sanitize_filename_strict_raises_on_internal_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TIMMY_BETA_STRICT", "1")
    dummy_unicode = types.SimpleNamespace(
        normalize=lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    monkeypatch.setattr(path_utils, "unicodedata", dummy_unicode, raising=True)
    with pytest.raises(path_utils.FilenameSanitizeError):
        path_utils.sanitize_filename("ok")


def test_sorted_paths_strict_raises_on_base_resolve(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TIMMY_BETA_STRICT", "1")
    original_resolve = path_utils.Path.resolve

    def _resolve(self: Path, *args: object, **kwargs: object) -> Path:
        if "BAD_BASE" in str(self):
            raise RuntimeError("boom")
        return original_resolve(self, *args, **kwargs)

    monkeypatch.setattr(path_utils.Path, "resolve", _resolve, raising=True)
    with pytest.raises(path_utils.PathSortError):
        path_utils.sorted_paths([Path("ok")], base=Path("BAD_BASE"))


def test_sorted_paths_strict_raises_on_item_resolve(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TIMMY_BETA_STRICT", "1")
    original_resolve = path_utils.Path.resolve

    def _resolve(self: Path, *args: object, **kwargs: object) -> Path:
        if "BAD_ITEM" in str(self):
            raise RuntimeError("boom")
        return original_resolve(self, *args, **kwargs)

    monkeypatch.setattr(path_utils.Path, "resolve", _resolve, raising=True)
    with pytest.raises(path_utils.PathSortError):
        path_utils.sorted_paths([Path("BAD_ITEM")])
