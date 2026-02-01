# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import os
import time
from pathlib import Path

from pipeline.frontmatter_utils import read_frontmatter


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_frontmatter_cache_invalidation_on_mtime_and_size(tmp_path: Path) -> None:
    base = tmp_path / "ws"
    base.mkdir(parents=True, exist_ok=True)
    md = base / "book" / "sample.md"

    initial = """---
title: Hello
tags:
  - a
---
Body A
"""
    _write(md, initial)

    # First read (populate cache)
    meta1, body1 = read_frontmatter(base, md, encoding="utf-8", use_cache=True)
    assert meta1.get("title") == "Hello"
    assert "Body A" in body1

    # Read again without modifications: same result
    meta2, body2 = read_frontmatter(base, md, encoding="utf-8", use_cache=True)
    assert meta2 == meta1
    assert body2 == body1

    # Modify file (both size and content) and bump mtime to ensure invalidation
    modified = """---
title: Hello2
tags:
  - a
  - b
---
Body B
"""
    _write(md, modified)
    try:
        st = md.stat()
        os.utime(md, (st.st_atime, st.st_mtime + 1))
    except Exception:
        # Fallback: small sleep to ensure FS mtime tick
        time.sleep(0.01)

    meta3, body3 = read_frontmatter(base, md, encoding="utf-8", use_cache=True)
    assert meta3.get("title") == "Hello2"
    assert "Body B" in body3
