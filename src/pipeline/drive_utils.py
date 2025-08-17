# src/pipeline/drive_utils.py
"""
Utility Google Drive per la pipeline:

- Inizializzazione client (Service Account)
- Creazione / elenco / cancellazione cartelle e file (compatibile con Shared Drives)
- Creazione struttura remota da YAML (supporto formato mapping e legacy root_folders)
- Creazione struttura locale convenzionale (raw/book/config) con categorie SOLO da RAW/raw
- Upload di config.yaml
- Download PDF idempotente con verifica md5/size e file handle sicuri

Requisiti: variabili d'ambiente/contesto per SERVICE_ACCOUNT_FILE (e DRIVE_ID a livello orchestratore).
"""

from __future__ import annotations

import hashlib
import time
import random
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import yaml
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload

from pipeline.exceptions import ConfigError, DriveDownloadError, DriveUploadError
from pipeline.logging_utils import get_structured_logger
from pipeline.path_utils import sanitize_filename

logger = get_structured_logger("pipeline.drive_utils")

# ---------------------------------------------------------
# Costanti / Scope
# ---------------------------------------------------------
DRIVE_SCOPES = ["https://www.googleapis.com/auth/drive"]
MIME_FOLDER = "application/vnd.google-apps.folder"
MIME_PDF = "application/pdf"


# ---------------------------------------------------------
# Helpers locali
# ---------------------------------------------------------
def _md5sum(path: Path, chunk_size: int = 1024 * 1024) -> str:
    """Calcola l’MD5 del file in streaming (robusto su file grandi)."""
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            h.update(chunk)
    return h.hexdigest()


def _retry(fn: Callable[[], Any], *, tries: int = 3, delay: float = 0.8, backoff: float = 1.6):
    """Retry esponenziale per chiamate Drive (HttpError) con jitter per evitare retry sincronizzati."""
    _delay = delay
    for attempt in range(1, tries + 1):
        try:
            return fn()
        except HttpError as e:
            if attempt >= tries:
                raise
            status = getattr(e, "resp", None).status if getattr(e, "resp", None) else "?"
            logger.warning(
                f"HTTP {status} su Drive; retry {attempt}/{tries}",
                extra={"error": str(e)},
            )
            # jitter: +/- 30% del delay corrente
            jitter = 1.0 + random.uniform(-0.3, 0.3)
            time.sleep(max(0.0, _delay * jitter))
            _delay *= backoff


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _normalize_yaml_structure(data: Any) -> Dict[str, Any]:
    """
    Normalizza la struttura YAML della gerarchia remota.

    Accetta:
      1) Mapping moderno: { RAW: {categoria: {}}, YAML: {} }
      2) Legacy: { root_folders: [ {name: "raw", subfolders: [...]}, ... ] }

    Ritorna sempre un dict annidato {nome: {sotto: {...}}}.
    (N.B. qui NON aggiungiamo alias RAW/YAML per evitare doppioni su Drive;
    eventuali alias sono aggiunti SOLO nel valore di ritorno di
    create_drive_structure_from_yaml.)
    """
    if isinstance(data, dict) and "root_folders" in data and isinstance(data["root_folders"], list):
        def to_map(items: List[dict]) -> Dict[str, Any]:
            out: Dict[str, Any] = {}
            for it in items:
                name = it.get("name")
                subs = it.get("subfolders", [])
                out[name] = to_map(subs) if subs else {}
            return out

        mapping = to_map(data["root_folders"])
    elif isinstance(data, dict):
        mapping = data
    else:
        raise ConfigError("Formato YAML non supportato per la struttura cartelle.")
    return mapping


# ---------------------------------------------------------
# Inizializzazione client
# ---------------------------------------------------------
def get_drive_service(context_or_sa_file: Any, drive_id: Optional[str] = None):
    """
    Inizializza il client Google Drive (v3).

    Args:
        context_or_sa_file: oggetto con .env['SERVICE_ACCOUNT_FILE'] oppure Path/str al JSON del Service Account.
        drive_id: non utilizzato qui; mantenuto per compat futura.

    Returns:
        service Drive v3
    """
    if hasattr(context_or_sa_file, "env"):
        sa_path = context_or_sa_file.env.get("SERVICE_ACCOUNT_FILE")
        if not sa_path:
            raise ConfigError("SERVICE_ACCOUNT_FILE non impostato nel contesto")
        sa_path = Path(sa_path)
    else:
        sa_path = Path(context_or_sa_file)

    if not sa_path.exists():
        raise ConfigError(f"Service Account file non trovato: {sa_path}", file_path=sa_path)

    creds = Credentials.from_service_account_file(str(sa_path), scopes=DRIVE_SCOPES)
    service = build("drive", "v3", credentials=creds, cache_discovery=False)
    return service


