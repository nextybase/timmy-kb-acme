# SPDX-License-Identifier: GPL-3.0-or-later
# src/pipeline/logging_utils.py
"""Logging strutturato per Timmy-KB.

Obiettivi:
- Logger **idempotente**, con filtri di **contesto** (slug, run_id) e **redazione**
  I filtri sono attivabili da `context.redact_logs`.
- Niente `print`: tutti i moduli usano logging strutturato (console + opzionale file).
- Utility di **masking** coerenti per ID, percorsi e aggiornamenti di config.
- Le preferenze applicative (livello, redazione, tracing) provengono da
  `pipeline.observability_config`, mentre gli ENV regolano soli aspetti
  infrastrutturali (rotazione file, propagate, endpoint OTEL).

Formato di output (console/file):
    %(asctime)s %(levelname)s %(name)s: %(message)s |
    slug=<slug> run_id=<run> file_path=<p> [event=<evt> branch=<b> repo=<r>]

Indice funzioni principali (ruolo):
- `get_structured_logger(name, *, context=None, log_file=None, run_id=None, level=INFO)`:
    istanzia un logger con handler console (sempre) e file (opzionale),
    aggiunge i filtri di contesto e redazione.
- `redact_secrets(msg)`:
    redige pattern comuni di segreti in testo libero.
- `mask_partial(value, keep=3)`, `mask_id_map(d)`, `mask_updates(d)`:
    utility per mascherare valori da includere in `extra`.
- `tail_path(p, keep_segments=2)`:
    coda compatta di un path per log.

Linee guida implementative:
- **Redazione centralizzata**: se `context.redact_logs` e' True, il filtro applica la redazione
  ai messaggi e a campi extra sensibili (`SERVICE_ACCOUNT_FILE`, ecc.).
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
from typing import Any, ContextManager, Literal, Mapping, Optional, Type, Union

from pipeline.metrics import observe_phase_duration, record_phase_failed
from pipeline.tracing import ensure_tracer, infer_trace_kind, start_phase_span

try:
    from opentelemetry import trace as _otel_trace
except Exception:
    _otel_trace = None

_SENSITIVE_KEYS = {"SERVICE_ACCOUNT_FILE", "Authorization", "GIT_HTTP_EXTRAHEADER"}
GATE_EVENT_NAMES = {
    "evidence_gate_blocked",
    "skeptic_gate_blocked",
    "skeptic_gate_pass_with_conditions",
    "qa_gate_failed",
    "qa_gate_retry",
}
BRIDGE_FIELDS_ALWAYS = {"run_id", "slug", "phase_id", "state_id", "intent_id", "action_id"}
BRIDGE_FIELDS_OTEL = {"trace_id", "span_id"}
_STREAMLIT_NOISE_SUPPRESSED = False


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
            redact_keys = {
                "SERVICE_ACCOUNT_FILE",
                "Authorization",
                "GIT_HTTP_EXTRAHEADER",
            }
            sensitive_substrings = ("token", "secret", "authorization", "password", "key", "service_account")
            for field, _value in list(record.__dict__.items()):
                if field in redact_keys or any(sub in field.lower() for sub in sensitive_substrings):
                    try:
                        setattr(record, field, "***")
                    except Exception:
                        pass
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
        if _otel_trace is not None:
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


class _SafeStreamHandler(logging.StreamHandler):
    """StreamHandler con flush best-effort per evitare crash su stdout Windows."""

    def flush(self) -> None:
        try:
            super().flush()
        except (OSError, ValueError):
            return


def _make_console_handler(level: int, fmt: str) -> logging.Handler:
    ch = _SafeStreamHandler(stream=sys.stdout)
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


class _PhaseInjectFilter(logging.Filter):
    """Inietta il campo 'phase' sui record se mancante (utile dentro phase_scope)."""

    def __init__(self, phase: str):
        super().__init__()
        self.phase = phase

    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "phase"):
            try:
                record.phase = self.phase
            except Exception:
                pass
        return True


def _is_streamlit_process() -> bool:
    for arg in sys.argv:
        if "streamlit" in str(arg).lower():
            return True
    return False


def _suppress_streamlit_noise_if_needed() -> None:
    global _STREAMLIT_NOISE_SUPPRESSED
    if _STREAMLIT_NOISE_SUPPRESSED or _is_streamlit_process():
        return
    for name in (
        "streamlit.runtime",
        "streamlit.runtime.scriptrunner_utils.script_run_context",
        "streamlit.runtime.state.session_state_proxy",
    ):
        logging.getLogger(name).setLevel(logging.ERROR)
    _STREAMLIT_NOISE_SUPPRESSED = True


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
    from pipeline.observability_config import get_observability_settings

    obs_settings = get_observability_settings()

    # 1) Livello
    if level is None:
        level_name = (obs_settings.log_level or "INFO").upper()
        level = getattr(logging, level_name, logging.INFO)
    elif isinstance(level, str):
        level = getattr(logging, level.upper(), logging.INFO)

    _suppress_streamlit_noise_if_needed()

    # 2) Redazione (Observability come default, override opzionale da context/parametro)
    effective_redact = bool(obs_settings.redact_logs)
    if context is not None:
        ctx_attr = getattr(context, "redact_logs", None)
        if ctx_attr is not None:
            effective_redact = bool(ctx_attr)
    if redact_logs is not None:
        effective_redact = bool(redact_logs)

    # 3) Tracing OTEL (Observability come default, override opzionale dal parametro)
    effective_tracing = bool(obs_settings.tracing_enabled)
    if enable_tracing is not None:
        effective_tracing = bool(enable_tracing)

    # 4) Se viene passato un run_id e un log_file, usa un file unico per run:
    #    esempio: onboarding.log -> onboarding-<run_id>.log
    if log_file and run_id:
        try:
            if log_file.suffix:
                log_file = log_file.with_name(f"{log_file.stem}-{run_id}{log_file.suffix}")
        except Exception:
            # fallback: usa il path originale se qualcosa va storto
            pass

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
    ctx.redact_logs = bool(effective_redact)

    # formatter base
    fmt = "%(asctime)s %(levelname)s %(name)s: %(message)s"

    # filtri
    ctx_filter = _ContextFilter(ctx)
    redact_filter = _RedactFilter(bool(effective_redact))
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
        context_settings = getattr(context, "settings", None) if context is not None else None
        max_b_setting: Any = None
        bk_cnt_setting: Any = None
        if context_settings is not None:
            getter = getattr(context_settings, "get", None)
            if callable(getter):
                try:
                    max_b_setting = getter("log_max_bytes", None)
                    bk_cnt_setting = getter("log_backup_count", None)
                except Exception:
                    max_b_setting = None
                    bk_cnt_setting = None
            elif isinstance(context_settings, Mapping):
                max_b_setting = context_settings.get("log_max_bytes")
                bk_cnt_setting = context_settings.get("log_backup_count")
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

    ensure_tracer(context=context, enable_tracing=bool(effective_tracing))
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
        self._span_ctx: ContextManager[Any] | None = None
        self._trace_kind = infer_trace_kind(self.stage)
        self._phase_filter_key = f"{getattr(logger, 'name', 'logger')}::phase::{self.stage}"
        self._phase_filter: logging.Filter | None = None

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
            self._span_ctx = start_phase_span(
                self.stage,
                slug=self.customer,
                run_id=self._run_id,
                trace_kind=self._trace_kind,
            )
            if self._span_ctx is not None:
                self._span = self._span_ctx.__enter__()
        except Exception:
            self._span = None
            self._span_ctx = None
        try:
            self._phase_filter = _PhaseInjectFilter(self.stage)
            # se il logger supporta chiavi dei filtri, usa lo stesso schema di _set_logger_filter
            self.logger.addFilter(self._phase_filter)
        except Exception:
            self._phase_filter = None
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
                record_phase_failed(self.customer, self.stage)
            except Exception:
                pass
            try:
                if self._span is not None:
                    self._span.record_exception(exc)
            except Exception:
                pass
            if self._span is not None:
                try:
                    self._span.set_attribute("status", "failed")
                    if duration_ms is not None:
                        self._span.set_attribute("duration_ms", duration_ms)
                    if self._artifact_count is not None:
                        self._span.set_attribute("artifact_count", self._artifact_count)
                except Exception:
                    pass
            if self._span_ctx is not None:
                try:
                    self._span_ctx.__exit__(exc_type, exc, tb)
                except Exception:
                    pass
            return False
        # Successo: 'status=success'
        extra["status"] = "success"
        self.logger.info("phase_completed", extra={"event": "phase_completed", **extra})
        if self._span is not None:
            try:
                self._span.set_attribute("status", "success")
                if duration_ms is not None:
                    self._span.set_attribute("duration_ms", duration_ms)
                if self._artifact_count is not None:
                    self._span.set_attribute("artifact_count", self._artifact_count)
            except Exception:
                pass
        if self._span_ctx is not None:
            try:
                self._span_ctx.__exit__(None, None, None)
            except Exception:
                pass
        if duration_ms is not None:
            try:
                observe_phase_duration(self.customer, self.stage, duration_ms / 1000.0)
            except Exception:
                pass
        if self._phase_filter is not None:
            try:
                self.logger.removeFilter(self._phase_filter)
            except Exception:
                pass
        return False

    def _base_extra(self) -> dict[str, Any]:
        return {
            "phase": self.stage,
            "slug": self.customer or "-",
            "run_id": self._run_id or "-",
            "trace_kind": self._trace_kind,
        }


PHASE_ARTIFACT_SCHEMA: dict[str, str] = {
    # pipeline / semantic
    "convert_markdown": "numero di markdown di contenuto prodotti (esclude README/SUMMARY)",
    "require_reviewed_vocab": "presenza vocabolario reviewed (bool via artifact_count 0/1)",
    "enrich_frontmatter": "numero di file markdown arricchiti",
    "write_summary_and_readme": "numero file SUMMARY/README scritti/validati (tipicamente 2)",
    # kg/tag builder
    "semantic.tag_kg_builder": "numero di nodi/tag arricchiti (se disponibile)",
    # ingest
    "ingest.embed": "numero di chunk embedding salvati",
    "ingest.persist": "numero di record persistiti",
    "ingest.process_file": "numero di file processati nel batch",
}


def log_workflow_summary(
    logger: logging.Logger,
    *,
    event: str,
    slug: str,
    artifacts: int | None,
    extra: Mapping[str, Any] | None = None,
) -> None:
    """Emette un log di riepilogo uniforme per un workflow CLI/UI.

    Campi standardizzati:
      - event: codice evento (es. 'cli.semantic_onboarding.summary')
      - slug: identificatore cliente
      - artifacts: conteggio principale (coerente con PHASE_ARTIFACT_SCHEMA ove applicabile)
      - altri extra opzionali (es. summary_exists/readme_exists)
    """

    payload: dict[str, Any] = {"slug": slug}
    if artifacts is not None:
        payload["artifacts"] = artifacts
    if extra:
        payload.update(extra)
    logger.info(event, extra=payload)


def log_gate_event(
    logger: logging.Logger,
    event_name: str,
    *,
    fields: Mapping[str, Any] | None = None,
) -> None:
    """Emette eventi canonici di gate con bridge fields best-effort."""
    payload: dict[str, Any] = dict(fields or {})
    ctx_view = getattr(logger, "_logging_ctx_view", None)
    if ctx_view is not None:
        payload.setdefault("slug", getattr(ctx_view, "slug", None))
        payload.setdefault("run_id", getattr(ctx_view, "run_id", None))

    missing: list[str] = [k for k in BRIDGE_FIELDS_ALWAYS if not payload.get(k)]
    tracing_enabled = False
    try:
        from pipeline.observability_config import get_observability_settings

        tracing_enabled = bool(get_observability_settings().tracing_enabled)
    except Exception:
        tracing_enabled = False

    if tracing_enabled and _otel_trace is not None:
        try:
            span = _otel_trace.get_current_span()
            ctx = span.get_span_context()
            if ctx is not None and ctx.is_valid:
                payload.setdefault("trace_id", f"{ctx.trace_id:032x}")
                payload.setdefault("span_id", f"{ctx.span_id:016x}")
        except Exception:
            pass
        missing.extend([k for k in BRIDGE_FIELDS_OTEL if not payload.get(k)])

    if missing:
        payload["missing_fields"] = sorted(set(missing))

    payload["event"] = event_name
    logger.info(event_name, extra=payload)


__all__ = [
    "get_structured_logger",
    "phase_scope",
    "redact_secrets",
    "mask_partial",
    "tail_path",
    "mask_id_map",
    "mask_updates",
    "PHASE_ARTIFACT_SCHEMA",
    "log_workflow_summary",
    "GATE_EVENT_NAMES",
    "BRIDGE_FIELDS_ALWAYS",
    "BRIDGE_FIELDS_OTEL",
    "log_gate_event",
]
