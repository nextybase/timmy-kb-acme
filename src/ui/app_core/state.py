# SPDX-License-Identifier: GPL-3.0-or-later
# src/ui/app_core/state.py
from __future__ import annotations

"""
Compatibilità e costanti per lo stato/fasi lato UI.

- Lo stato cliente persistito usa sempre l'italiano ed è definito in `ui.constants`.
- Le fasi UI del wizard sono effimere (session_state) e restano in italiano.
"""


from ..constants import SEMANTIC_READY_STATES  # SSoT per gating "Semantica"
from ..constants import UI_PHASE_INIT  # "iniziale"
from ..constants import UI_PHASE_PROVISIONED  # "predisposto"
from ..constants import UI_PHASE_READY_TO_OPEN  # "pronto_apertura"

# Fasi UI in italiano (SSoT)
UI_PAGE_PHASES = {UI_PHASE_INIT, UI_PHASE_READY_TO_OPEN, UI_PHASE_PROVISIONED}


def normalize_ui_phase(phase: str | None) -> str:
    """
    Normalizza eventuali valori storici/inglesi alle fasi italiane correnti.
    Utile per letture di compatibilità da session_state o query param.
    """
    p = (phase or "").strip()
    mapping: dict[str, str] = {
        # Inglese -> Italiano (compat)
        "init": UI_PHASE_INIT,
        "ready_to_open": UI_PHASE_READY_TO_OPEN,
        "provisioned": UI_PHASE_PROVISIONED,
        # Italiano -> Italiano (idempotente)
        UI_PHASE_INIT: UI_PHASE_INIT,
        UI_PHASE_READY_TO_OPEN: UI_PHASE_READY_TO_OPEN,
        UI_PHASE_PROVISIONED: UI_PHASE_PROVISIONED,
    }
    return mapping.get(p) or UI_PHASE_INIT


# (Facoltativo) Alias di compat per codice vecchio che importava STATE_SEM_READY:
# Meglio usare direttamente ui.constants.SEMANTIC_READY_STATES.
STATE_SEM_READY = SEMANTIC_READY_STATES
