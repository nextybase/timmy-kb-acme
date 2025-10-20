# tests/ui/test_manage_scan.py
from pathlib import Path

import pytest

from ui.pages.manage import _scan_raw_pdfs


def test_scan_ignores_symlink(tmp_path: Path):
    raw = tmp_path / "raw"
    raw.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "x.pdf").write_bytes(b"%PDF-1.4")
    try:
        (raw / "link").symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError) as e:
        pytest.skip(f"Symlink creation not permitted on this system: {e}")

    has, count = _scan_raw_pdfs(raw)
    assert has is False and count == 0
