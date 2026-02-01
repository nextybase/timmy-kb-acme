# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import os
from pathlib import Path

import pytest

import pipeline.path_utils as path_utils
from pipeline.exceptions import PathTraversalError
from pipeline.file_utils import safe_write_bytes
from pipeline.path_utils import ensure_within, ensure_within_and_resolve, iter_safe_pdfs

pytestmark = pytest.mark.unit


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


def test_safe_write_pdf_refreshes_cache(tmp_path: Path) -> None:
    workspace = tmp_path / "client"
    raw_dir = workspace / "raw"
    raw_dir.mkdir(parents=True)

    pdf_one = raw_dir / "doc1.pdf"
    pdf_two = raw_dir / "doc2.pdf"

    safe_write_bytes(pdf_one, b"%PDF-1.4\n", atomic=True)
    first_listing = list(iter_safe_pdfs(raw_dir, use_cache=True))
    assert pdf_one.resolve() in first_listing

    safe_write_bytes(pdf_two, b"%PDF-1.4\n", atomic=True)

    path_utils.clear_iter_safe_pdfs_cache(root=raw_dir)

    original_iter_safe_paths = path_utils.iter_safe_paths

    called = False

    def _spy(*args: object, **kwargs: object) -> list[Path]:
        nonlocal called
        called = True
        return original_iter_safe_paths(*args, **kwargs)

    path_utils.iter_safe_paths = _spy
    try:
        cached_listing = list(path_utils.iter_safe_pdfs(raw_dir, use_cache=True))
    finally:
        path_utils.iter_safe_paths = original_iter_safe_paths

    resolved_listing = {item.resolve() for item in cached_listing}
    assert pdf_one.resolve() in resolved_listing
    assert pdf_two.resolve() in resolved_listing
    assert len(resolved_listing) == 2
    assert called, "iter_safe_paths should be used when strict disables prewarm"


def test_safe_write_pdf_prewarms_cache_when_non_strict(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TIMMY_BETA_STRICT", "0")
    workspace = tmp_path / "client"
    raw_dir = workspace / "raw"
    raw_dir.mkdir(parents=True)

    pdf_one = raw_dir / "doc1.pdf"
    safe_write_bytes(pdf_one, b"%PDF-1.4\n", atomic=True)

    called = False

    def _boom(*args: object, **kwargs: object) -> list[Path]:
        nonlocal called
        called = True
        raise AssertionError("iter_safe_paths should not be called when cache is prewarmed")

    original_iter_safe_paths = path_utils.iter_safe_paths
    path_utils.iter_safe_paths = _boom
    try:
        cached_listing = list(path_utils.iter_safe_pdfs(raw_dir, use_cache=True))
    finally:
        path_utils.iter_safe_paths = original_iter_safe_paths

    assert not called, "iter_safe_paths should not be called when non-strict prewarms the cache"
    assert pdf_one.resolve() in {item.resolve() for item in cached_listing}


def test_iter_safe_pdfs_cache_invariant_set(tmp_path: Path) -> None:
    workspace = tmp_path / "client"
    raw_dir = workspace / "raw"
    raw_dir.mkdir(parents=True)

    pdfs = [raw_dir / f"doc{idx}.pdf" for idx in range(3)]
    for pdf in pdfs:
        safe_write_bytes(pdf, b"%PDF-1.4\n", atomic=True)

    no_cache = {p.resolve() for p in iter_safe_pdfs(raw_dir, use_cache=False)}
    with_cache = {p.resolve() for p in iter_safe_pdfs(raw_dir, use_cache=True)}

    assert no_cache == with_cache
