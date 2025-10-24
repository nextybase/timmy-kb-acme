# SPDX-License-Identifier: GPL-3.0-or-later
# src/pipeline/logging_utils.py
"""Logging strutturato per Timmy-KB.

Obiettivi:
- Logger **idempotente**, con filtri di **contesto** (slug, run_id) e **redazione**
  I filtri sono attivabili da `context.redact_logs`.
- Niente `print`: tutti i moduli usano logging strutturato (console + opzionale file).
- Utility di **masking** coerenti per ID, percorsi e aggiornamenti di config.

Formato di output (console/file):
    %(asctime)s %(levelname)s %(name)s: %(message)s |
    slug=<slug> run_id=<run> file_path=<p> [event=<evt> branch=<b> repo=<r>]

Indice funzioni principali (ruolo):
- `get_structured_logger(name, *, context=None, log_file=None, run_id=None, level=INFO)`:
    istanzia un logger con handler console (sempre) e file (opzionale),
    aggiunge i filtri di contesto e redazione.
- `metrics_scope(logger, *, stage, customer=None)`:
    context manager leggero che logga start/end/fail di una microfase.
- `redact_secrets(msg)`:
    redige pattern comuni di segreti in testo libero.
- `mask_partial(value, keep=3)`, `mask_id_map(d)`, `mask_updates(d)`:
    utility per mascherare valori da includere in `extra`.
- `tail_path(p, keep_segments=2)`:
    coda compatta di un path per log.

Linee guida implementative:
- **Redazione centralizzata**: se `context.redact_logs` e' True, il filtro applica la redazione
  ai messaggi e a campi extra sensibili (`GITHUB_TOKEN`, `SERVICE_ACCOUNT_FILE`, ecc.).
- **Idempotenza**: chiamate ripetute a `get_structured_logger` non creano handler duplicati.
"""

from __future__ import annotations

import logging
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType
from typing import Any, Literal, Mapping, Optional, Type, Union

# ---------------------------------------------
# Redazione (API semplice usata dai moduli)
# ---------------------------------------------
_SENSITIVE_KEYS = {"GITHUB_TOKEN", "SERVICE_ACCOUNT_FILE", "Authorization", "GIT_HTTP_EXTRAHEADER"}


def redact_secrets(msg: str) -> str:
    """Redige token/credenziali se accidentalmente presenti in un testo libero."""
    if not msg:
        return msg
    out = msg
    # Mascherature semplici; per casi complessi si demanda ai moduli chiamanti
    replacements = (
        (re.compile(r"x-access-token\s*:\s*\S+", re.IGNORECASE), "x-access-token:***"),
        (re.compile(r"Authorization\s*:\s*Basic\s+\S+", re.IGNORECASE), "Authorization: Basic ***"),
        (re.compile(r"Authorization\s*:\s*Bearer\s+\S+", re.IGNORECASE), "Authorization: Bearer ***"),
    )
    for pattern, replacement in replacements:
        out = pattern.sub(replacement, out)
    return out


def mask_partial(value: Optional[str], keep: int = 3) -> str:
    """Maschera parzialmente un identificativo: 'abcdef' -> 'abc...'."""
    if not value:
        return ""
    return value[:keep] + "..." if len(value) > keep else value


def tail_path(p: Union[Path, str], keep_segments: int = 2) -> str:
    """Restituisce la coda del path per logging compatto (accetta `Path` o `str`)."""
    parts = list(Path(p).parts)
    return "/".join(parts[-keep_segments:]) if parts else str(p)


def mask_id_map(d: Mapping[str, Any]) -> Mapping[str, Any]:
    """Maschera i valori (ID) di un mapping, lasciando le chiavi in chiaro."""
    return {k: mask_partial(str(v)) for k, v in (d or {}).items()}


def mask_updates(d: Mapping[str, Any]) -> Mapping[str, Any]:
    """Maschera in modo prudente alcuni campi noti durante il log degli update di config."""
    out: dict[str, Any] = {}
    for k, v in (d or {}).items():
        ku = k.upper()
        if ku.endswith("_ID") or ku in _SENSITIVE_KEYS or "TOKEN" in ku:
            out[k] = mask_partial(str(v))
        else:
            out[k] = v
    return out


# ---------------------------------------------
# Structured logging
# ---------------------------------------------
@dataclass
class _CtxView:
    slug: Optional[str] = None
    run_id: Optional[str] = None
    redact_logs: bool = False


def _ctx_view_from(context: Any = None, run_id: Optional[str] = None) -> _CtxView:
    """Estrae una vista minima del contesto per i filtri di logging."""
    cv = _CtxView()
    if context is not None:
        cv.slug = getattr(context, "slug", None)
        cv.redact_logs = bool(getattr(context, "redact_logs", False))
        # se il contesto espone un run_id, usalo; altrimenti quello passato a get_structured_logger
        cv.run_id = getattr(context, "run_id", None) or run_id
    else:
        cv.run_id = run_id
    return cv


