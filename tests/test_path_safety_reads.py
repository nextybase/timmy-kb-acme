# SPDX-License-Identifier: GPL-3.0-or-later
import os
from pathlib import Path

import pytest

from pipeline.exceptions import ConfigError
from pipeline.path_utils import ensure_within_and_resolve, read_text_safe

pytestmark = pytest.mark.unit


def test_resolve_allows_file_within_base(tmp_path: Path) -> None:
    base = tmp_path / "base"
    base.mkdir()
    f = base / "ok.txt"
    f.write_text("hello", encoding="utf-8")
    safe = read_text_safe(base, f, encoding="utf-8")
    assert safe == "hello"


def test_blocks_path_traversal_outside_base(tmp_path: Path) -> None:
    base = tmp_path / "base"
    base.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("secret", encoding="utf-8")

    p = base / ".." / "outside.txt"
    with pytest.raises(ConfigError):
        read_text_safe(base, p, encoding="utf-8")


def test_blocks_symlink_pointing_outside(tmp_path: Path) -> None:
    base = tmp_path / "base"
    base.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("secret", encoding="utf-8")

    link = base / "link.txt"

    # Try to create a symlink; skip if not supported in this environment.
    try:
        os.symlink(str(outside), str(link))
    except (
        OSError,
        NotImplementedError,
    ) as e:  # pragma: no cover - platform limitation
        pytest.skip(f"symlink not supported on this platform: {e}")

    with pytest.raises(ConfigError):
        read_text_safe(base, link, encoding="utf-8")
