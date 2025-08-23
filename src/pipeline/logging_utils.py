# src/pipeline/logging_utils.py
"""
Utility per la creazione di logger strutturati per la pipeline Timmy-KB.

Caratteristiche:
- Formattazione uniforme per console e file (opzionalmente con rotazione).
- Campo contestuale `slug` (se disponibile) in ogni record di log.
- Supporto opzionale a `run_id` (correlazione di una singola esecuzione).
- Possibilità di iniettare campi extra di base (`extra_base`) su ogni record.
- Comportamento “safe”: nessun crash se il file di log non è scrivibile
  (degrada a console-only con avviso).
- **Redazione centralizzata**: se `context.redact_logs` è True, applica mascheratura
  ai messaggi/argomenti tramite `env_utils.redact_secrets(...)` e ai campi `extra`
  considerati sensibili (es. token, secret, key, password, service_account, authorization, path).
- **Mascheratura riusabile**: helper pubblici `mask_partial`, `tail_path`,
  `mask_id_map`, `mask_updates` per eliminare duplicazioni negli orchestratori.

Note architetturali:
- Nessun I/O non necessario oltre alla creazione opzionale del file di log.
- Nessuna dipendenza dai moduli di orchestrazione; può essere usato ovunque.
- Design decision: handler sempre “puliti” (reset) per evitare duplicazioni.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional, Union, Protocol, runtime_checkable, Dict, Any
from logging.handlers import RotatingFileHandler

from .env_utils import redact_secrets  # 🔐 mascheratura token/segreti

# --- Nuovi import non vincolanti per metriche (safe fallback) ---
import time
try:
    import psutil  # type: ignore
except Exception:  # pragma: no cover
    psutil = None  # fallback
try:
    import resource  # Unix-only; usato solo se presente
except Exception:  # pragma: no cover
    resource = None  # type: ignore


# Chiavi/substring considerate sensibili negli extra
_SENSITIVE_EXTRA_SUBSTRS = (
    "token",
    "secret",
    "key",
    "password",
    "service_account",
    "authorization",
    "path",
)

# -----------------------------
#  Helpers di mascheratura (NEW)
# -----------------------------
def mask_partial(s: Optional[str]) -> str:
    """
    Maschera parzialmente stringhe sensibili per i log.
    Regola: se <= 7 caratteri → '***', altrimenti primi 3 + '***' + ultimi 3.
    """
    if not s:
        return ""
    s = str(s)
    if len(s) <= 7:
        return "***"
    return f"{s[:3]}***{s[-3:]}"


def tail_path(p: Path, max_len: int = 120) -> str:
    """
    Restituisce solo la coda del path per leggibilità nei log (non segreto).
    """
    s = str(p)
    return s if len(s) <= max_len else s[-max_len:]


def mask_id_map(d: Dict[str, Any]) -> Dict[str, Any]:
    """
    Maschera i valori tipo ID in un mapping (es. mappa cartelle Drive).
    """
    out: Dict[str, Any] = {}
    for k, v in (d or {}).items():
        out[k] = mask_partial(v) if isinstance(v, str) else v
    return out


def mask_updates(d: Dict[str, Any]) -> Dict[str, Any]:
    """
    Maschera campi potenzialmente sensibili in un dizionario di aggiornamenti.
    Regola: se la chiave contiene 'id' o 'drive' (case-insensitive) e il valore è stringa → maschera.
    """
    out: Dict[str, Any] = {}
    for k, v in (d or {}).items():
        if isinstance(v, str) and ("id" in k.lower() or "drive" in k.lower()):
            out[k] = mask_partial(v)
        else:
            out[k] = v
    return out


@runtime_checkable
class SupportsSlug(Protocol):
    """Protocol di typing per oggetti che espongono l'attributo `slug`."""
    slug: str


def _make_context_filter(
    context: Optional[SupportsSlug],
    run_id: Optional[str],
    extra_base: Optional[Dict[str, Any]],
):
    """Crea un filtro che arricchisce ogni record con slug/run_id/extra_base."""
    def _filter(record: logging.LogRecord) -> bool:
        # slug
        if context is not None:
            try:
                setattr(record, "slug", getattr(context, "slug", "n/a"))
            except Exception:
                setattr(record, "slug", "n/a")
        # run_id
        if run_id is not None:
            try:
                setattr(record, "run_id", run_id)
            except Exception:
                pass
        # extra_base
        if extra_base:
            for k, v in extra_base.items():
                # non sovrascrivere se già presente
                if not hasattr(record, k):
                    try:
                        setattr(record, k, v)
                    except Exception:
                        pass
        return True
    return _filter


