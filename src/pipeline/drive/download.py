# SPDX-License-Identifier: GPL-3.0-or-later
# src/pipeline/drive/download.py
"""
Download da Google Drive (PDF) con scansione gerarchica e idempotenza.

Superficie pubblica (esposta tramite il facade `pipeline.drive_utils`):
- download_drive_pdfs_to_local(service, remote_root_folder_id, local_root_dir, *,
  progress=True, context=None, redact_logs=False) -> (scaricati:int, skippati:int)

Comportamento:
- Scansiona in ampiezza (BFS) le sottocartelle sotto `remote_root_folder_id`.
- Scarica soltanto PDF (mimeType application/pdf o estensione .pdf), replicando
  la gerarchia su disco.
- Idempotenza: se un file locale esiste ed è identico (md5Checksum e/o size) → skip.
- Integrità: dopo il download, verifica l’MD5 locale se disponibile quello remoto.
- Logging strutturato; niente `print()`. Nessuna interazione con l’utente.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Deque, Dict, Optional, Tuple, List
from collections import deque

from googleapiclient.errors import HttpError  # type: ignore
from googleapiclient.http import MediaIoBaseDownload  # type: ignore

from ..exceptions import DriveDownloadError
from ..logging_utils import get_structured_logger
from ..path_utils import sanitize_filename, ensure_within  # STRONG guard per write/delete
from .client import list_drive_files, get_file_metadata, _retry

# Logger di modulo (fallback). In presenza di `context` useremo un logger contestualizzato locale.
logger = get_structured_logger("pipeline.drive.download")

# MIME type cartella e PDF in Google Drive
_FOLDER_MIME = "application/vnd.google-apps.folder"
_PDF_MIME = "application/pdf"


def _maybe_redact(text: str, redact: bool) -> str:
    """Minimizza informazioni sensibili nei log se `redact` è attivo."""
    if not redact or not text:
        return text
    t = str(text)
    if len(t) <= 7:
        return "***"
    return f"{t[:3]}***{t[-3:]}"


def _ensure_dir(path: Path) -> None:
    """Crea la directory se non esiste (idempotente)."""
    path.mkdir(parents=True, exist_ok=True)


def _local_md5(path: Path, chunk_size: int = 1024 * 1024) -> Optional[str]:
    """Calcola l’MD5 di un file locale (hex). Ritorna None se il file non esiste/leggibile."""
    try:
        if not path.is_file():
            return None
        md5 = hashlib.md5()
        with path.open("rb") as fh:
            for chunk in iter(lambda: fh.read(chunk_size), b""):
                md5.update(chunk)
        return md5.hexdigest()
    except Exception:
        return None


def _same_file(local_path: Path, remote_md5: Optional[str], remote_size: Optional[int]) -> bool:
    """
    Determina se un file locale coincide con quello remoto.
    Regole:
    - Se presente MD5 remoto → confronta MD5 (preferito).
    - Altrimenti, se presente `size` remoto → confronta dimensione.
    - Se mancano entrambi → non può garantire identità → False.
    """
    if not local_path.exists():
        return False
    if remote_md5:
        local_md5 = _local_md5(local_path)
        return local_md5 == remote_md5 if local_md5 else False
    if remote_size is not None:
        try:
            return local_path.stat().st_size == int(remote_size)
        except Exception:
            return False
    return False


def _download_file_with_retry(
    service: Any,
    file_id: str,
    out_path: Path,
    *,
    progress: bool = True,
    redact_logs: bool = False,
    chunk_size: int = 1024 * 1024,
    op_name: str = "files.get_media",
    log=None,
) -> None:
    """
    Scarica un singolo file da Drive con retry sull’intera operazione.

    Nota: in caso di errore transiente durante `next_chunk()`, il retry riparte
    dall’inizio del download del singolo file (approccio conservativo e semplice).
    """
    _log = log or logger

    def _op():
        _ensure_dir(out_path.parent)
        with out_path.open("wb") as fh:
            request = service.files().get_media(fileId=file_id, supportsAllDrives=True)
            downloader = MediaIoBaseDownload(fh, request, chunksize=chunk_size)
            done = False
            while not done:
                status, done = downloader.next_chunk()
                if progress and status:
                    try:
                        perc = int(status.progress() * 100)
                        _log.info(
                            "drive.download.chunk",
                            extra={"file_id": _maybe_redact(file_id, redact_logs), "progress_pct": perc},
                        )
                    except Exception:
                        pass
        return True

    _retry(_op, op_name=f"{op_name}:{file_id}")


def download_drive_pdfs_to_local(
    service: Any,
    remote_root_folder_id: str,
    local_root_dir: str | Path,
    *,
    progress: bool = True,
    context: Any | None = None,
    redact_logs: bool = False,
) -> Tuple[int, int]:
    """
    Scarica ricorsivamente i PDF dalla cartella remota in una root locale.

    Parametri:
    - service: client Drive v3.
    - remote_root_folder_id: ID della cartella remota da cui iniziare (tipicamente RAW).
    - local_root_dir: path locale in cui replicare la gerarchia.
    - progress: se True, emette log periodici di avanzamento (inclusi chunk).
    - context: opzionale, per telemetria/metriche (best-effort).
    - redact_logs: se True, minimizza informazioni sensibili nei log.

    Ritorna:
    - (num_scaricati, num_skippati)

    Solleva:
    - DriveDownloadError per errori persistenti/non recuperabili.
    """
    if not remote_root_folder_id:
        raise DriveDownloadError("ID cartella remota mancante.")
    if not local_root_dir:
        raise DriveDownloadError("Percorso locale mancante.")

    # Logger contestualizzato (se abbiamo il contesto), altrimenti fallback al logger di modulo
    local_logger = get_structured_logger("pipeline.drive.download", context=context) if context else logger
    # Redazione: ON se richiesto esplicitamente o se abilitata nel contesto
    redact_logs = bool(redact_logs or (getattr(context, "redact_logs", False) if context is not None else False))

    local_root = Path(local_root_dir)
    _ensure_dir(local_root)

    downloaded = 0
    skipped = 0

    # Coda per BFS: tuple (remote_folder_id, local_dir_path)
    queue: Deque[Tuple[str, Path]] = deque()
    queue.append((remote_root_folder_id, local_root))

    local_logger.info(
        "drive.download.start",
        extra={
            "remote_root": _maybe_redact(remote_root_folder_id, redact_logs),
            "local_root": str(local_root),
        },
    )

    try:
        while queue:
            current_remote_id, current_local_dir = queue.popleft()

            # STRONG guard: la dir corrente deve essere sotto la root locale
            try:
                ensure_within(local_root, current_local_dir)
            except Exception:
                local_logger.warning(
                    "drive.download.skip_unsafe_dir",
                    extra={"folder_path": str(current_local_dir)},
                )
                continue

            # Garantisce la presenza della cartella locale del livello corrente
            _ensure_dir(current_local_dir)

            # Percorso relativo per logging (solo diagnostica)
            try:
                rel = current_local_dir.relative_to(local_root).as_posix() or "."
            except Exception:
                rel = current_local_dir.as_posix()

            local_logger.info("drive.download.folder", extra={"folder_path": rel})

            # 1) Sottocartelle del livello corrente (BFS)
            subfolders = list_drive_files(
                service,
                current_remote_id,
                query=f"mimeType = '{_FOLDER_MIME}'",
            )
            for folder in subfolders:
                fid = folder.get("id")
                fname = sanitize_filename(folder.get("name") or "senza_nome")
                next_dir = current_local_dir / fname
                # validazione STRONG anche sugli enqueued path
                try:
                    ensure_within(local_root, next_dir)
                    queue.append((fid, next_dir))
                except Exception:
                    local_logger.warning(
                        "drive.download.skip_unsafe_dir",
                        extra={"folder_path": str(next_dir)},
                    )

            # 2) PDF nel livello corrente
            pdfs = list_drive_files(
                service,
                current_remote_id,
                query=f"mimeType = '{_PDF_MIME}'",
            )
            for f in pdfs:
                file_id = f.get("id")
                remote_name = f.get("name") or "download.pdf"
                safe_name = sanitize_filename(
                    remote_name if remote_name.lower().endswith(".pdf") else f"{remote_name}.pdf"
                )
                out_path = current_local_dir / safe_name

                # STRONG guard: l'output deve rimanere dentro la root locale
                try:
                    ensure_within(local_root, out_path)
                except Exception:
                    local_logger.warning(
                        "drive.download.skip_unsafe_path",
                        extra={"file_id": _maybe_redact(file_id, redact_logs), "file_path": str(out_path)},
                    )
                    continue

                # Metadati per idempotenza/integrità (con retry lato client)
                try:
                    meta = get_file_metadata(
                        service,
                        file_id,
                        fields="id, name, mimeType, size, md5Checksum",
                    )
                except Exception:
                    meta = {}

                remote_md5 = meta.get("md5Checksum")
                remote_size = int(meta["size"]) if meta.get("size") is not None else None

                # Idempotenza
                if _same_file(out_path, remote_md5, remote_size):
                    skipped += 1
                    if progress and (skipped % 50 == 0):
                        local_logger.info(
                            "drive.download.progress",
                            extra={"downloaded": downloaded, "skipped": skipped, "last": safe_name},
                        )
                    continue

                # Download con retry e progress chunk
                _download_file_with_retry(
                    service,
                    file_id,
                    out_path,
                    progress=progress,
                    redact_logs=redact_logs,
                    log=local_logger,
                )

                # Verifica integrità post-download (se md5 remoto disponibile)
                if remote_md5:
                    local_md5 = _local_md5(out_path)
                    if not local_md5 or local_md5 != remote_md5:
                        # Rimozione best-effort del file corrotto per idempotenza retry futuri
                        try:
                            ensure_within(local_root, out_path)
                            out_path.unlink(missing_ok=True)  # type: ignore[arg-type]
                        except Exception:
                            pass
                        raise DriveDownloadError(
                            f"MD5 mismatch dopo download per file '{remote_name}' (id={file_id})"
                        )

                downloaded += 1
                if progress and (downloaded % 25 == 0):
                    local_logger.info(
                        "drive.download.progress",
                        extra={"downloaded": downloaded, "skipped": skipped, "last": safe_name},
                    )

    except DriveDownloadError:
        # Errori specifici: li logghiamo e rilanciamo
        local_logger.error(
            "drive.download.error",
            extra={
                "remote_root": _maybe_redact(remote_root_folder_id, redact_logs),
                "downloaded": downloaded,
                "skipped": skipped,
            },
        )
        raise
    except Exception as e:  # noqa: BLE001
        # Qualsiasi altro errore → mappiamo a DriveDownloadError
        local_logger.exception(
            "drive.download.unexpected_error",
            extra={
                "remote_root": _maybe_redact(remote_root_folder_id, redact_logs),
                "exc_type": type(e).__name__,
                "message": str(e)[:300],
                "downloaded": downloaded,
                "skipped": skipped,
            },
        )
        raise DriveDownloadError(f"Errore durante il download da Drive: {e}") from e

    local_logger.info("drive.download.done", extra={"downloaded": downloaded, "skipped": skipped})

    # Compatibilità con orchestratori che annotano lo stato step nel contesto
    try:
        if context is not None and hasattr(context, "set_step_status"):
            context.set_step_status("drive_retries", "0")  # best-effort
    except Exception:
        pass

    return downloaded, skipped


__all__ = ["download_drive_pdfs_to_local"]
