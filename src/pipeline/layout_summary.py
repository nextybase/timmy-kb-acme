# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

import re
from pathlib import Path

from pipeline.path_utils import ensure_within_and_resolve, read_text_safe


def parse_layout_summary_entries(text: str) -> list[str]:
    """Estrae la lista delle sezioni top-level dai bullet Markdown."""
    entries: list[str] = []
    for line in text.splitlines():
        match = re.match(r"- \*\*(.+?)\*\*", line.strip())
        if match:
            entries.append(match.group(1).strip())
    return entries


def read_layout_summary_entries(md_dir: Path) -> list[str]:
    """Legge `layout_summary.md` e restituisce i top level previsti."""
    summary = md_dir / "layout_summary.md"
    if not summary.exists():
        return []
    try:
        safe = ensure_within_and_resolve(md_dir, summary)
        text = read_text_safe(safe.parent, safe, encoding="utf-8")
    except Exception:
        return []
    return parse_layout_summary_entries(text)
