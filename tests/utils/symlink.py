# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from pathlib import Path

import pytest


def make_symlink(src: Path, dst: Path, *, is_dir: bool = False) -> None:
    try:
        if is_dir:
            dst.symlink_to(src, target_is_directory=True)
        else:
            dst.symlink_to(src)
    except OSError as exc:
        pytest.skip(f"symlink not supported on this platform: {exc}")
