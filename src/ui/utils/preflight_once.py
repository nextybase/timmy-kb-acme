# SPDX-License-Identifier: GPL-3.0-only
"""Utility per gestire lo stato del preflight nella UI."""

from __future__ import annotations

from typing import Any, MutableMapping, Optional


def apply_preflight_once(
    skip_once: bool,
    session_state: MutableMapping[str, Any],
    logger: Optional[Any] = None,
) -> bool:
    """
    Ritorna sempre False (nessun effetto su session_state).
    """
    if logger is not None:
        try:
            if skip_once:
                logger.warning("ui.preflight.once.disabled", extra={"disabled": True})
        except Exception:
            pass
    return False
