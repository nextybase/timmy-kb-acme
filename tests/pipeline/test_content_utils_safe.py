# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path

import pytest

from pipeline.content_utils import _ensure_safe
from pipeline.exceptions import PathTraversalError


def test_ensure_safe_adds_structured_context(tmp_path: Path) -> None:
    base = tmp_path / "base"
    base.mkdir()
    outside = tmp_path / "evil.pdf"
    outside.write_text("malicious", encoding="utf-8")

    with pytest.raises(PathTraversalError) as excinfo:
        _ensure_safe(base, outside, slug="dummy")

    err = excinfo.value
    assert getattr(err, "slug", None) == "dummy"
    assert str(getattr(err, "file_path", "")).endswith("evil.pdf")
