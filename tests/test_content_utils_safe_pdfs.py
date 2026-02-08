# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from pathlib import Path

import pytest

import pipeline.content_utils as cu
from pipeline.exceptions import PathTraversalError


def test_filter_safe_pdfs_requires_raw_root_within_perimeter(tmp_path: Path) -> None:
    perimeter = tmp_path / "workspace"
    perimeter.mkdir(parents=True, exist_ok=True)
    raw_outside = tmp_path / "outside" / "raw"
    raw_outside.mkdir(parents=True, exist_ok=True)

    with pytest.raises(PathTraversalError):
        cu._filter_safe_pdfs(perimeter, raw_outside, pdfs=[], slug="dummy")
