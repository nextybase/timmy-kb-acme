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
    alias di `phase_scope` per retro-compatibilità (stessa telemetria strutturata).
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
from logging.handlers import RotatingFileHandler
from pathlib import Path
from types import TracebackType
from typing import TYPE_CHECKING, Any, Literal, Mapping, Optional, Type, Union

# --- OpenTelemetry (opzionale) -------------------------------------------------
_OTEL_ENABLED = False
_OTEL_TRACER = None
try:
    from opentelemetry import trace as _otel_trace
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    _OTEL_IMPORT_OK = True
except Exception:
    _OTEL_IMPORT_OK = False

# ---------------------------------------------
# Redazione (API semplice usata dai moduli)
# ---------------------------------------------
_SENSITIVE_KEYS = {"GITHUB_TOKEN", "SERVICE_ACCOUNT_FILE", "Authorization", "GIT_HTTP_EXTRAHEADER"}

if TYPE_CHECKING:
    from pipeline.observability_config import ObservabilitySettings

_OBS_SETTINGS: "ObservabilitySettings | None" = None


def _get_observability_settings() -> ObservabilitySettings:
    """Carica e cache le preferenze globali di osservabilita'."""
    global _OBS_SETTINGS
    if _OBS_SETTINGS is None:
        try:
            from pipeline.observability_config import load_observability_settings

            _OBS_SETTINGS = load_observability_settings()
        except Exception:

            class _FallbackSettings:
                stack_enabled = False
                tracing_enabled = False
                redact_logs = True
                log_level = "INFO"

            _OBS_SETTINGS = _FallbackSettings()  # type: ignore[assignment]
    return _OBS_SETTINGS


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


class _EventDefaultFilter(logging.Filter):
    """Garantisce che 'event' sia sempre presente; se manca usa il messaggio come codice evento."""

    def filter(self, record: logging.LogRecord) -> bool:  # pragma: no cover
        try:
            if not hasattr(record, "event"):
                msg = record.getMessage() if hasattr(record, "getMessage") else getattr(record, "msg", "")
                if isinstance(msg, str):
                    record.event = msg.strip() or "log"
                else:
                    record.event = "log"
        except Exception:
            # mai bloccare il logging
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
        if _OTEL_ENABLED:
            try:
                span = _otel_trace.get_current_span()
                ctx = span.get_span_context()
                if ctx is not None and ctx.is_valid:
                    kv.append(f"trace_id={ctx.trace_id:032x}")
                    kv.append(f"span_id={ctx.span_id:016x}")
            except Exception:
                pass
        if kv:
            return f"{base} | " + " ".join(kv)
        return base


def _make_console_handler(level: int, fmt: str) -> logging.Handler:
    ch = logging.StreamHandler(stream=sys.stdout)
    ch.setLevel(level)
    ch.setFormatter(_KVFormatter(fmt))
    return ch


def _make_file_handler(
    path: Path, level: int, fmt: str, *, max_bytes: int | None = None, backup_count: int | None = None
) -> logging.Handler:
    max_b = max(1024 * 128, int(max_bytes or 0)) if (max_bytes or 0) > 0 else 1024 * 1024
    bk_cnt = int(backup_count or 3)
    fh = RotatingFileHandler(path, encoding="utf-8", maxBytes=max_b, backupCount=bk_cnt)
    fh.setLevel(level)
    fh.setFormatter(_KVFormatter(fmt))
    return fh


