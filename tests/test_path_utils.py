from __future__ import annotations

import os
from pathlib import Path

import pytest

from pipeline.exceptions import PathTraversalError
from pipeline.path_utils import ensure_within, ensure_within_and_resolve


def test_ensure_within_ok_fail(tmp_path: Path) -> None:
    base = tmp_path / "sandbox"
    base.mkdir()
    inside = base / "nested" / "file.txt"
    inside.parent.mkdir()

    ensure_within(base, inside)

    outside = tmp_path / "outside.txt"
    outside.touch()

    with pytest.raises(PathTraversalError):
        ensure_within(base, outside)


def test_traversal_parent(tmp_path: Path) -> None:
    base = tmp_path / "sandbox"
    base.mkdir()

    traversal_candidate = base / ".." / "evil.txt"
    with pytest.raises(PathTraversalError):
        ensure_within(base, traversal_candidate)


@pytest.mark.skipif(not hasattr(os, "symlink"), reason="symlink not supported on this platform")
def test_symlink_inside_outside(tmp_path: Path) -> None:
    base = tmp_path / "sandbox"
    base.mkdir()
    target_dir = base / "data"
    target_dir.mkdir()
    inside_target = target_dir / "inside.txt"
    inside_target.write_text("ok", encoding="utf-8")

    good_link = base / "inside_link.txt"
    try:
        os.symlink(inside_target, good_link)
    except (OSError, NotImplementedError) as exc:  # pragma: no cover
        pytest.skip(f"symlink not supported on this platform: {exc}")

    resolved = ensure_within_and_resolve(base, good_link)
    assert resolved == inside_target.resolve()

    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()
    outside_target = outside_dir / "outside.txt"
    outside_target.write_text("no", encoding="utf-8")
    bad_link = base / "outside_link.txt"
    try:
        os.symlink(outside_target, bad_link)
    except (OSError, NotImplementedError) as exc:  # pragma: no cover
        pytest.skip(f"symlink not supported on this platform: {exc}")

    with pytest.raises(PathTraversalError):
        ensure_within(base, bad_link)
