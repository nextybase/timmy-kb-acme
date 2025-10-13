# SPDX-License-Identifier: GPL-3.0-or-later
# src/ui/utils/html.py
from __future__ import annotations

from html import escape as _esc
from urllib.parse import quote as _q


def esc_text(s: str | None) -> str:
    return _esc(s or "", quote=True)


def esc_url_component(s: str | None) -> str:
    # usato per querystring/segmenti URL
    return _q(s or "", safe="")
