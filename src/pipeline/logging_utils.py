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
- **Redazione centralizzata**: decisione basata su compute_redact_flag(env, level) e
  applicazione in un filtro che maschera msg/args/extra sensibili.
- **Mascheratura riusabile**: helper pubblici `mask_partial`, `tail_path`,
  `mask_id_map`, `mask_updates`, `redact_secrets`.

Note architetturali:
- Nessun I/O non necessario oltre alla creazione opzionale del file di log.
- Nessuna dipendenza dagli orchestratori; può essere usato ovunque.
- Handler sempre “puliti” (reset) per evitare duplicazioni.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional, Union, Protocol, runtime_checkable, Dict, Any, Iterable
from logging.handlers import RotatingFileHandler

from .env_utils import compute_redact_flag  # SSoT del flag

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

# Variabili d'ambiente i cui valori, se presenti, vanno mascherati nel testo
_SECRET_ENV_KEYS: tuple[str, ...] = (
    "GITHUB_TOKEN",
    "GH_TOKEN",
    "PAT",
    "OPENAI_API_KEY",
    "AWS_SECRET_ACCESS_KEY",
    "SERVICE_ACCOUNT_FILE",
)


# -----------------------------
#  Helpers di mascheratura
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
    """Ritorna solo la coda del path per leggibilità nei log (non segreto)."""
    s = str(p)
    return s if len(s) <= max_len else s[-max_len:]


def mask_id_map(d: Dict[str, Any]) -> Dict[str, Any]:
    """Maschera i valori tipo ID in un mapping (es. mappa cartelle Drive)."""
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


def redact_secrets(text: str, extra_keys: Iterable[str] | None = None) -> str:
    """
    Maschera nei testi eventuali valori di segreti presenti nell'ambiente.
    Sostituisce i match esatti con '****'. Accetta chiavi extra opzionali.
    """
    if not text:
        return text
    redacted = str(text)
    keys = list(_SECRET_ENV_KEYS) + list(extra_keys or [])
    for k in keys:
        v = os.getenv(k)
        if v:
            try:
                redacted = redacted.replace(v, "****")
            except Exception:
                pass
    return redacted


@runtime_checkable
class SupportsSlug(Protocol):
    """Protocol di typing per oggetti che espongono l'attributo `slug` e opzionalmente `env`, `redact_logs`."""
    slug: str  # obbligatorio
    # opzionali:
    # env: dict
    # redact_logs: bool


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
                if not hasattr(record, k):
                    try:
                        setattr(record, k, v)
                    except Exception:
                        pass
        return True
    return _filter


def _make_redaction_filter(context: Optional[SupportsSlug], level: int):
    """
    Crea un filtro che applica la redazione ai record (se attiva).
    La decisione usa, in quest’ordine:
      1) context.redact_logs (se presente),
      2) compute_redact_flag(context.env, level), altrimenti OFF.
    """
    # Calcolo del flag (una volta alla creazione del logger)
    redact_flag = False
    try:
        if context is not None and hasattr(context, "redact_logs"):
            redact_flag = bool(getattr(context, "redact_logs"))
        elif context is not None and hasattr(context, "env") and isinstance(getattr(context, "env"), dict):
            redact_flag = bool(compute_redact_flag(getattr(context, "env"), logging.getLevelName(level)))
        else:
            redact_flag = False
    except Exception:
        redact_flag = False

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
        if not redact_flag:
            return True
        try:
            # msg/args
            record.msg = _redact_obj(record.msg)
            record.args = _redact_obj(record.args)

            # extra sensibili
            rec_dict = getattr(record, "__dict__", {})
            for k in list(rec_dict.keys()):
                if k in ("msg", "args"):
                    continue
                k_low = k.lower()
                if any(sub in k_low for sub in _SENSITIVE_EXTRA_SUBSTRS):
                    try:
                        rec_dict[k] = _redact_obj(rec_dict[k])
                    except Exception:
                        pass
        except Exception:
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
    Crea un logger strutturato (console + opzionale file) con redazione centralizzata.

    Side effects:
    - Reset handler esistenti sul logger con lo stesso nome.
    - Non propaga al root logger.
    """
    logger = logging.getLogger(name)

    if logger.hasHandlers():
        logger.handlers.clear()

    if level is None:
        level = logging.INFO
    logger.setLevel(level)
    logger.propagate = False

    fmt = "%(asctime)s | %(levelname)s | %(name)s"
    if context is not None:
        fmt += " | slug=%(slug)s"
    if run_id is not None:
        fmt += " | run_id=%(run_id)s"
    fmt += " | %(message)s"

    formatter = logging.Formatter(fmt, datefmt="%Y-%m-%d %H:%M:%S")

    ctx_filter = _make_context_filter(context, run_id, extra_base)
    redact_filter = _make_redaction_filter(context, level)

    # Console
    ch = logging.StreamHandler()
    ch.setFormatter(formatter)
    ch.addFilter(ctx_filter)
    ch.addFilter(redact_filter)
    logger.addHandler(ch)

    # File (opzionale)
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
            try:
                logger.warning(
                    f"Impossibile creare file di log {log_file_path}: {e}. Logging solo su console."
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
            usage = resource.getrusage(resource.RUSAGE_SELF)
            ru = float(getattr(usage, "ru_maxrss", 0.0))
            return (ru / (1024 * 1024)) if ru > 10**9 else (ru / 1024.0)
    except Exception:
        pass
    return None


class metrics_scope:
    """
    Context manager per registrare metriche di performance a fine blocco.

    with metrics_scope(logger, stage="build_md", category="contratti"):
        ...
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
        for k, v in self._kv.items():
            if k not in extra:
                extra[k] = v
        try:
            self._logger.log(self._level, f"metrics: {self._stage}", extra=extra)
        except Exception:
            pass
        return False


def log_with_metrics(logger: logging.Logger, level: int, msg: str, **kv: Any) -> None:
    """Logga un messaggio aggiungendo campi extra standardizzati (best-effort)."""
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
    "redact_secrets",
]
