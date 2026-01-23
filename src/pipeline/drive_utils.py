# SPDX-License-Identifier: GPL-3.0-or-later
# src/pipeline/drive_utils.py
"""
Adapter strict per le utility Google Drive della pipeline Timmy-KB.

Obiettivo
---------
- Esporre una superficie pubblica minimale e dichiarativa per la capability Drive,
  delegando l'implementazione ai moduli interni:
  - `pipeline.drive.client`   -> client e primitive di lettura/elenco
  - `pipeline.drive.upload`   -> creazione/albero/upload e struttura locale
  - `pipeline.drive.download` -> download dei contenuti (PDF, ecc.)

Note
----
- Questo file non contiene logica di business: effettua solo import statici e re-export.
- Gli orchestratori e il resto del codice importano da qui.

Funzioni riesportate (ruolo sintetico)
--------------------------------------
Client/Lettura:
- `get_drive_service(context)` -> istanzia client Drive v3 (Service Account).
- `list_drive_files(service, **query)` -> elenca file/cartelle (paginato).
- `get_file_metadata(service, file_id)` -> metadata (mimeType, name, parents, ecc.).

Upload/Strutture:
- `create_drive_folder(service, name, parent_id, ...)` -> crea una cartella.
- `create_drive_minimal_structure(service, client_folder_id, ...)` -> struttura base (raw + contrattualistica).
- `upload_config_to_drive_folder(service, context, parent_id, ...)` -> carica config.
- `delete_drive_file(service, file_id)` -> rimozione file/cartella.

Download:
- `download_drive_pdfs_to_local(service, remote_root_folder_id, local_root_dir, ...)`
  -> scarica PDF su sandbox locale.

Redazione/Logging:
- La redazione dei log (token, ID) e l'auditing sono gestiti nei moduli implementativi.
  Questo adapter resta `thin` e privo di side effect.
"""

from __future__ import annotations

# ----------------------------------- Client/lettura --------------------------------
from .drive.client import get_drive_service, get_file_metadata, list_drive_files

# -------------------------------------- Download -----------------------------------
from .drive.download import download_drive_pdfs_to_local

# --------------------------- Creazione/albero/upload/local --------------------------
from .drive.upload import (
    create_drive_folder,
    create_drive_minimal_structure,
    delete_drive_file,
    upload_config_to_drive_folder,
)

# --------------------------------- Superficie pubblica ------------------------------

__all__: list[str] = [
    # client / lettura
    "get_drive_service",
    "list_drive_files",
    "get_file_metadata",
    # upload / strutture
    "create_drive_folder",
    "create_drive_minimal_structure",
    "upload_config_to_drive_folder",
    "delete_drive_file",
    # download
    "download_drive_pdfs_to_local",
]
