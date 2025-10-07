"""Helper puri per la gestione dello stato applicativo della UI."""

from __future__ import annotations

from ui.utils.workspace import has_raw_pdfs

STATE_MANAGE_READY = {"inizializzato", "pronto", "arricchito", "finito"}
STATE_SEM_READY = {"pronto", "arricchito", "finito"}

__all__ = [
    "STATE_MANAGE_READY",
    "STATE_SEM_READY",
    "normalize_state",
    "compute_home_enabled",
    "compute_manage_enabled",
    "compute_sem_enabled",
]


def normalize_state(state: str | None) -> str:
    """Restituisce lo stato normalizzato (lowercase, trimmed)."""
    return (state or "").strip().lower()


def compute_home_enabled(state: str | None, slug: str | None) -> bool:
    """Determina se la tab Home deve essere abilitata."""
    normalized = normalize_state(state)
    if normalized in STATE_MANAGE_READY:
        return True
    return bool((slug or "").strip())


def compute_manage_enabled(state: str | None, slug: str | None) -> bool:
    """Determina se la tab Gestisci cliente deve essere abilitata."""
    _ = slug
    return normalize_state(state) in STATE_MANAGE_READY


def compute_sem_enabled(state: str | None, slug: str | None) -> bool:
    """Determina se la tab Semantica deve essere abilitata."""
    if normalize_state(state) not in STATE_SEM_READY:
        return False
    ready, _ = has_raw_pdfs(slug)
    return bool(ready)
