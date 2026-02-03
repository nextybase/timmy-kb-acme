# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from pathlib import Path

from pipeline.content_utils import _filter_safe_pdfs


def test_filter_safe_pdfs_blocks_traversal(tmp_path: Path) -> None:
    raw_root = tmp_path / "raw"
    raw_root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    unsafe = outside / "outside.pdf"
    unsafe.write_bytes(b"%PDF-1.4\n")

    result = _filter_safe_pdfs(tmp_path, raw_root, [unsafe], slug="dummy")
    assert result == []
