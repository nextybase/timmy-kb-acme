# src/pipeline/drive_utils.py
"""
Utility Google Drive per la pipeline Timmy-KB.

Funzioni principali:
- Inizializzazione client (Service Account).
- Creazione / elenco / cancellazione cartelle e file (compatibile con Shared Drives).
- Creazione struttura remota da YAML (supporto mapping moderno e legacy `root_folders`).
- Creazione struttura locale convenzionale (raw/book/config) con categorie SOLO da RAW/raw.
- Upload di `config.yaml`.
- Download PDF idempotente con verifica md5/size e file handle sicuri.
  ➕ (Agg.) Download RICORSIVO: visita BFS di sottocartelle, preservando la gerarchia locale.

Requisiti: variabili d'ambiente/contesto per `SERVICE_ACCOUNT_FILE`.

Note:
- Le funzioni qui NON terminano il processo; eventuali errori sono propagati come eccezioni tipizzate.
- Logging strutturato tramite logger di modulo (nessun segreto in chiaro).
"""
from __future__ import annotations

import hashlib
import time
import random
from dataclasses import dataclass, field
from collections import defaultdict
from contextlib import contextmanager
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
from pipeline.env_utils import redact_secrets  # 🔐 redazione opzionale nei log

logger = get_structured_logger("pipeline.drive_utils")

# ---------------------------------------------------------
# Costanti / Scope
# ---------------------------------------------------------
DRIVE_SCOPES = ["https://www.googleapis.com/auth/drive"]
MIME_FOLDER = "application/vnd.google-apps.folder"
MIME_PDF = "application/pdf"

# ---------------------------------------------------------
# Metriche retry (osservabilità non invasiva)
# ---------------------------------------------------------
@dataclass
class _DriveRetryMetrics:
    """Contatori lightweight per osservabilità dei retry/backoff Drive."""
    retries_total: int = 0
    retries_by_error: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    last_error: Optional[str] = None
    last_status: Optional[Any] = None
    backoff_total_ms: int = 0

    def as_dict(self) -> Dict[str, Any]:
        return {
            "retries_total": self.retries_total,
            "retries_by_error": dict(self.retries_by_error),
            "last_error": self.last_error,
            "last_status": self.last_status,
            "backoff_total_ms": self.backoff_total_ms,
        }

# Contesto metrico corrente (per thread singolo/processo pipeline)
_METRICS_CTX: Optional[_DriveRetryMetrics] = None

@contextmanager
def _metrics_scope(metrics: _DriveRetryMetrics):
    """Imposta metriche correnti per includere anche retry interni (list/create/etc.)."""
    global _METRICS_CTX
    prev = _METRICS_CTX
    _METRICS_CTX = metrics
    try:
        yield
    finally:
        _METRICS_CTX = prev


# ---------------------------------------------------------
# Helpers locali
# ---------------------------------------------------------
def _md5sum(path: Path, chunk_size: int = 1024 * 1024) -> str:
    """Calcola l’MD5 del file in streaming (robusto su file grandi).

    Args:
        path: Percorso del file locale.
        chunk_size: Dimensione dei chunk di lettura.

    Returns:
        Stringa esadecimale MD5 del file.
    """
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            h.update(chunk)
    return h.hexdigest()


def _maybe_redact(text: str, redact: bool) -> str:
    """Applica redazione solo se richiesto."""
    return redact_secrets(text) if (redact and text) else text