def _make_redaction_filter(context: Optional[SupportsSlug]):
    """
    Crea un filtro che applica la redazione ai record se `context.redact_logs` è True.

    La redazione viene applicata a:
      - `record.msg` (stringhe o contenenti token sensibili)
      - `record.args` (tuple/list/dict con stringhe potenzialmente sensibili)
      - campi `extra` (solo per chiavi considerate sensibili: token/secret/key/password/service_account/authorization/path)

    Note:
    - Non modifica `exc_info`.
    - Qualsiasi eccezione nel processo di redazione viene silenziata:
      il logging non deve mai andare in errore.
    """
    def _redact_obj(obj):
        try:
            if isinstance(obj, str):
                return redact_secrets(obj)
            if isinstance(obj, tuple):
                return tuple(_redact_obj(x) for x in obj)
            if isinstance(obj, list):
                return [_redact_obj(x) for x in obj]
            if isinstance(obj, dict):
                return {k: _redact_obj(v) for k, v in obj.items()}
            return obj
        except Exception:
            return obj

    def _filter(record: logging.LogRecord) -> bool:
        try:
            redact = bool(getattr(context, "redact_logs", False)) if context is not None else False
            if not redact:
                return True

            # Applica redazione a msg/args
            record.msg = _redact_obj(record.msg)
            record.args = _redact_obj(record.args)

            # NEW: redazione sugli extra sensibili nel record.__dict__
            rec_dict = getattr(record, "__dict__", {})
            for k in list(rec_dict.keys()):
                if k in ("msg", "args"):
                    continue
                k_low = k.lower()
                if any(sub in k_low for sub in _SENSITIVE_EXTRA_SUBSTRS):
                    try:
                        v = rec_dict[k]
                        rec_dict[k] = _redact_obj(v)
                    except Exception:
                        pass

        except Exception:
            # mai bloccare il logging per errori di filtro
            pass
        return True

    return _filter


def get_structured_logger(
    name: str = "default",
    log_file: Optional[Union[str, Path]] = None,
    level: Optional[int] = None,
    rotate: bool = False,
    max_bytes: int = 5 * 1024 * 1024,
    backup_count: int = 3,
    context: Optional[SupportsSlug] = None,
    *,
    run_id: Optional[str] = None,
    extra_base: Optional[Dict[str, Any]] = None,
) -> logging.Logger:
    """
    Crea un logger strutturato con supporto per console e file, opzionalmente
    legato a un contesto che espone `.slug` (es. `ClientContext`).

    Args:
        name: Nome del logger (namespace).
        log_file: Percorso del file di log; se `None` scrive solo su console.
        level: Livello di logging (default: `logging.INFO`).
        rotate: Se `True`, abilita rotazione con `RotatingFileHandler`.
        max_bytes: Dimensione massima del file prima della rotazione.
        backup_count: Numero massimo di file di backup per la rotazione.
        context: Oggetto opzionale con attributo `.slug` da riportare nei record.
        run_id: Identificativo opzionale per correlare i log di una singola esecuzione.
        extra_base: Dizionario di campi extra da iniettare in ogni record.

    Returns:
        logging.Logger: Logger configurato e pronto all'uso.

    Side Effects:
        - Se `log_file` è indicato, crea la cartella padre e il file (se possibile).
        - Reset degli handler esistenti sul logger nominato per coerenza.
        - Non propaga al root logger (evita doppie emissioni).
    """
    logger = logging.getLogger(name)

    # Evita handler duplicati
    if logger.hasHandlers():
        logger.handlers.clear()

    # Livello di default
    if level is None:
        level = logging.INFO
    logger.setLevel(level)

    # Importante: non propagare al root logger
    logger.propagate = False

    # Formatter uniforme; include slug/run_id solo se forniti
    fmt = "%(asctime)s | %(levelname)s | %(name)s"
    if context is not None:
        fmt += " | slug=%(slug)s"
    if run_id is not None:
        fmt += " | run_id=%(run_id)s"
    fmt += " | %(message)s"

    formatter = logging.Formatter(fmt, datefmt="%Y-%m-%d %H:%M:%S")

    # Filtri: contesto + redazione
    ctx_filter = _make_context_filter(context, run_id, extra_base)
    redact_filter = _make_redaction_filter(context)

    # Handler console
    ch = logging.StreamHandler()
    ch.setFormatter(formatter)
    ch.addFilter(ctx_filter)
    ch.addFilter(redact_filter)
    logger.addHandler(ch)

    # Handler file, se richiesto
    if log_file:
        log_file_path = Path(log_file)
        log_file_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            if rotate:
                fh = RotatingFileHandler(
                    log_file_path,
                    maxBytes=max_bytes,
                    backupCount=backup_count,
                    encoding="utf-8",
                )
            else:
                fh = logging.FileHandler(log_file_path, encoding="utf-8")
            fh.setFormatter(formatter)
            fh.addFilter(ctx_filter)
            fh.addFilter(redact_filter)
            logger.addHandler(fh)
        except Exception as e:
            # Se il file non è creabile, degrada a console-only
            try:
                logger.warning(
                    f"Impossibile creare file di log {log_file_path}: {e}. "
                    "Logging solo su console."
                )
            except Exception:
                pass

    return logger


