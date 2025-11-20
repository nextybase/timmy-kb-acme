# SPDX-License-Identifier: GPL-3.0-or-later
# src/ui/theme/tokens.py
from __future__ import annotations

from types import SimpleNamespace

# Palette LIGHT (default)
_LIGHT = dict(
    COLOR_TEXT="#333333",
    COLOR_BG="#ffffff",
    COLOR_DARK="#006699",  # nav / bottoni base
    COLOR_ACCENT="#ffcc00",  # CTA giallo
    COLOR_LINK="#23527b",
    COLOR_OCEAN="#006699",
    FONT_FAMILY='"Lexend", Tahoma, sans-serif',
    H1_SIZE_PX=36,
    RADIUS_M=10,
    INSET_HIGHLIGHT="#ffffff66",
    # Percorso relativo al repo root per il logo in tema chiaro
    LOGO_IMAGE="src/ui/theme/img/next-logo.png",
)

# Palette DARK
_DARK = dict(
    COLOR_TEXT="#aaaaaa",
    COLOR_BG="#006699",
    COLOR_DARK="#1f2530",
    COLOR_ACCENT="#ffcc00",
    COLOR_LINK="#8ab4f8",
    COLOR_OCEAN="#5aa7ff",
    FONT_FAMILY='"Lexend", Tahoma, sans-serif',
    H1_SIZE_PX=36,
    RADIUS_M=10,
    INSET_HIGHLIGHT="#00000055",
    # Percorso relativo al repo root per il logo in tema scuro
    LOGO_IMAGE="src/ui/theme/img/next-logo-bianco.png",
)


def resolve_tokens(base: str | None) -> SimpleNamespace:
    """
    Restituisce palette light/dark come SimpleNamespace.

    Args:
        base: "light" o "dark" (case-insensitive). Qualsiasi altro valore
              viene normalizzato a "light".
    """
    base_normalized = (base or "light").strip().lower()
    return SimpleNamespace(**(_DARK if base_normalized == "dark" else _LIGHT))