def _retry(
    fn: Callable[[], Any],
    *,
    tries: int = 3,
    delay: float = 0.8,
    backoff: float = 1.6,
    max_total_delay: Optional[float] = 60.0,  # ⬅️ NOVITÀ: tetto massimo ai sleep cumulati (secondi)
    redact_logs: bool = False,  # 👈 opzionale: redazione nei log dei retry
) -> Any:
    """Retry esponenziale per chiamate Drive (HttpError) con jitter per evitare retry sincronizzati.

    Args:
        fn: Funzione senza argomenti da eseguire con retry.
        tries: Numero massimo di tentativi.
        delay: Ritardo iniziale tra i tentativi (secondi).
        backoff: Fattore di moltiplicazione del ritardo a ogni retry.
        max_total_delay: Se impostato, limite superiore (in secondi) del tempo di attesa cumulato
                         tra i tentativi. Al superamento, interrompe con eccezione.
        redact_logs: Se True, maschera eventuali segreti nei messaggi di log.

    Returns:
        Il valore ritornato da `fn` in caso di successo.

    Raises:
        HttpError: se tutti i tentativi falliscono.
        TimeoutError: se il budget `max_total_delay` viene superato prima di esaurire i tentativi.
    """
    _delay = delay
    elapsed = 0.0
    for attempt in range(1, tries + 1):
        try:
            return fn()
        except HttpError as e:
            # Ultimo tentativo: propaga
            if attempt >= tries:
                raise
            # Telemetria (se attiva)
            status = getattr(getattr(e, "resp", None), "status", "?")
            if _METRICS_CTX is not None:
                _METRICS_CTX.retries_total += 1
                _METRICS_CTX.retries_by_error[type(e).__name__] += 1
                _METRICS_CTX.last_error = str(e)
                _METRICS_CTX.last_status = status

            logger.warning(
                _maybe_redact(f"HTTP {status} su Drive; retry {attempt}/{tries}", redact_logs),
                extra={"error": _maybe_redact(str(e), redact_logs)},
            )
            # jitter: +/- 30% del delay corrente
            jitter_factor = 1.0 + random.uniform(-0.3, 0.3)
            sleep_s = max(0.0, _delay * jitter_factor)

            # 🔒 Limite di budget sugli sleep cumulati
            if max_total_delay is not None and (elapsed + sleep_s) > max_total_delay:
                logger.warning(
                    _maybe_redact(
                        f"⏱️ Limite retry superato: sleep cumulato {elapsed:.1f}s + next {sleep_s:.1f}s > {max_total_delay:.1f}s",
                        redact_logs,
                    ),
                    extra={"retries_so_far": attempt - 1, "max_total_delay": max_total_delay},
                )
                # Interrompe subito: nessun ulteriore sleep
                raise TimeoutError(f"Drive retry budget exceeded ({elapsed:.1f}s >= {max_total_delay:.1f}s)")

            # Aggiorna metriche e dormi
            if _METRICS_CTX is not None:
                _METRICS_CTX.backoff_total_ms += int(round(sleep_s * 1000))
            time.sleep(sleep_s)
            elapsed += sleep_s
            _delay *= backoff


def _ensure_dir(path: Path) -> None:
    """Crea la directory (e genitori) se non esiste (idempotente)."""
    path.mkdir(parents=True, exist_ok=True)


def _normalize_yaml_structure(data: Any) -> Dict[str, Any]:
    """Normalizza la struttura YAML della gerarchia remota.

    Accetta:
      1) Mapping moderno: `{ RAW: {categoria: {}}, YAML: {} }`
      2) Legacy: `{ root_folders: [ {name: "raw", subfolders: [...]}, ... ] }`

    Returns:
        Un dizionario annidato `{nome: {sotto: {...}}}`.

    Note:
        Qui NON aggiungiamo alias `RAW`/`YAML` per evitare doppioni su Drive.
        Gli alias sono aggiunti solo nel valore di ritorno di
        `create_drive_structure_from_yaml`.
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
    """Inizializza il client Google Drive (v3).

    Args:
        context_or_sa_file: Oggetto con `.env['SERVICE_ACCOUNT_FILE']` oppure
            percorso (Path/str) al JSON del Service Account.
        drive_id: Non utilizzato qui; mantenuto per compat futura.

    Returns:
        Oggetto service Drive v3 (googleapiclient.discovery.Resource).

    Raises:
        ConfigError: se il file delle credenziali non è configurato o non esiste.
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
def create_drive_folder(service, name: str, parent_id: Optional[str] = None, *, redact_logs: bool = False) -> str:
    """Crea una cartella su Drive e ritorna l'ID (compatibile con Shared Drives).

    Idempotenza:
        se sotto `parent_id` esiste già una cartella con lo stesso `name`,
        riusa quell'ID invece di crearne una nuova.

    Args:
        service: Client Drive v3.
        name: Nome cartella.
        parent_id: ID della cartella padre (opzionale).
        redact_logs: Se True, applica redazione ai log di warning/error.

    Returns:
        ID della cartella creata o esistente.

    Raises:
        DriveUploadError: se la creazione fallisce per cause di permessi/parent errato.
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
                    logger.info(
                        _maybe_redact(
                            f"↺ Riutilizzo cartella esistente '{name}' ({folder_id}) sotto parent {parent_id}",
                            redact_logs,
                        )
                    )
                    return folder_id
        except Exception as e:
            logger.warning(
                _maybe_redact(f"Lookup cartella '{name}' fallito, procedo con creazione: {e}", redact_logs)
            )

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
        res = _retry(_do, redact_logs=redact_logs)
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
    """Elenca file sotto una cartella Drive.

    Args:
        service: Client Drive v3.
        parent_id: ID della cartella padre.
        query: Filtro addizionale (es. `"mimeType='application/pdf'"`).

    Returns:
        Lista di dict con campi: `id`, `name`, `mimeType`, `md5Checksum`, `size`.
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

        resp = _retry(_do)  # nessun contenuto sensibile previsto: redazione non necessaria
        files = resp.get("files", [])
        results.extend(files)
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    return results