class _ContextFilter(logging.Filter):
    """Arricchisce ogni record con campi standardizzati."""

    def __init__(self, ctx: _CtxView):
        super().__init__()
        self.ctx = ctx

    def filter(self, record: logging.LogRecord) -> bool:
        # campi extra "globali"
        if not hasattr(record, "slug"):
            record.slug = self.ctx.slug or "-"
        if not hasattr(record, "run_id"):
            record.run_id = self.ctx.run_id or "-"
        # normalizza campi facoltativi per evitare KeyError nei formatter
        if not hasattr(record, "file_path"):
            record.file_path = getattr(record, "pathname", None)
        return True


class _RedactFilter(logging.Filter):
    """Applica redazione ai messaggi quando attiva."""

    def __init__(self, enabled: bool):
        super().__init__()
        self.enabled = enabled

    def filter(self, record: logging.LogRecord) -> bool:
        if not self.enabled:
            return True
        try:
            # redigi message
            if isinstance(record.msg, str):
                record.msg = redact_secrets(record.msg)
            # redigi campi extra comuni
            for field in (
                "GITHUB_TOKEN",
                "SERVICE_ACCOUNT_FILE",
                "Authorization",
                "GIT_HTTP_EXTRAHEADER",
            ):
                if hasattr(record, field):
                    setattr(record, field, "***")
        except Exception:
            # mai bloccare il logging per un errore di redazione
            pass
        return True


class _KVFormatter(logging.Formatter):
    """Formatter semplice e leggibile, con campi chiave-valore stabili."""

    def format(self, record: logging.LogRecord) -> str:
        base = super().format(record)
        kv = []
        # includi subset di extra utili se presenti
        for k in (
            "slug",
            "run_id",
            "file_path",
            "event",
            "branch",
            "repo",
            "phase",
            "duration_ms",
            "artifact_count",
        ):
            v = getattr(record, k, None)
            if v:
                kv.append(f"{k}={v}")
        if kv:
            return f"{base} | " + " ".join(kv)
        return base


def _make_console_handler(level: int, fmt: str) -> logging.Handler:
    ch = logging.StreamHandler(stream=sys.stdout)
    ch.setLevel(level)
    ch.setFormatter(_KVFormatter(fmt))
    return ch


def _make_file_handler(path: Path, level: int, fmt: str) -> logging.Handler:
    fh = logging.FileHandler(path, encoding="utf-8")
    fh.setLevel(level)
    fh.setFormatter(_KVFormatter(fmt))
    return fh


def _ensure_no_duplicate_handlers(lg: logging.Logger, key: str) -> None:
    """Evita handler duplicati (idempotenza)."""
    to_remove = []
    for h in lg.handlers:
        if getattr(h, "_logging_utils_key", None) == key:
            to_remove.append(h)
    for h in to_remove:
        lg.removeHandler(h)


def _set_logger_filter(lg: logging.Logger, flt: logging.Filter, key: str) -> None:
    """Sostituisce (se presente) un filtro identificato dal key e lo rimpiazza."""
    to_remove = [f for f in lg.filters if getattr(f, "_logging_utils_key", None) == key]
    for f in to_remove:
        lg.removeFilter(f)
    flt._logging_utils_key = key  # type: ignore[attr-defined]
    lg.addFilter(flt)


def get_structured_logger(
    name: str,
    *,
    context: Any = None,
    log_file: Optional[Path] = None,
    run_id: Optional[str] = None,
    level: int = logging.INFO,
    propagate: Optional[bool] = None,
) -> logging.Logger:
    """Restituisce un logger configurato e idempotente.

    Parametri:
        name:     nome del logger (es. 'pre_onboarding').
        context:  oggetto con attributi opzionali `.slug`, `.redact_logs`, `.run_id`.
        log_file: path file log; se presente, aggiunge file handler (dir gia' creata a monte).
        run_id:   identificativo run usato se `context.run_id` assente.
        level:    livello logging (default: INFO).

    Comportamento:
      - `propagation=False`, handler console sempre presente,
      - file handler opzionale se `log_file` e' fornito (si assume path gia' validato/creato),
      - filtri: contesto + redazione (se `context.redact_logs` True),
      - formatter coerente console/file.

    Nota:
      - Questo modulo **non** crea directory: farlo a monte con path-safety e mkdir.
      - Per mascherare valori in `extra`, usare `mask_partial`/`mask_id_map`/`mask_updates`.

    Ritorna:
        logging.Logger pronto all'uso.
    """
    lg = logging.getLogger(name)
    lg.setLevel(level)
    if propagate is None:
        env_override = os.getenv("TIMMY_LOG_PROPAGATE", "").lower()
        if env_override:
            propagate = env_override in {"1", "true", "yes", "on"}
        else:
            propagate = True
    lg.propagate = propagate

    ctx = _ctx_view_from(context, run_id)

    # formatter base
    fmt = "%(asctime)s %(levelname)s %(name)s: %(message)s"

    # filtri
    ctx_filter = _ContextFilter(ctx)
    redact_filter = _RedactFilter(ctx.redact_logs)
    _set_logger_filter(lg, ctx_filter, f"{name}::ctx_filter")
    _set_logger_filter(lg, redact_filter, f"{name}::redact_filter")

    # console handler (idempotente per chiave)
    key_console = f"{name}::console"
    _ensure_no_duplicate_handlers(lg, key_console)
    ch = _make_console_handler(level, fmt)
    ch._logging_utils_key = key_console  # type: ignore[attr-defined]
    ch.addFilter(ctx_filter)
    ch.addFilter(redact_filter)
    lg.addHandler(ch)

    # file handler opzionale
    if log_file:
        key_file = f"{name}::file::{str(log_file)}"
        _ensure_no_duplicate_handlers(lg, key_file)
        fh = _make_file_handler(log_file, level, fmt)
        fh._logging_utils_key = key_file  # type: ignore[attr-defined]
        fh.addFilter(ctx_filter)
        fh.addFilter(redact_filter)
        lg.addHandler(fh)

    return lg