# ---------------------------------------------------------
# Operazioni di base (Shared Drives compat)
# ---------------------------------------------------------
def create_drive_folder(service, name: str, parent_id: Optional[str] = None) -> str:
    """
    Crea una cartella su Drive e ritorna l'ID (compatibile con Shared Drives).

    Idempotenza: se sotto `parent_id` esiste già una cartella con lo stesso `name`,
    riusa quell'ID invece di crearne una nuova.
    """
    # Lookup preventivo per idempotenza
    if parent_id:
        try:
            existing = list_drive_files(
                service,
                parent_id,
                query=f"name = '{name}' and mimeType = '{MIME_FOLDER}'",
            )
            if existing:
                folder_id = existing[0].get("id")
                if folder_id:
                    logger.info(f"↺ Riutilizzo cartella esistente '{name}' ({folder_id}) sotto parent {parent_id}")
                    return folder_id
        except Exception as e:
            logger.warning(f"Lookup cartella '{name}' fallito, procedo con creazione: {e}")

    file_metadata = {"name": name, "mimeType": MIME_FOLDER}
    if parent_id:
        file_metadata["parents"] = [parent_id]

    def _do():
        return service.files().create(
            body=file_metadata,
            fields="id",
            supportsAllDrives=True,
        ).execute()

    try:
        res = _retry(_do)
    except HttpError as e:
        # 404 tipico quando il SA non è membro della Drive/parent o l'ID parent è errato
        if getattr(e, "resp", None) and getattr(e.resp, "status", None) == 404 and parent_id:
            raise DriveUploadError(
                f"Parent non trovato o non accessibile: {parent_id}. "
                f"Verifica DRIVE_ID oppure usa DRIVE_PARENT_FOLDER_ID; "
                f"assicurati che il Service Account sia membro della Shared Drive/cartella."
            ) from e
        raise

    folder_id = res.get("id")
    if not folder_id:
        raise DriveUploadError(f"Impossibile creare cartella Drive '{name}'")
    return folder_id