def delete_drive_file(service, file_id: str) -> None:
    """Cancella un file su Drive per ID (compat Shared Drives)."""
    def _do():
        return service.files().delete(fileId=file_id, supportsAllDrives=True).execute()

    _retry(_do)


def upload_config_to_drive_folder(service, context, parent_id: str, *, redact_logs: bool = False) -> str:
    """Carica la config del cliente su Drive (sostituisce se esiste).

    Args:
        service: Client Drive v3.
        context: Oggetto che espone `config_path: Path`.
        parent_id: ID della cartella cliente su Drive.
        redact_logs: Se True, applica redazione ai log di warning/error.

    Returns:
        L'ID del file caricato su Drive.

    Raises:
        ConfigError: se `config.yaml` è assente localmente.
        DriveUploadError: in caso di errori durante l'upload.
    """
    config_path: Path = context.config_path
    if not config_path.exists():
        raise ConfigError(f"config.yaml non trovato: {config_path}", file_path=config_path)

    metrics = _DriveRetryMetrics()
    with _metrics_scope(metrics):
        # rimuovi eventuale file esistente con lo stesso nome
        existing = list_drive_files(service, parent_id, query=f"name = '{config_path.name}'")
        for f in existing:
            try:
                delete_drive_file(service, f["id"])
            except Exception as e:
                logger.warning(
                    _maybe_redact("Impossibile rimuovere config pre-esistente su Drive", redact_logs),
                    extra={"error": _maybe_redact(str(e), redact_logs), "slug": getattr(context, "slug", None)},
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
            res = _retry(_do, redact_logs=redact_logs)
            file_id = res.get("id")
            if not file_id:
                raise DriveUploadError("Upload config su Drive fallito: ID mancante")
            return file_id
        except HttpError as e:
            # Eccezione immutata (no redazione qui): diagnosi piena a carico chiamante
            raise DriveUploadError(f"Errore upload config su Drive: {e}") from e
        finally:
            # Log strutturato riepilogativo metriche
            logger.info(
                "metrics.drive.summary (upload_config)",
                extra={
                    "metrics.drive.retries_total": metrics.retries_total,
                    "metrics.drive.retries_by_error": dict(metrics.retries_by_error),
                    "metrics.drive.backoff_total_ms": metrics.backoff_total_ms,
                    "slug": getattr(context, "slug", None),
                },
            )
            # Snapshot leggero su contesto (se disponibile)
            try:
                if hasattr(context, "set_step_status"):
                    context.set_step_status("drive_retries", str(metrics.retries_total))
            except Exception:
                # best-effort, nessuna propagazione
                pass


# ---------------------------------------------------------
# Strutture (remoto e locale)
# ---------------------------------------------------------
def _create_remote_tree_from_mapping(
    service,
    root_id: str,
    mapping: Dict[str, Any],
    *,
    redact_logs: bool = False,  # 👈 NOVITÀ: propagazione redazione
) -> Dict[str, str]:
    """Crea ricorsivamente la struttura di cartelle su Drive partendo da un mapping dict.

    Args:
        service: Client Drive v3.
        root_id: ID della cartella radice (cliente).
        mapping: Dizionario `{nome: sottostruttura}`.
        redact_logs: Se True, applica redazione ai log durante la creazione cartelle.

    Returns:
        Dizionario `{nome_cartella: id}` per i livelli creati (non tutta la profondità).
    """
    created: Dict[str, str] = {}

    def _walk(parent_id: str, subtree: Dict[str, Any]) -> None:
        for name, children in subtree.items():
            folder_id = create_drive_folder(service, name, parent_id, redact_logs=redact_logs)
            created[name] = folder_id
            if isinstance(children, dict) and children:
                _walk(folder_id, children)

    _walk(root_id, mapping)
    return created


def create_drive_structure_from_yaml(
    service,
    yaml_path: Path,
    client_folder_id: str,
    *,
    redact_logs: bool = False,  # 👈 NOVITÀ: parametro opt-in
) -> Dict[str, str]:
    """Crea su Drive la gerarchia definita in YAML.

    Supporta:
      - mapping: `{ RAW: {...}, YAML: {...} }`
      - legacy:  `{ root_folders: [ {name, subfolders: [...]}, ... ] }`

    Args:
        service: Client Drive v3.
        yaml_path: Percorso del file YAML con la struttura.
        client_folder_id: ID della cartella radice del cliente su Drive.
        redact_logs: Se True, applica redazione ai log durante la creazione cartelle.

    Returns:
        Dizionario con `{nome_cartella: id}`; aggiunge alias in uscita:
        se esiste 'raw' → aggiunge chiave 'RAW' con lo stesso ID (e viceversa per 'yaml'/'YAML'),
        **senza** creare doppioni su Drive.

    Raises:
        ConfigError: se `yaml_path` non esiste o YAML non valido/supportato.
    """
    if not yaml_path.exists():
        raise ConfigError(f"YAML struttura non trovato: {yaml_path}", file_path=yaml_path)

    with open(yaml_path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    mapping = _normalize_yaml_structure(raw)
    created = _create_remote_tree_from_mapping(service, client_folder_id, mapping, redact_logs=redact_logs)

    # Alias SOLO nel risultato (compat CLI/orchestratori)
    if "raw" in created and "RAW" not in created:
        created["RAW"] = created["raw"]
    if "yaml" in created and "YAML" not in created:
        created["YAML"] = created["yaml"]

    return created


def create_local_base_structure(context, yaml_path: Path) -> None:
    """Crea la struttura locale convenzionale sotto `output/<slug>/`.

    Convenzione locale:
        output/<slug>/
          ├─ raw/   ← SOLO le categorie definite in YAML sotto RAW/raw
          ├─ book/
          └─ config/

    Nota:
        Le categorie top-level NON finite sotto RAW/raw nel YAML
        non vengono replicate in `output/<slug>/raw`.

    Args:
        context: Contesto con `output_dir`/`base_dir` e path canonici.
        yaml_path: YAML che definisce la struttura remota (per derivare le categorie RAW/raw).

    Raises:
        ConfigError: se il contesto non ha base/output dir o se lo YAML è assente.
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
            extra={"yaml_path": str(yaml_path), "slug": getattr(context, "slug", None)},
        )

    for name in categories:
        _ensure_dir(raw_dir / sanitize_filename(name))


# ---------------------------------------------------------
# Download PDF (idempotente, ora RICORSIVO)
# ---------------------------------------------------------
def download_drive_pdfs_to_local(
    service,
    remote_root_folder_id: str,
    local_root_dir: Path,
    *,
    progress: bool = True,
    context: Any = None,
    redact_logs: bool = False,  # 👈 opzionale: redazione nei log
) -> Tuple[int, int]:
    """Scarica TUTTI i PDF dalle sottocartelle di `remote_root_folder_id` in `local_root_dir`.

    La gerarchia locale replica quella remota: ogni sottocartella remota → sottocartella locale.

    Idempotenza:
        Se il file esiste ed è identico (md5 o size) → skip.

    Args:
        service: Client Drive v3.
        remote_root_folder_id: ID della cartella remota contenente le categorie.
        local_root_dir: Radice locale in cui salvare i PDF.
        progress: Se `True`, logga avanzamento dei chunk durante il download.
        context: (opz.) `ClientContext` per snapshot metriche in `step_status`.
        redact_logs: Se True, applica redazione ai log di warning/error.

    Returns:
        `tuple(downloaded_count, skipped_count)`.

    Raises:
        DriveDownloadError: in caso di errori di download dal servizio Drive.
    """
    local_root_dir = Path(local_root_dir)
    _ensure_dir(local_root_dir)

    metrics = _DriveRetryMetrics()
    downloaded_count = 0
    skipped_count = 0

    with _metrics_scope(metrics):
        # Seed: sottocartelle immediate della radice remota
        top_subfolders = list_drive_files(service, remote_root_folder_id, query=f"mimeType = '{MIME_FOLDER}'")
        queue: List[Tuple[str, List[str]]] = []
        for folder in top_subfolders:
            queue.append((folder["id"], [sanitize_filename(folder["name"])]))

        while queue:
            current_id, rel_parts = queue.pop(0)
            rel_path = Path(*rel_parts)
            local_subdir = local_root_dir / rel_path
            _ensure_dir(local_subdir)

            logger.info(f"📂 Cartella: {rel_path.as_posix()}")

            # PDF nel livello corrente
            pdfs = list_drive_files(service, current_id, query=f"mimeType = '{MIME_PDF}'")
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
                        .execute(),
                        redact_logs=redact_logs,
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

                # Download sicuro (streaming a chunk)
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
                    # annota errore su metriche (best-effort)
                    if _METRICS_CTX is not None:
                        _METRICS_CTX.last_error = str(e)
                        _METRICS_CTX.last_status = getattr(getattr(e, "resp", None), "status", "?")
                    # Eccezione immutata (no redazione qui): diagnosi piena a carico chiamante
                    raise DriveDownloadError(f"Errore download '{remote_name}': {e}") from e

                # Verifica integrità post-download (se md5 remoto disponibile)
                if meta.get("md5Checksum"):
                    try:
                        downloaded_md5 = _md5sum(local_file_path)
                        if downloaded_md5 != meta["md5Checksum"]:
                            logger.warning(
                                _maybe_redact(
                                    f"⚠️  md5 mismatch per {local_file_path}: "
                                    f"{downloaded_md5} != {meta['md5Checksum']}",
                                    redact_logs,
                                )
                            )
                    except Exception:
                        pass

                downloaded_count += 1
                logger.info(f"✅ PDF salvato: {local_file_path}")

            # Sottocartelle (ricorsione BFS)
            child_folders = list_drive_files(service, current_id, query=f"mimeType = '{MIME_FOLDER}'")
            for cf in child_folders:
                queue.append((cf["id"], rel_parts + [sanitize_filename(cf["name"])]))

    # Riepilogo download
    logger.info(
        f"📊 Download completato: {downloaded_count} PDF scaricati in {local_root_dir}"
        + (f" (skip: {skipped_count})" if skipped_count else "")
    )
    # Snapshot metriche Drive
    logger.info(
        "metrics.drive.summary (download)",
        extra={
            "metrics.drive.retries_total": metrics.retries_total,
            "metrics.drive.retries_by_error": dict(metrics.retries_by_error),
            "metrics.drive.backoff_total_ms": metrics.backoff_total_ms,
            "metrics.drive.downloaded": downloaded_count,
            "metrics.drive.skipped": skipped_count,
        },
    )
    # Propaga nel contesto (se disponibile)
    try:
        if context is not None and hasattr(context, "set_step_status"):
            context.set_step_status("drive_retries", str(metrics.retries_total))
    except Exception:
        # best-effort
        pass

    return downloaded_count, skipped_count