# ---------------------------------------------
# Metriche leggere (helper opzionale)
# ---------------------------------------------
class phase_scope:
    """Context manager per telemetria di fase con campi strutturati.

    Eventi emessi:
      - event=phase_started | phase_completed | phase_failed
      - Campi: phase, slug, run_id (dal filtro di contesto), duration_ms (se disponibile), artifact_count (opz.).
    """

    def __init__(self, logger: logging.Logger, *, stage: str, customer: Optional[str] = None):
        self.logger = logger
        self.stage = stage
        self.customer = customer
        self._t0: Optional[float] = None
        self._artifact_count: Optional[int] = None

    def set_artifacts(self, count: Optional[int]) -> None:
        if count is None:
            self._artifact_count = None
            return
        try:
            self._artifact_count = int(count)
        except Exception:
            self._artifact_count = None

    def __enter__(self) -> "phase_scope":
        try:
            from time import monotonic as _monotonic

            self._t0 = _monotonic()
        except Exception:
            self._t0 = None
        self.logger.info(
            "phase_started",
            extra={
                "event": "phase_started",
                "phase": self.stage,
                "slug": self.customer,
                "status": "start",
            },
        )
        return self

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc: Optional[BaseException],
        tb: Optional[TracebackType],
    ) -> Literal[False]:
        duration_ms: Optional[int] = None
        if self._t0 is not None:
            try:
                from time import monotonic as _monotonic

                duration_ms = int(round((_monotonic() - self._t0) * 1000))
            except Exception:
                duration_ms = None

        extra: dict[str, Any] = {"phase": self.stage, "slug": self.customer}
        if duration_ms is not None:
            extra["duration_ms"] = duration_ms
        if self._artifact_count is not None:
            extra["artifact_count"] = self._artifact_count
            # Alias strutturato stabile
            extra["artifacts"] = self._artifact_count

        if exc:
            # In caso di errore, aggiungi campo strutturato 'error' e 'status=failed'
            extra["error"] = str(exc)
            extra["status"] = "failed"
            self.logger.error("phase_failed", extra={"event": "phase_failed", **extra})
        else:
            # Successo: 'status=success'
            extra["status"] = "success"
            self.logger.info("phase_completed", extra={"event": "phase_completed", **extra})
        return False


class metrics_scope:
    """Context manager leggero per misurare micro-fasi e loggare in modo uniforme.

    Esempio:
        with metrics_scope(logger, stage="drive_upload", customer=context.slug):
            upload_config_to_drive_folder(...)

    Log prodotti:
        INFO -> start:<stage> | slug=<customer>
        INFO -> end:<stage>   | slug=<customer>
        ERROR -> fail:<stage>: <exc> | slug=<customer>
    """

    def __init__(self, logger: logging.Logger, *, stage: str, customer: Optional[str] = None):
        self.logger = logger
        self.stage = stage
        self.customer = customer

    def __enter__(self) -> "metrics_scope":
        self.logger.info(f"[start] {self.stage}", extra={"slug": self.customer})
        return self

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc: Optional[BaseException],
        tb: Optional[TracebackType],
    ) -> Literal[False]:
        if exc:
            self.logger.error(f"[fail] {self.stage}: {exc}", extra={"slug": self.customer})
        else:
            self.logger.info(f"[end] {self.stage}", extra={"slug": self.customer})
        # non sopprimere eccezioni
        return False


__all__ = [
    "get_structured_logger",
    "phase_scope",
    "metrics_scope",
    "redact_secrets",
    "mask_partial",
    "tail_path",
    "mask_id_map",
    "mask_updates",
]
