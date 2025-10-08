# SPDX-License-Identifier: GPL-3.0-or-later
# src/ui/app_core/state.py
"""
State helpers (Beta 0).

- Niente retrocompatibilità con router/switcher a tab.
- Nessuna dipendenza da util di UI (no has_raw_pdfs, no workspace utils).
- Le pagine principali restano sempre accessibili; eventuali "gate"
  sono gestiti localmente nelle pagine (es. Semantica controlla RAW).
"""

from __future__ import annotations

from typing import Optional

__all__ = [
    "normalize_state",
    "STATE_SEM_READY",
    "compute_home_enabled",
    "compute_manage_enabled",
]

# Manteniamo un set di stati "ready" solo per compatibilità con eventuali import.
STATE_SEM_READY: set[str] = {"ready", "ready_to_open", "open"}


def normalize_state(phase: Optional[str]) -> str:
    """Normalizza la stringa di stato (lower/trim)."""
    if phase is None:
        return ""
    return str(phase).strip().lower()


def compute_home_enabled(state: Optional[str], slug: Optional[str]) -> bool:
    """La pagina Home è sempre disponibile in Beta 0."""
    _ = (state, slug)  # non usati
    return True


def compute_manage_enabled(state: Optional[str], slug: Optional[str]) -> bool:
    """
    La pagina Gestisci cliente resta sempre disponibile (creazione/gestione workspace,
    Drive, diff, tagging). Non dipende dalla presenza di PDF o dallo stato.
    """
    _ = (state, slug)  # non usati
    return True
