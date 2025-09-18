from __future__ import annotations

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# SPDX-License-Identifier: GPL-3.0-or-later
# src/pipeline/drive/client.py
"""
Client e primitive di lettura per Google Drive (v3).

Superficie pubblica (usata tramite il facade `pipeline.drive_utils`):
- get_drive_service(context)
    Costruisce un client Drive v3 autenticato con Service Account (scope: Drive).
    Applica il logging strutturato con slug/run_id e redazione delegata ai filtri globali.
- list_drive_files(service, parent_id, query=None, *, fields=..., page_size=1000)
    Elenca in modo paginato i file/cartelle sotto una directory, includendo Shared Drives.
    Usa retry con backoff esponenziale + jitter su errori transienti (5xx/429/network).
- get_file_metadata(service, file_id, *, fields=...)
    Restituisce metadati essenziali (id, name, mimeType, size, md5Checksum).
- drive_metrics_scope()
    Context manager che attiva la raccolta di metriche per i retry (_DriveRetryMetrics).
    Utile per misurare retries, backoff cumulato e ultimo status/error.
- get_retry_metrics()
    Ritorna uno snapshot dict delle metriche correnti (vuoto se non attive).

Note d’uso:
- Nessun `print()`; tutta la diagnostica passa dal logging strutturato del repo.
- La policy di retry/metriche è centralizzata qui ed è riutilizzata anche da upload/download via `_retry(...)`.
"""

import os
import random
import time
from collections import defaultdict
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Generator, List, Optional, cast


from ..env_utils import get_env_var  # ✅ centralizzazione ENV
from ..exceptions import ConfigError
from ..logging_utils import get_structured_logger

# Logger a livello di modulo per aderire alle convenzioni di logging strutturato del repo.
logger = get_structured_logger("pipeline.drive.client")


# ------------------------------- Metriche & Retry ---------------------------------


@dataclass
class _DriveRetryMetrics:
    """Metriche interne per i retry Drive (aggregate sul blocco corrente).

    Campi:
      - retries_total: numero totale di retry effettuati (esclusi i tentativi iniziali riusciti).
      - retries_by_error: mappa {NomeEccezione: conteggio}.
      - backoff_total_ms: somma delle attese (sleep) in millisecondi effettuate tra i tentativi.
      - last_error: stringa breve con l’ultimo errore osservato.
      - last_status: ultimo HTTP status osservato (se disponibile).
    """

    retries_total: int = 0
    retries_by_error: Dict[str, int] = field(
        default_factory=lambda: cast(Dict[str, int], defaultdict(int))
    )
    backoff_total_ms: int = 0
    last_error: Optional[str] = None
    last_status: Optional[int | str] = None

    def as_dict(self) -> Dict[str, Any]:
        return {
            "retries_total": self.retries_total,
            "retries_by_error": dict(self.retries_by_error),
            "backoff_total_ms": self.backoff_total_ms,
            "last_error": self.last_error,
            "last_status": self.last_status,
        }


# ContextVar che ospita le metriche correnti (thread-safe).
_METRICS_CTX: ContextVar[Optional[_DriveRetryMetrics]] = ContextVar(
    "drive_metrics_ctx", default=None
)


@contextmanager
def drive_metrics_scope() -> Generator[_DriveRetryMetrics, None, None]:
    """
    Context manager per attivare la raccolta metriche dei retry Drive in un blocco.

    Esempio:
        with drive_metrics_scope():
            ... chiamate che usano _retry(...) ...
        snapshot = get_retry_metrics()
    """
    metrics = _DriveRetryMetrics()
    token = _METRICS_CTX.set(metrics)
    try:
        yield metrics
    finally:
        _METRICS_CTX.reset(token)


def get_retry_metrics() -> Dict[str, Any]:
    """Ritorna uno snapshot (dict) delle metriche correnti. Se non attive, dict vuoto."""
    m = _METRICS_CTX.get()
    return m.as_dict() if m is not None else {}


class _RetryBudgetExceeded(RuntimeError):
    """Interno: sollevato quando si supera il budget massimo di attesa cumulata."""


def _is_retryable_error(err: Exception) -> bool:
    """
    Valuta se un'eccezione è transiente e merita un nuovo tentativo.

    Criteri:
    - HttpError 5xx e 429 (Too Many Requests) → retry.
    - Messaggi comuni di rete (timeout, reset, unavailable, quota, ecc.) → retry.
    """
    if isinstance(err, HttpError):
        try:
            status = int(err.resp.status)
        except Exception:
            status = None
        return status in {429, 500, 502, 503, 504}

    msg = str(err).lower()
    transient_snippets = (
        "timed out",
        "timeout",
        "temporarily unavailable",
        "connection reset",
        "connection aborted",
        "reset by peer",
        "server busy",
        "rate limit",
        "too many requests",
        "unavailable",
        "quota exceeded",
    )
    return any(s in msg for s in transient_snippets)


