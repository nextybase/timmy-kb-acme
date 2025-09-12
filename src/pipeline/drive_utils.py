# SPDX-License-Identifier: GPL-3.0-or-later
# src/pipeline/drive_utils.py
"""
Facade compatibile per le utility Google Drive della pipeline Timmy-KB.

Obiettivo
---------
- Mantenere **invariata** l'API pubblica storica (`pipeline.drive_utils.*`) delegando
  Implementazione ai moduli interni suddivisi:
  - `pipeline.drive.client`   → client e primitive di lettura/elenco
  - `pipeline.drive.upload`   → creazione/albero/upload e struttura locale
  - `pipeline.drive.download` → download dei contenuti (PDF, ecc.)

Note
----
- Questo file non contiene logica di business: effettua solo import **statici** e re-export.
  In questo modo evitiamo import “lazy” a runtime e ogni rischio di cicli/race.
- **Compat test**: riesporta `MIME_FOLDER`, `MIME_PDF` e `MediaIoBaseDownload` per
  compatibilità con i test che monkeypatchano questi simboli a livello di facciata.
- Gli orchestratori e il resto del codice continuano a importare da qui.

Funzioni/Costanti riesportate (ruolo sintetico)
-----------------------------------------------
Client/Lettura:
- `get_drive_service(context)` → istanzia client Drive v3 (Service Account), con redazione log a valle.
- `list_drive_files(service, **query)` → elenca file/cartelle (paginato).
- `get_file_metadata(service, file_id)` → metadata di un file (mimeType, name, parents, ecc.).
- `_retry(fn, *args, **kwargs)` → helper interno (ri-esportato per test avanzati).

Upload/Strutture:
- `create_drive_folder(service, name, parent_id, ...)` → crea una cartella.
- `create_drive_structure_from_yaml(service, yaml_path, client_folder_id, ...)` → albero Drive da YAML.
- `upload_config_to_drive_folder(service, context, parent_id, ...)` → carica `config.yaml`.
- `delete_drive_file(service, file_id)` → rimozione file/cartella.
- `create_local_base_structure(context, yaml_structure_file)` → struttura locale (mirror parziale).

Download:
- `download_drive_pdfs_to_local(service, remote_root_folder_id, local_root_dir, ...)` → scarica PDF su sandbox locale.

Redazione/Logging:
- La redazione dei log (token, ID) e i dettagli di auditing sono gestiti **nei moduli implementativi**.
  Questa facciata resta volutamente “thin” e priva di side effect.
"""

from __future__ import annotations
from typing import Any
from pathlib import Path

# ---------------------------------- Costanti MIME ----------------------------------
# Alcuni test si aspettano che le costanti MIME siano accessibili come:
#   DU.MIME_FOLDER  /  DU.MIME_PDF
try:
    from .constants import GDRIVE_FOLDER_MIME as MIME_FOLDER, PDF_MIME_TYPE as MIME_PDF
except Exception:  # pragma: no cover - fallback sicuro per ambienti minimi
    # Fallback conservativo: valori standard noti
    MIME_FOLDER = "application/vnd.google-apps.folder"
    MIME_PDF = "application/pdf"

# ------------------------ Classe MediaIoBaseDownload (compat) ----------------------
# I test patchano DU.MediaIoBaseDownload; la riesportiamo dal pacchetto googleapiclient
# se disponibile, altrimenti forniamo un placeholder (sostituibile via monkeypatch).
try:  # pragma: no cover - dipendenza opzionale in ambienti CI minimali
    from googleapiclient.http import MediaIoBaseDownload as _GAPI_MediaIoBaseDownload

    MediaIoBaseDownload: Any = _GAPI_MediaIoBaseDownload
except Exception:  # pragma: no cover

    class _MediaIoBaseDownloadPlaceholder:
        """Placeholder per `googleapiclient.http.MediaIoBaseDownload`.

        Viene definito solo se la libreria `google-api-python-client` non è presente.
        È pensato per essere rimpiazzato nei test con `monkeypatch.setattr(...)`.
        Qualsiasi istanziazione diretta solleva un ImportError esplicito.
        """

        def __init__(self: Any, *args: Any, **kwargs: Any) -> None:
            raise ImportError(
                "googleapiclient non installato: `MediaIoBaseDownload` è un placeholder. "
                "Installa `google-api-python-client` oppure monkeypatcha questa classe nei test."
            )

    MediaIoBaseDownload = _MediaIoBaseDownloadPlaceholder


# ----------------------------- Import espliciti (statici) --------------------------

# Client/lettura (Drive v3)
try:
    from .drive.client import (
        get_drive_service,
        list_drive_files,
        get_file_metadata,
        _retry,  # export interno per test avanzati
    )
except Exception as e:  # pragma: no cover
    raise ImportError(
        "Impossibile importare 'pipeline.drive.client'. Verifica dipendenze e path."
    ) from e

# Creazione/albero/upload/struttura locale
try:
    from .drive.upload import (
        create_drive_folder,
        create_drive_structure_from_yaml,
        upload_config_to_drive_folder,
        delete_drive_file,
        create_local_base_structure,
    )
except Exception as e:  # pragma: no cover
    raise ImportError(f"Impossibile importare 'pipeline.drive.upload': {e}") from e

# Download (opzionale ma consigliato). Se non presente, forniamo un errore chiaro a chiamata.
try:  # noqa: SIM105
    from .drive.download import download_drive_pdfs_to_local
except Exception:
    # Fallback: definisce uno stub che guida l'utente a includere il modulo mancante.
    def download_drive_pdfs_to_local(
        service: Any,
        remote_root_folder_id: str,
        local_root_dir: Path,
        *,
        progress: bool = False,
        context: Any | None = None,
        redact_logs: bool = False,
        chunk_size: int = 8 * 1024 * 1024,
    ) -> int:
        """Stub: modulo 'pipeline.drive.download' non disponibile.

        Questo placeholder viene definito solo se l'import del modulo reale fallisce.
        """
        raise ImportError(
            "Funzione 'download_drive_pdfs_to_local' non disponibile: manca 'pipeline.drive.download'. "
            "Aggiungi 'src/pipeline/drive/download.py' oppure aggiorna l'installazione del pacchetto."
        )


# ----------------------------- Superficie pubblica ---------------------------------

__all__ = [
    # costanti/compat test
    "MIME_FOLDER",
    "MIME_PDF",
    "MediaIoBaseDownload",
    # client/lettura
    "get_drive_service",
    "list_drive_files",
    "get_file_metadata",
    "_retry",
    # upload/strutture
    "create_drive_folder",
    "create_drive_structure_from_yaml",
    "upload_config_to_drive_folder",
    "delete_drive_file",
    "create_local_base_structure",
    # download
    "download_drive_pdfs_to_local",
]