def _coerce_positive_int(value: Any, *, default: int, minimum: int) -> int:
    """Converte value in int positivo, oppure ritorna default."""
    if value is None:
        return default
    try:
        candidate = int(value)
    except Exception:
        return default
    if candidate < minimum:
        return default
    return candidate


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
    level: int | str | None = None,
    redact_logs: Optional[bool] = None,
    enable_tracing: Optional[bool] = None,
    propagate: Optional[bool] = None,
) -> logging.Logger:
    """Restituisce un logger configurato e idempotente.

    Parametri:
        name:     nome del logger (es. 'pre_onboarding').
        context:  oggetto con attributi opzionali `.slug`, `.redact_logs`, `.run_id`.
        log_file: path file log; se presente, aggiunge file handler (dir gia' creata a monte).
        run_id:   identificativo run usato se `context.run_id` assente.
        level:    livello logging (default: dalle preferenze osservabilita', fallback INFO).
        redact_logs: abilita/disabilita redazione (default: preferenze o context.redact_logs).
        enable_tracing: abilita OTEL (default: preferenze globali).

    Comportamento:
      - `propagation=False`, handler console sempre presente,
      - file handler opzionale se `log_file` e' fornito (si assume path gia' validato/creato),
      - filtri: contesto + redazione (se attiva),
      - formatter coerente console/file.

    Nota:
      - Questo modulo **non** crea directory: farlo a monte con path-safety e mkdir.
      - Per mascherare valori in `extra`, usare `mask_partial`/`mask_id_map`/`mask_updates`.

    Ritorna:
        logging.Logger pronto all'uso.
    """
    settings = _get_observability_settings()

    # 1) Livello
    if level is None:
        level_name = (settings.log_level or "INFO").upper()
        level = getattr(logging, level_name, logging.INFO)
    elif isinstance(level, str):
        level = getattr(logging, level.upper(), logging.INFO)

    # 2) Redazione
    if redact_logs is None:
        ctx_redact = bool(getattr(context, "redact_logs", False)) if context is not None else False
        redact_logs = ctx_redact if ctx_redact is not None else settings.redact_logs

    # 3) Tracing OTEL
    if enable_tracing is None:
        enable_tracing = settings.tracing_enabled

    lg = logging.getLogger(name)
    lg.setLevel(level)
    if propagate is None:
        env_override = ""
        try:  # lazy import per evitare cicli durante bootstrap
            from pipeline.env_utils import get_env_var as _get_env_var
        except Exception:
            _get_env_var = None
        if _get_env_var is not None:
            try:
                env_override = (_get_env_var("TIMMY_LOG_PROPAGATE", default="") or "").lower()
            except Exception:
                env_override = ""
        else:
            env_override = os.getenv("TIMMY_LOG_PROPAGATE", "").lower()
        if env_override:
            propagate = env_override in {"1", "true", "yes", "on"}
        else:
            propagate = False
    # Nei test pytest intercettiamo i log via caplog (attaccato al root). Se la propagazione
    # resta disabilitata i test non vedono i messaggi. Optiamo quindi per riabilitarla in
    # questo scenario, lasciando invariato il comportamento runtime.
    if not propagate and (os.getenv("PYTEST_CURRENT_TEST") or "pytest" in sys.modules):
        propagate = True
    lg.propagate = propagate

    ctx = _ctx_view_from(context, run_id)
    try:
        ctx.redact_logs = bool(redact_logs)
    except Exception:
        ctx.redact_logs = False

    # formatter base
    fmt = "%(asctime)s %(levelname)s %(name)s: %(message)s"

    # filtri
    ctx_filter = _ContextFilter(ctx)
    redact_filter = _RedactFilter(bool(redact_logs))
    event_filter = _EventDefaultFilter()
    _set_logger_filter(lg, ctx_filter, f"{name}::ctx_filter")
    _set_logger_filter(lg, redact_filter, f"{name}::redact_filter")
    _set_logger_filter(lg, event_filter, f"{name}::event_filter")

    # esponi il contesto sul logger per i consumer (es. phase_scope)
    try:
        setattr(lg, "_logging_ctx_view", ctx)
    except Exception:
        pass

    # console handler (idempotente per chiave)
    key_console = f"{name}::console"
    _ensure_no_duplicate_handlers(lg, key_console)
    ch = _make_console_handler(level, fmt)
    ch._logging_utils_key = key_console  # type: ignore[attr-defined]
    ch.addFilter(ctx_filter)
    ch.addFilter(redact_filter)
    ch.addFilter(event_filter)
    lg.addHandler(ch)

    # file handler opzionale
    if log_file:
        settings = getattr(context, "settings", None) if context is not None else None
        max_b_setting: Any = None
        bk_cnt_setting: Any = None
        if settings is not None:
            getter = getattr(settings, "get", None)
            if callable(getter):
                try:
                    max_b_setting = getter("log_max_bytes", None)
                    bk_cnt_setting = getter("log_backup_count", None)
                except Exception:
                    max_b_setting = None
                    bk_cnt_setting = None
            elif isinstance(settings, Mapping):
                max_b_setting = settings.get("log_max_bytes")
                bk_cnt_setting = settings.get("log_backup_count")
        env_max = os.getenv("TIMMY_LOG_MAX_BYTES")
        if env_max:
            try:
                max_b_setting = int(env_max)
            except Exception:
                max_b_setting = max_b_setting or None
        env_bk = os.getenv("TIMMY_LOG_BACKUP_COUNT")
        if env_bk:
            try:
                bk_cnt_setting = int(env_bk)
            except Exception:
                bk_cnt_setting = bk_cnt_setting or None
        max_b = _coerce_positive_int(max_b_setting, default=1024 * 1024, minimum=1024 * 128)
        bk_cnt = _coerce_positive_int(bk_cnt_setting, default=3, minimum=1)
        key_file = f"{name}::file::{str(log_file)}"
        _ensure_no_duplicate_handlers(lg, key_file)
        fh = _make_file_handler(log_file, level, fmt, max_bytes=max_b, backup_count=bk_cnt)
        fh._logging_utils_key = key_file  # type: ignore[attr-defined]
        fh.addFilter(ctx_filter)
        fh.addFilter(redact_filter)
        fh.addFilter(event_filter)
        lg.addHandler(fh)

    _maybe_setup_tracing(context=context, enable_tracing=bool(enable_tracing))
    return lg


