# tests/ui/test_manage_scan.py
from pathlib import Path

import pytest

from ui.utils.workspace import count_pdfs_safe


def test_scan_ignores_symlink(tmp_path: Path):
    raw = tmp_path / "raw"
    raw.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "x.pdf").write_bytes(b"%PDF-1.4")
    try:
        (raw / "link").symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("Symlink non permessi su questo sistema")

    # Il walker sicuro non deve contare PDF fuori perimetro via symlink
    assert count_pdfs_safe(raw) == 0
