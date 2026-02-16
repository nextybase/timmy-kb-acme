# SPDX-License-Identifier: GPL-3.0-or-later
# src/timmy_kb/cli/semantic_facade.py
"""
Porta applicativa per dipendenze del dominio `semantic`.

Obiettivo: ridurre coupling cross-layer (pipeline -> semantic) mantenendo
un singolo punto di import/compatibilita nel layer applicativo (CLI/orchestrazione).
"""

from __future__ import annotations

from semantic.auto_tagger import extract_semantic_candidates

__all__ = ["extract_semantic_candidates"]
