# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import types
from pathlib import Path

import pytest

import pipeline.path_utils as path_utils


@pytest.mark.parametrize("value", ["", "   "])
def test_sanitize_filename_invalid_inputs(value: str) -> None:
    with pytest.raises(path_utils.FilenameSanitizeError):
        path_utils.sanitize_filename(value)


def test_sanitize_filename_strict_raises_on_internal_error(monkeypatch: pytest.MonkeyPatch) -> None:
    dummy_unicode = types.SimpleNamespace(
        normalize=lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    monkeypatch.setattr(path_utils, "unicodedata", dummy_unicode, raising=True)
    with pytest.raises(path_utils.FilenameSanitizeError):
        path_utils.sanitize_filename("ok")


@pytest.mark.parametrize(
    ("trigger", "paths", "base"),
    (
        ("BAD_BASE", [Path("ok")], Path("BAD_BASE")),
        ("BAD_ITEM", [Path("BAD_ITEM")], None),
    ),
)
def test_sorted_paths_strict_raises_on_resolve(
    monkeypatch: pytest.MonkeyPatch, trigger: str, paths: list[Path], base: Path | None
) -> None:
    original_resolve = path_utils.Path.resolve

    def _resolve(self: Path, *args: object, **kwargs: object) -> Path:
        if trigger in str(self):
            raise RuntimeError("boom")
        return original_resolve(self, *args, **kwargs)

    monkeypatch.setattr(path_utils.Path, "resolve", _resolve, raising=True)
    with pytest.raises(path_utils.PathSortError):
        if base is None:
            path_utils.sorted_paths(paths)
        else:
            path_utils.sorted_paths(paths, base=base)
