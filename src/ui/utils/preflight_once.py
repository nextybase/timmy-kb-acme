"""Utility per gestire il bypass del preflight su singola run."""

from __future__ import annotations

from typing import Any, MutableMapping, Optional


def apply_preflight_once(
    skip_once: bool,
    session_state: MutableMapping[str, Any],
    logger: Optional[Any] = None,
) -> bool:
    """
    Applica il bypass del preflight **solo per questa esecuzione**.

    - Non modifica preferenze persistenti.
    - È idempotente nella stessa sessione (loggato una sola volta).

    Ritorna:
        True se il bypass è attivo per questa run, False altrimenti.
    """
    if not skip_once:
        return False

    if session_state.get("_preflight_once_applied", False):
        session_state["preflight_ok"] = True
        return True

    session_state["preflight_ok"] = True
    session_state["_preflight_once_applied"] = True

    if logger is not None:
        try:
            logger.info("ui.preflight.once", extra={"mode": "one_shot"})
        except Exception:
            pass
    return True