def _retry(
    op: Callable[[], Any],
    *,
    is_retryable: Optional[Callable[[Exception], bool]] = None,
    max_attempts: int = 6,
    base_delay_s: float = 0.5,
    max_total_sleep_s: float = 20.0,
    op_name: str = "drive-op",
) -> Any:
    """
    Esegue `op()` con backoff esponenziale + jitter, rispettando un budget massimo.

    Comportamento:
    - Ritenta eccezioni transienti (HttpError 5xx/429 e errori di rete comuni).
    - Jitter “full”: attesa uniforme in [0, base * 2**(tentativo-1)].
    - Se i tentativi si esauriscono o l’errore non è retryable → rilancia l’eccezione.
    - Se il sonno cumulato supera `max_total_sleep_s` → interrompe con `_RetryBudgetExceeded`.

    Parametri:
    - is_retryable: classificatore alternativo; se None usa `_is_retryable_error`.
    - max_attempts: numero massimo di tentativi (incluso il primo).
    - base_delay_s: base del backoff esponenziale.
    - max_total_sleep_s: tetto massimo al sonno cumulato (budget).
    - op_name: nome logico dell’operazione per i log.
    """
    attempts = 0
    total_sleep = 0.0
    while True:
        try:
            attempts += 1
            return op()
        except Exception as e:  # noqa: BLE001
            retryable = _is_retryable_error(e) if is_retryable is None else bool(is_retryable(e))
            if not retryable or attempts >= max_attempts:
                logger.debug(
                    "drive.retry.giveup",
                    extra={
                        "op": op_name,
                        "attempts": attempts,
                        "retryable": retryable,
                        "exc_type": type(e).__name__,
                        "message": str(e)[:300],
                    },
                )
                raise

            # Aggiornamento metriche (se attive)
            m = _METRICS_CTX.get()
            if m is not None:
                m.retries_total += 1
                m.retries_by_error[type(e).__name__] += 1
                m.last_error = str(e)[:300]
                # Proviamo a leggere lo status HTTP se c'è
                try:
                    resp = getattr(e, "resp", None)
                    if resp is None:
                        raise AttributeError("missing resp")
                    status_val = getattr(resp, "status", None)
                    if status_val is None:
                        raise AttributeError("missing status")
                    m.last_status = int(status_val)
                except Exception:
                    m.last_status = getattr(e, "status", None)

            # Calcolo del backoff con jitter completo e rispetto del budget
            backoff = base_delay_s * (2 ** (attempts - 1))
            sleep_s = random.uniform(0, backoff)
            if total_sleep + sleep_s > max_total_sleep_s:
                sleep_s = max(0.0, max_total_sleep_s - total_sleep)
                if sleep_s == 0.0:
                    logger.debug(
                        "drive.retry.budget_exceeded",
                        extra={
                            "op": op_name,
                            "attempts": attempts,
                            "total_sleep_s": round(total_sleep, 3),
                            "budget_s": max_total_sleep_s,
                        },
                    )
                    raise _RetryBudgetExceeded(f"Budget di retry esaurito per {op_name}") from e

            logger.debug(
                "drive.retry.backoff",
                extra={
                    "op": op_name,
                    "attempt": attempts,
                    "sleep_s": round(sleep_s, 3),
                    "total_sleep_s": round(total_sleep, 3),
                },
            )
            time.sleep(sleep_s)
            total_sleep += sleep_s

            # Aggiorna accumulo metriche (se attive)
            m = _METRICS_CTX.get()
            if m is not None:
                m.backoff_total_ms += int(round(sleep_s * 1000))


# ------------------------------- Costruzione client --------------------------------


def _resolve_service_account_file(context: Any) -> str:
    """
    Risolve il percorso assoluto del file JSON del service account.

    Ordine di ricerca:
      1) `context.service_account_file`
      2) `context.SERVICE_ACCOUNT_FILE`
      3) `context.env['SERVICE_ACCOUNT_FILE']`
      4) env `SERVICE_ACCOUNT_FILE` via `get_env_var`

    Solleva:
      ConfigError se non trovato o non leggibile.
    """
    candidates: List[Optional[str]] = []
    # Attributi sul contesto (via proprietà o campi)
    for attr in ("service_account_file", "SERVICE_ACCOUNT_FILE"):
        if hasattr(context, attr):
            candidates.append(getattr(context, attr))
    # Mappa env nel contesto (se esiste)
    if hasattr(context, "env") and isinstance(getattr(context, "env"), dict):
        sa: Optional[str] = cast(Optional[str], context.env.get("SERVICE_ACCOUNT_FILE"))
        candidates.append(sa)
    # Variabile d'ambiente letta tramite resolver centralizzato
    candidates.append(get_env_var("SERVICE_ACCOUNT_FILE", default=None, required=False))

    for cand in candidates:
        if not cand:
            continue
        path = os.path.abspath(os.path.expanduser(str(cand)))
        if os.path.isfile(path):
            return path

    raise ConfigError(
        "SERVICE_ACCOUNT_FILE mancante o non valido. Fornire un path leggibile tramite "
        "context.service_account_file o variabile d'ambiente SERVICE_ACCOUNT_FILE."
    )


