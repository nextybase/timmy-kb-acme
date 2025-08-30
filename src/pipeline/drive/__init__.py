# SPDX-License-Identifier: GPL-3.0-or-later
"""
Package interno 'drive' (client/download/upload).

⚠️ Nota:
- L'API pubblica resta esposta da `pipeline.drive_utils` (facade/shim).
- I moduli qui dentro NON devono essere importati dagli orchestratori.
- Questo file è safe-to-push anche senza gli altri moduli: non importa
  sottopacchetti per evitare ImportError finché non vengono creati.

Struttura prevista:
- pipeline/drive/client.py    → bootstrap client GDrive + retry/metriche + primitive read
- pipeline/drive/download.py  → BFS sottocartelle RAW, download PDF, idempotenza/integrità
- pipeline/drive/upload.py    → creazione albero da YAML, upload config, delete
"""

# Espone i sotto-moduli previsti; l'import effettivo è gestito dalla facade `drive_utils`.
__all__ = []
