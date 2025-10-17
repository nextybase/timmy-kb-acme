# SPDX-License-Identifier: GPL-3.0-or-later
# src/pipeline/drive_utils.py
"""
Facade compatibile per le utility Google Drive della pipeline Timmy-KB.

Obiettivo
---------
- Mantenere invariata l'API pubblica storica (`pipeline.drive_utils.*`) delegando
  l'implementazione ai moduli interni:
  - `pipeline.drive.client`   → client e primitive di lettura/elenco
  - `pipeline.drive.upload`   → creazione/albero/upload e struttura locale
  - `pipeline.drive.download` → download dei contenuti (PDF, ecc.)

Note
----
- Questo file non contiene logica di business: effettua solo import statici e re-export.
  In questo modo evitiamo import `lazy` a runtime e rischi di cicli/race.
- Compat test: riesporta `MIME_FOLDER`, `MIME_PDF` e `MediaIoBaseDownload` per
  compatibilità con i test che monkeypatchano questi simboli a livello di facciata.
- Gli orchestratori e il resto del codice continuano a importare da qui.

Funzioni/Costanti riesportate (ruolo sintetico)
-----------------------------------------------
Client/Lettura:
- `get_drive_service(context)` → istanzia client Drive v3 (Service Account).
- `list_drive_files(service, **query)` → elenca file/cartelle (paginato).
- `get_file_metadata(service, file_id)` → metadata (mimeType, name, parents, ecc.).
- `_retry(fn, *args, **kwargs)` → helper interno (ri-esportato per test avanzati).

Upload/Strutture:
- `create_drive_folder(service, name, parent_id, ...)` → crea una cartella.
- `create_drive_structure_from_yaml(service, yaml_path, client_folder_id, ...)`
  → albero Drive da YAML.
- `upload_config_to_drive_folder(service, context, parent_id, ...)` → carica config.
- `delete_drive_file(service, file_id)` → rimozione file/cartella.
- `create_local_base_structure(context, yaml_structure_file)` → struttura locale.

Download:
- `download_drive_pdfs_to_local(service, remote_root_folder_id, local_root_dir, ...)`
  → scarica PDF su sandbox locale.

Redazione/Logging:
- La redazione dei log (token, ID) e l'auditing sono gestiti nei moduli implementativi.
  Questa facciata resta volutamente `thin` e priva di side effect.
"""

from __future__ import annotations

# ---------------------- Classe MediaIoBaseDownload (hard import) --------------------
from googleapiclient.http import MediaIoBaseDownload as MediaIoBaseDownload

# ------------------------------------ Costanti MIME --------------------------------
from .constants import GDRIVE_FOLDER_MIME as MIME_FOLDER
from .constants import PDF_MIME_TYPE as MIME_PDF

# ----------------------------------- Client/lettura --------------------------------
from .drive.client import _retry  # export interno per test avanzati
from .drive.client import get_drive_service, get_file_metadata, list_drive_files

# -------------------------------------- Download -----------------------------------
from .drive.download import download_drive_pdfs_to_local

# --------------------------- Creazione/albero/upload/local --------------------------
from .drive.upload import (
    create_drive_folder,
    create_drive_minimal_structure,
    create_drive_structure_from_yaml,
    create_local_base_structure,
    delete_drive_file,
    upload_config_to_drive_folder,
)

# --------------------------------- Superficie pubblica ------------------------------

__all__: list[str] = [
    # costanti / compat test
    "MIME_FOLDER",
    "MIME_PDF",
    "MediaIoBaseDownload",
    # client / lettura
    "get_drive_service",
    "list_drive_files",
    "get_file_metadata",
    "_retry",
    # upload / strutture
    "create_drive_folder",
    "create_drive_minimal_structure",
    "create_drive_structure_from_yaml",
    "upload_config_to_drive_folder",
    "delete_drive_file",
    "create_local_base_structure",
    # download
    "download_drive_pdfs_to_local",
]