def list_drive_files(service, parent_id: str, query: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Elenca file sotto una cartella Drive.

    Args:
        parent_id: ID della cartella padre
        query: filtro addizionale (es. "mimeType='application/pdf'")

    Returns:
        Lista di dict con campi: id, name, mimeType, md5Checksum, size
    """
    base_q = f"'{parent_id}' in parents and trashed = false"
    q = f"{base_q} and {query}" if query else base_q

    results: List[Dict[str, Any]] = []
    page_token: Optional[str] = None
    while True:
        def _do():
            return (
                service.files()
                .list(
                    q=q,
                    spaces="drive",
                    fields="nextPageToken, files(id, name, mimeType, md5Checksum, size)",
                    pageToken=page_token,
                    includeItemsFromAllDrives=True,
                    supportsAllDrives=True,
                )
                .execute()
            )

        resp = _retry(_do)
        files = resp.get("files", [])
        results.extend(files)
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    return results


def delete_drive_file(service, file_id: str) -> None:
    """Cancella un file su Drive per ID."""
    def _do():
        return service.files().delete(fileId=file_id, supportsAllDrives=True).execute()

    _retry(_do)


def upload_config_to_drive_folder(service, context, parent_id: str) -> str:
    """
    Carica la config del cliente su Drive (sostituisce se esiste).

    Args:
        context: espone .config_path: Path
        parent_id: ID cartella cliente su Drive

    Returns:
        ID del file caricato
    """
    config_path: Path = context.config_path
    if not config_path.exists():
        raise ConfigError(f"config.yaml non trovato: {config_path}", file_path=config_path)

    # rimuovi eventuale file esistente con lo stesso nome
    existing = list_drive_files(service, parent_id, query=f"name = '{config_path.name}'")
    for f in existing:
        try:
            delete_drive_file(service, f["id"])
        except Exception as e:
            logger.warning(
                "Impossibile rimuovere config pre-esistente su Drive",
                extra={"error": str(e)},
            )

    media = MediaFileUpload(str(config_path), mimetype="text/yaml", resumable=True)
    metadata = {"name": config_path.name, "parents": [parent_id]}

    def _do():
        return service.files().create(
            body=metadata,
            media_body=media,
            fields="id",
            supportsAllDrives=True,
        ).execute()

    try:
        res = _retry(_do)
        file_id = res.get("id")
        if not file_id:
            raise DriveUploadError("Upload config su Drive fallito: ID mancante")
        return file_id
    except HttpError as e:
        raise DriveUploadError(f"Errore upload config su Drive: {e}") from e


# ---------------------------------------------------------
# Strutture (remoto e locale)
# ---------------------------------------------------------
def _create_remote_tree_from_mapping(service, root_id: str, mapping: Dict[str, Any]) -> Dict[str, str]:
    """
    Crea ricorsivamente la struttura di cartelle su Drive partendo da un mapping dict.

    Returns:
        Dict {nome_cartella: id} per i livelli creati (non tutta la profondità).
    """
    created: Dict[str, str] = {}

    def _walk(parent_id: str, subtree: Dict[str, Any]) -> None:
        for name, children in subtree.items():
            folder_id = create_drive_folder(service, name, parent_id)
            created[name] = folder_id
            if isinstance(children, dict) and children:
                _walk(folder_id, children)

    _walk(root_id, mapping)
    return created


def create_drive_structure_from_yaml(service, yaml_path: Path, client_folder_id: str) -> Dict[str, str]:
    """
    Crea su Drive la gerarchia definita in YAML.

    Supporta:
      - mapping: { RAW: {...}, YAML: {...} }
      - legacy:  { root_folders: [ {name, subfolders: [...]}, ... ] }

    Returns:
        Dict con {nome_cartella: id}; aggiunge alias in uscita:
        se esiste 'raw' → aggiunge chiave 'RAW' con lo stesso ID (e viceversa per 'yaml'/'YAML'),
        SENZA creare doppioni su Drive.
    """
    if not yaml_path.exists():
        raise ConfigError(f"YAML struttura non trovato: {yaml_path}", file_path=yaml_path)

    with open(yaml_path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    mapping = _normalize_yaml_structure(raw)
    created = _create_remote_tree_from_mapping(service, client_folder_id, mapping)

    # Alias SOLO nel risultato (compat CLI/orchestratori)
    if "raw" in created and "RAW" not in created:
        created["RAW"] = created["raw"]
    if "yaml" in created and "YAML" not in created:
        created["YAML"] = created["yaml"]

    return created


def create_local_base_structure(context, yaml_path: Path) -> None:
    """
    Crea la struttura locale convenzionale sotto output/<slug>/.

    Convenzione locale:
        output/<slug>/
          ├─ raw/   ← SOLO le categorie definite in YAML sotto RAW/raw
          ├─ book/
          └─ config/

    Nota: le categorie top-level NON finite sotto RAW/raw nel YAML
          NON vengono replicate in output/<slug>/raw.
    """
    base = getattr(context, "output_dir", None) or getattr(context, "base_dir", None)
    if not base:
        raise ConfigError("Context privo di output/base dir per creare struttura locale.")
    base = Path(base)
    _ensure_dir(base)

    # Cartelle fisse locali
    raw_dir = Path(getattr(context, "raw_dir", base / "raw"))
    book_dir = Path(getattr(context, "md_dir", base / "book"))
    config_dir = Path(getattr(context, "config_dir", base / "config"))
    for d in (raw_dir, book_dir, config_dir):
        _ensure_dir(d)

    if not yaml_path.exists():
        raise ConfigError(f"YAML struttura non trovato: {yaml_path}", file_path=yaml_path)

    with open(yaml_path, "r", encoding="utf-8") as f:
        raw_yaml = yaml.safe_load(f) or {}

    mapping = _normalize_yaml_structure(raw_yaml)

    # Solo le categorie dichiarate sotto RAW/raw
    categories: List[str] = []
    if isinstance(mapping.get("RAW"), dict):
        categories = list(mapping["RAW"].keys())
    elif isinstance(mapping.get("raw"), dict):
        categories = list(mapping["raw"].keys())
    else:
        logger.warning(
            "YAML senza sezione RAW/raw: nessuna categoria creata in output/<slug>/raw",
            extra={"yaml_path": str(yaml_path)},
        )

    for name in categories:
        _ensure_dir(raw_dir / sanitize_filename(name))


# ---------------------------------------------------------
# Download PDF (idempotente)
# ---------------------------------------------------------
def download_drive_pdfs_to_local(
    service,
    remote_root_folder_id: str,
    local_root_dir: Path,
    *,
    progress: bool = True,
) -> Tuple[int, int]:
    """
    Scarica TUTTI i PDF dalle sottocartelle di `remote_root_folder_id` in `local_root_dir`,
    preservando la gerarchia (nome cartella locale = nome cartella remota).

    Idempotenza:
        se il file esiste ed è identico (md5 o size) → skip.

    Returns:
        (downloaded_count, skipped_count)
    """
    local_root_dir = Path(local_root_dir)
    _ensure_dir(local_root_dir)

    subfolders = list_drive_files(service, remote_root_folder_id, query=f"mimeType = '{MIME_FOLDER}'")
    downloaded_count = 0
    skipped_count = 0

    for folder in subfolders:
        folder_id = folder["id"]
        folder_name = folder["name"]
        logger.info(f"📂 Entrando nella cartella: {folder_name}")

        pdfs = list_drive_files(service, folder_id, query=f"mimeType = '{MIME_PDF}'")

        local_subdir = local_root_dir / sanitize_filename(folder_name)
        _ensure_dir(local_subdir)

        for f in pdfs:
            remote_file_id = f["id"]
            remote_name = f.get("name") or "download.pdf"
            safe_name = sanitize_filename(remote_name)
            local_file_path = local_subdir / safe_name

            logger.info(f"📥 Scaricamento PDF: {remote_name} → {local_file_path}")

            # Metadata per idempotenza/integrità
            try:
                meta = _retry(
                    lambda: service.files()
                    .get(
                        fileId=remote_file_id,
                        fields="md5Checksum,size,name",
                        supportsAllDrives=True,
                    )
                    .execute()
                )
            except Exception:
                meta = {}

            _ensure_dir(local_file_path.parent)

            # Idempotenza: md5 o size
            if local_file_path.exists():
                local_md5 = None
                try:
                    local_md5 = _md5sum(local_file_path)
                except Exception:
                    local_md5 = None

                remote_md5 = meta.get("md5Checksum")
                remote_size = int(meta.get("size", -1)) if meta.get("size") else -1
                local_size = local_file_path.stat().st_size

                if (remote_md5 and local_md5 and remote_md5 == local_md5) or (
                    remote_size >= 0 and local_size == remote_size
                ):
                    logger.info(f"⏭️  Invariato, skip download: {local_file_path}")
                    skipped_count += 1
                    continue

            # Download sicuro
            request = service.files().get_media(fileId=remote_file_id, supportsAllDrives=True)
            try:
                with open(local_file_path, "wb") as fh:
                    downloader = MediaIoBaseDownload(fh, request)
                    done = False
                    while not done:
                        status, done = downloader.next_chunk()
                        if progress and status:
                            try:
                                perc = int(status.progress() * 100)
                                logger.info(f"   ↳ Progresso: {perc}%")
                            except Exception:
                                pass
            except HttpError as e:
                raise DriveDownloadError(f"Errore download '{remote_name}': {e}") from e

            # Verifica integrità post-download (se md5 remoto disponibile)
            if meta.get("md5Checksum"):
                try:
                    downloaded_md5 = _md5sum(local_file_path)
                    if downloaded_md5 != meta["md5Checksum"]:
                        logger.warning(
                            f"⚠️  md5 mismatch per {local_file_path}: "
                            f"{downloaded_md5} != {meta['md5Checksum']}"
                        )
                except Exception:
                    pass

            downloaded_count += 1
            logger.info(f"✅ PDF salvato: {local_file_path}")

    logger.info(
        f"📊 Download completato: {downloaded_count} PDF scaricati in {local_root_dir}"
        + (f" (skip: {skipped_count})" if skipped_count else "")
    )
    return downloaded_count, skipped_count
