# SPDX-License-Identifier: GPL-3.0-or-later
# src/ui/constants.py
from __future__ import annotations

"""
Costanti condivise per lo stato cliente (persistito) e le fasi UI (contratto unico 1.0 Beta).

- Lo **stato cliente** è salvato nel registry (SSoT) gestito da `ui.clients_store`
  nel campo `stato` e usa SOLO valori in italiano.
- Le **fasi UI** (wizard "Nuovo cliente") sono stati effimeri di interfaccia e restano in italiano.

Usa SEMANTIC_ENTRY_STATES per il gating della scheda "Semantica"
e SEMANTIC_READY_STATES per le funzioni disponibili solo a stato arricchito/finito (es. preview).
"""

# Nome del campo nel registry clienti (per chiarezza)
CLIENT_STATE_FIELD = "stato"

# Stati "ready" per preview/finishing
SEMANTIC_READY_STATES = {"arricchito", "finito"}

# Stati che consentono l'accesso alla pagina "Semantica" (dopo la conversione)
SEMANTIC_ENTRY_STATES = SEMANTIC_READY_STATES | {"pronto"}
SEMANTIC_GATING_MESSAGE = (
    "La semantica è disponibile da stato 'pronto' in poi e richiede Markdown presenti in `normalized/`."
)

# Facoltativo: elenco di stati "conosciuti" (può servire per validazioni o UI)
KNOWN_CLIENT_STATES = {"nuovo", "pronto", "arricchito", "finito"}

# Nota: le fasi UI NON sono persistite nel registry clienti.
# Esempi (solo UI): {"iniziale", "pronto_apertura", "predisposto"}

# Fasi UI (wizard Nuovo cliente) in italiano (contratto unico)
UI_PHASE_INIT = "iniziale"
UI_PHASE_READY_TO_OPEN = "pronto_apertura"
UI_PHASE_PROVISIONED = "predisposto"