# -------------------------------
#  Helpers metriche (non invasivi)
# -------------------------------

def _get_rss_mb() -> Optional[float]:
    """Ritorna la memoria RSS in MB se disponibile, altrimenti None (fallback safe)."""
    try:
        if psutil is not None:
            p = psutil.Process()  # processo corrente
            return float(p.memory_info().rss) / (1024 * 1024)
    except Exception:
        pass
    try:
        if resource is not None:
            # ru_maxrss: kilobytes su Linux, bytes su macOS; normalizziamo a MB
            usage = resource.getrusage(resource.RUSAGE_SELF)
            ru = float(getattr(usage, "ru_maxrss", 0.0))
            # Heuristica piattaforma: se troppo grande assumiamo bytes→MB, altrimenti KB→MB
            return (ru / (1024 * 1024)) if ru > 10**9 else (ru / 1024.0)
    except Exception:
        pass
    return None


class metrics_scope:
    """
    Context manager per registrare metriche di performance a fine blocco senza
    modificare il formato dei log.

    Uso:
        with metrics_scope(logger, stage="build_md", category="contratti"):
            ... # codice da misurare

    Effetto:
        - misura elapsed_ms
        - prova a misurare rss_mb (se possibile, con fallback safe)
        - emette un log INFO alla chiusura con extra standardizzati (stage, elapsed_ms, rss_mb, **kv)
    """
    def __init__(self, logger: logging.Logger, *, stage: str, level: int = logging.INFO, **kv: Any) -> None:
        self._logger = logger
        self._stage = stage
        self._kv = kv
        self._level = level
        self._t0 = 0.0

    def __enter__(self):
        self._t0 = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc, tb):
        elapsed_ms = int((time.perf_counter() - self._t0) * 1000)
        rss_mb = _get_rss_mb()
        extra = {"stage": self._stage, "elapsed_ms": elapsed_ms}
        if rss_mb is not None:
            extra["rss_mb"] = round(rss_mb, 2)
        # merge dei kv custom, senza sovrascrivere quelli già presenti
        for k, v in self._kv.items():
            if k not in extra:
                extra[k] = v
        try:
            self._logger.log(self._level, f"metrics: {self._stage}", extra=extra)
        except Exception:
            # i log non devono mai rompere il flusso
            pass
        # Non sopprime eventuali eccezioni nel blocco
        return False


def log_with_metrics(logger: logging.Logger, level: int, msg: str, **kv: Any) -> None:
    """
    Utility one-shot per loggare un messaggio aggiungendo campi extra standardizzati.
    Non altera il formatter né la pipeline di redazione.
    """
    try:
        logger.log(level, msg, extra=kv or None)
    except Exception:
        pass


__all__ = [
    "get_structured_logger",
    "SupportsSlug",
    "metrics_scope",
    "log_with_metrics",
    # helpers di mascheratura riusabili
    "mask_partial",
    "tail_path",
    "mask_id_map",
    "mask_updates",
]
