# SPDX-License-Identifier: GPL-3.0-or-later
# src/ui/constants.py
from __future__ import annotations

"""
Costanti condivise per lo stato cliente (persistito) e note sulle fasi UI.

- Lo **stato cliente** è salvato nel registry (SSoT) gestito da `ui.clients_store`
  nel campo `stato` e usa SOLO valori in italiano.
- Le **fasi UI** (es. wizard "Nuovo cliente") sono stati effimeri di interfaccia,
  NON vengono persistiti e possono restare in inglese senza impattare la logica.

Usare SEMANTIC_READY_STATES ovunque serva il gating della scheda "Semantica".
"""

# Nome del campo nel registry clienti (per chiarezza)
CLIENT_STATE_FIELD = "stato"

# Stati cliente ammessi per abilitare la scheda "Semantica"
SEMANTIC_READY_STATES = {"pronto", "arricchito", "finito"}

# Facoltativo: elenco di stati "conosciuti" (può servire per validazioni o UI)
KNOWN_CLIENT_STATES = {"nuovo", "pronto", "arricchito", "finito"}

# Nota: le fasi UI NON sono persistite nel registry clienti.
# Esempi (solo UI): {"init", "ready_to_open", "provisioned"}
