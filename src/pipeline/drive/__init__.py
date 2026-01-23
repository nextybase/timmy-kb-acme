# SPDX-License-Identifier: GPL-3.0-or-later
"""Package interno `drive` (client/download/upload).

Nota:
- Il package non re-esporta API pubbliche: usare `pipeline.drive_utils` come adapter
  ufficiale oppure importare i moduli specifici (`download`, `upload`, `client`).
- I moduli qui dentro non devono essere importati dagli orchestratori.
- Nessun import implicito di sottopacchetti per evitare side effect o ImportError.

Struttura prevista:
- pipeline/drive/client.py    -> bootstrap client GDrive + retry/metriche + primitive read
- pipeline/drive/download.py  -> BFS sottocartelle RAW, download PDF, idempotenza/integrità
- pipeline/drive/upload.py    -> creazione albero da YAML, upload config, delete
"""
