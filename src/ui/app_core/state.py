# SPDX-License-Identifier: GPL-3.0-or-later
# src/ui/app_core/state.py
from __future__ import annotations

"""
Costanti per lo stato/fasi lato UI (contratto unico 1.0 Beta).

- Lo stato cliente persistito usa sempre l'italiano ed è definito in `ui.constants`.
- Le fasi UI del wizard sono effimere (session_state) e restano in italiano.
"""


from ..constants import UI_PHASE_INIT, UI_PHASE_PROVISIONED, UI_PHASE_READY_TO_OPEN

# Fasi UI in italiano (SSoT)
UI_PAGE_PHASES = {UI_PHASE_INIT, UI_PHASE_READY_TO_OPEN, UI_PHASE_PROVISIONED}


def normalize_ui_phase(phase: str | None) -> str:
    """
    Normalizza alle fasi italiane correnti (contratto unico).
    """
    p = (phase or "").strip()
    mapping: dict[str, str] = {
        UI_PHASE_INIT: UI_PHASE_INIT,
        UI_PHASE_READY_TO_OPEN: UI_PHASE_READY_TO_OPEN,
        UI_PHASE_PROVISIONED: UI_PHASE_PROVISIONED,
    }
    return mapping.get(p, UI_PHASE_INIT)