def _maybe_setup_tracing(*, context: Optional[Mapping[str, Any]] = None, enable_tracing: bool = True) -> None:
    global _OTEL_ENABLED, _OTEL_TRACER
    if not enable_tracing:
        return
    if _OTEL_ENABLED or not _OTEL_IMPORT_OK:
        return
    endpoint = os.getenv("TIMMY_OTEL_ENDPOINT")
    if not endpoint:
        return
    service = os.getenv("TIMMY_SERVICE_NAME", "timmy-kb")
    env = os.getenv("TIMMY_ENV", "dev")
    slug = None
    if context:
        try:
            slug = getattr(context, "slug", None) or (context or {}).get("slug")
        except Exception:
            slug = None
    resource = Resource.create({"service.name": service, "deployment.environment": env, "customer.slug": slug or ""})
    provider = TracerProvider(resource=resource)
    processor = BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint))
    provider.add_span_processor(processor)
    _otel_trace.set_tracer_provider(provider)
    _OTEL_TRACER = _otel_trace.get_tracer(__name__)
    _OTEL_ENABLED = True


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
        ctx_view = getattr(logger, "_logging_ctx_view", None)
        inferred_slug = None
        inferred_run = None
        if ctx_view is not None:
            inferred_slug = getattr(ctx_view, "slug", None)
            inferred_run = getattr(ctx_view, "run_id", None)
        self.customer = customer or inferred_slug
        self._run_id = inferred_run
        self._t0: Optional[float] = None
        self._artifact_count: Optional[int] = None
        self._span: Any | None = None

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
        try:
            if _OTEL_ENABLED and _OTEL_TRACER:
                self._span = _OTEL_TRACER.start_as_current_span(f"phase:{self.stage}")
                self._span.__enter__()
        except Exception:
            self._span = None
        extra = self._base_extra()
        extra.update({"event": "phase_started", "status": "start"})
        self.logger.info("phase_started", extra=extra)
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

        extra: dict[str, Any] = self._base_extra()
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
            try:
                if self._span is not None:
                    self._span.record_exception(exc)
            except Exception:
                pass
            if self._span is not None:
                try:
                    self._span.__exit__(exc_type, exc, tb)
                except Exception:
                    pass
            return False
        # Successo: 'status=success'
        extra["status"] = "success"
        self.logger.info("phase_completed", extra={"event": "phase_completed", **extra})
        if self._span is not None:
            try:
                self._span.__exit__(None, None, None)
            except Exception:
                pass
        return False

    def _base_extra(self) -> dict[str, Any]:
        return {
            "phase": self.stage,
            "slug": self.customer or "-",
            "run_id": self._run_id or "-",
        }


def metrics_scope(logger: logging.Logger, *, stage: str, customer: Optional[str] = None) -> phase_scope:
    """
    Alias di phase_scope mantenuto per retro-compatibilità.

    In precedenza metrics_scope emetteva log ad-hoc ([start], [end], [fail]).
    Ora convoglia tutto su phase_scope, offrendo un'unica semantica strutturata:
    eventi phase_started/phase_completed/phase_failed, status, duration_ms,
    artifact_count.
    """

    return phase_scope(logger, stage=stage, customer=customer)


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