def get_drive_service(context: Any) -> Any:
    """
    Costruisce e restituisce un client Google Drive v3 usando un service account.

    Args:
        context: oggetto tipo ClientContext. Deve fornire info sul file di credenziali.

    Returns:
        googleapiclient.discovery.Resource per Drive v3.

    Raises:
        ConfigError: se il file credenziali manca o non è leggibile,
                     o se la creazione del client fallisce.
    """
    # Logger contestualizzato: eredita slug/run_id e filtri di redazione
    local_logger = get_structured_logger("pipeline.drive.client", context=context)

    sa_path = _resolve_service_account_file(context)
    try:
        creds = Credentials.from_service_account_file(
            sa_path,
            scopes=["https://www.googleapis.com/auth/drive"],
        )
    except Exception as e:  # noqa: BLE001
        raise ConfigError(f"Caricamento credenziali service account fallito: {e}") from e

    try:
        service = build("drive", "v3", credentials=creds, cache_discovery=False)
    except Exception as e:  # noqa: BLE001
        raise ConfigError(f"Creazione client Google Drive fallita: {e}") from e

    # NB: non logghiamo il path completo delle credenziali (solo basename)
    local_logger.debug(
        "drive.client.built",
        extra={"sa_file": Path(sa_path).name, "scopes": "drive", "impersonation": False},
    )
    return service


# ------------------------------- Primitive di lettura ------------------------------


def list_drive_files(
    service: Any,
    parent_id: str,
    query: Optional[str] = None,
    *,
    fields: str = "nextPageToken, files(id, name, mimeType, size, md5Checksum)",
    page_size: int = 1000,
) -> Generator[Dict[str, Any], None, None]:
    """
    Elenca file/cartelle sotto una cartella Drive (gestisce Shared Drives, paging, retry).

    Args:
        service: client Drive v3.
        parent_id: ID della cartella da elencare.
        query: filtro addizionale da AND-are con "parents in <parent_id>".
        fields: campi richiesti (minimi per performance).
        page_size: dimensione pagina (max raccomandato 1000).

    Yields:
        dict con almeno id, name, mimeType (ed md5Checksum/size quando disponibili).
    """
    if not parent_id:
        raise ValueError("parent_id è obbligatorio")

    base_q = f"'{parent_id}' in parents and trashed = false"
    q = f"({base_q}) and ({query})" if query else base_q

    page_token: Optional[str] = None
    op_name = "files.list"

    while True:

        def _call() -> Any:
            req = service.files().list(
                q=q,
                fields=fields,
                spaces="drive",
                pageSize=page_size,
                pageToken=page_token,
                includeItemsFromAllDrives=True,
                supportsAllDrives=True,
            )
            return req.execute()

        resp = _retry(_call, op_name=op_name)
        for f in resp.get("files", []):
            yield f

        page_token = resp.get("nextPageToken")
        if not page_token:
            break


def get_file_metadata(
    service: Any,
    file_id: str,
    *,
    fields: str = "id, name, mimeType, size, md5Checksum",
) -> Dict[str, Any]:
    """
    Recupera metadati minimi per un file su Drive.

    Args:
        service: client Drive v3.
        file_id: ID del file.
        fields: campi richiesti.

    Returns:
        dict con i campi specificati.

    Raises:
        ValueError: se `file_id` è vuoto.
    """
    if not file_id:
        raise ValueError("file_id è obbligatorio")

    def _call() -> Any:
        return service.files().get(fileId=file_id, fields=fields, supportsAllDrives=True).execute()

    return cast(Dict[str, Any], _retry(_call, op_name="files.get"))


# ------------------------------- Esportazioni modulo -------------------------------

__all__ = [
    "get_drive_service",
    "list_drive_files",
    "get_file_metadata",
    "_retry",  # riuso intra-pacchetto (download/upload)
    "drive_metrics_scope",  # attiva/gestisce metriche nel blocco corrente
    "get_retry_metrics",  # snapshot metriche correnti (dict)
]
