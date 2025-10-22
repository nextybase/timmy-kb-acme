# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from types import SimpleNamespace

# Palette LIGHT (default)
_LIGHT = dict(
    COLOR_TEXT="#333333",
    COLOR_BG="#ffffff",
    COLOR_DARK="#31383f",  # nav / bottoni base
    COLOR_ACCENT="#ffc100",  # CTA giallo
    COLOR_LINK="#23527b",
    COLOR_OCEAN="#006699",
    FONT_FAMILY='"Lexend", Tahoma, sans-serif',
    H1_SIZE_PX=36,
    RADIUS_M=10,
    INSET_HIGHLIGHT="#ffffff66",
)

# Palette DARK
_DARK = dict(
    COLOR_TEXT="#e6e6e6",
    COLOR_BG="#0f1218",
    COLOR_DARK="#1f2530",
    COLOR_ACCENT="#ffc100",
    COLOR_LINK="#8ab4f8",
    COLOR_OCEAN="#5aa7ff",
    FONT_FAMILY='"Lexend", Tahoma, sans-serif',
    H1_SIZE_PX=36,
    RADIUS_M=10,
    INSET_HIGHLIGHT="#00000055",
)


def resolve_tokens(base: str | None) -> SimpleNamespace:
    """Restituisce palette light/dark come SimpleNamespace."""
    base_normalized = (base or "light").strip().lower()
    return SimpleNamespace(**(_DARK if base_normalized == "dark" else _LIGHT))
