# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from pathlib import Path

from tests._helpers.workspace_paths import local_workspace_dir
from tools.dummy.bootstrap import ensure_dummy_vision_pdf


def test_ensure_dummy_vision_pdf_creates_file_if_missing(tmp_path: Path) -> None:
    workspace = local_workspace_dir(tmp_path / "output", "dummy")
    pdf_path = workspace / "config" / "VisionStatement.pdf"
    assert not pdf_path.exists()

    result_path = ensure_dummy_vision_pdf(workspace)

    assert result_path.exists()
    assert result_path.stat().st_size > 0


def test_ensure_dummy_vision_pdf_regenerates_when_empty(tmp_path: Path) -> None:
    workspace = local_workspace_dir(tmp_path / "output", "dummy")
    pdf_path = workspace / "config" / "VisionStatement.pdf"
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    pdf_path.write_bytes(b"")  # PDF vuoto / corrotto

    result_path = ensure_dummy_vision_pdf(workspace)

    assert result_path.exists()
    assert result_path.stat().st_size > 0
