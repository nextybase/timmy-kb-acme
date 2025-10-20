# tests/ui/test_workspace_helpers.py
from pathlib import Path

import pytest

from ui.utils.workspace import count_pdfs_safe, iter_pdfs_safe


def test_iter_pdfs_safe_basic(tmp_path: Path):
    root = tmp_path / "raw"
    (root / "a").mkdir(parents=True)
    (root / "a" / "x.pdf").write_text("%PDF-1.4")
    (root / "a" / "y.txt").write_text("nope")
    assert list(iter_pdfs_safe(root)) == [root / "a" / "x.pdf"]
    assert count_pdfs_safe(root) == 1


def test_iter_pdfs_safe_symlink(tmp_path: Path):
    root = tmp_path / "raw"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "ext.pdf").write_text("%PDF-1.4")
    try:
        (root / "link").symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("Symlink non permessi su questo sistema")
    # Non deve vedere file fuori perimetro
    assert count_pdfs_safe(root) == 0
