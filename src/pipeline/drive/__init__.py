# SPDX-License-Identifier: GPL-3.0-or-later
"""
Package interno 'drive' (client/download/upload).

âš ï¸ Nota:
- L'API pubblica resta esposta da `pipeline.drive_utils` (facade/shim).
- I moduli qui dentro NON devono essere importati dagli orchestratori.
- Questo file Ã¨ safe-to-push anche senza gli altri moduli: non importa
  sottopacchetti per evitare ImportError finchÃ© non vengono creati.

Struttura prevista:
- pipeline/drive/client.py    â†’ bootstrap client GDrive + retry/metriche + primitive read
- pipeline/drive/download.py  â†’ BFS sottocartelle RAW, download PDF, idempotenza/integritÃ 
- pipeline/drive/upload.py    â†’ creazione albero da YAML, upload config, delete
"""

# Espone i sotto-moduli previsti; l'import effettivo Ã¨ gestito dalla facade `drive_utils`.
from typing import List

__all__: List[str] = []
