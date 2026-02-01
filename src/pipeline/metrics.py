#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""
Metriche Prometheus opzionali per Timmy KB (hard cut 1.0 Beta).

Principi:
- Le metriche sono abilitate solo se richieste esplicitamente (env/parametri).
- Se abilitate, `prometheus_client` deve essere presente: nessuna degradazione silenziosa.
- Se non abilitate, il modulo resta inattivo (niente server, niente export).
"""

from __future__ import annotations

import logging
import os
from typing import Any, Callable, Optional

from .exceptions import ConfigError

_log = logging.getLogger("pipeline.metrics")

_METRICS_STARTED = False
_METRICS_INITIALIZED = False
_PROMETHEUS_COUNTER: Any | None = None
_PROMETHEUS_HISTOGRAM: Any | None = None
start_http_server: Callable[[int], None] | None = None
documents_processed_total: Any | None = None
phase_failed_total: Any | None = None
phase_duration_seconds: Any | None = None


def _metrics_requested(port: Optional[int]) -> bool:
    """Determina se le metriche sono state richieste in modo esplicito."""
    enabled_env = (os.getenv("TIMMY_METRICS_ENABLED") or "").strip().lower()
    env_port = os.getenv("TIMMY_METRICS_PORT")
    return bool(enabled_env in {"1", "true", "yes", "on"} or env_port or port is not None)


def _resolve_metrics_port(port: Optional[int]) -> int:
    candidate = port if port is not None else os.getenv("TIMMY_METRICS_PORT", "8000")
    try:
        return int(str(candidate))
    except Exception as exc:  # pragma: no cover - error path
        raise ConfigError("Porta metrica non valida", file_path=str(candidate)) from exc


def _require_prometheus() -> None:
    """Importa prometheus_client oppure fallisce esplicitamente."""
    global _PROMETHEUS_COUNTER, _PROMETHEUS_HISTOGRAM, start_http_server
    if _PROMETHEUS_COUNTER and _PROMETHEUS_HISTOGRAM and start_http_server:
        return
    try:
        from prometheus_client import Counter, Histogram
        from prometheus_client import start_http_server as _start
    except Exception as exc:  # pragma: no cover - dependency missing
        raise ConfigError(
            "Metriche abilitate ma prometheus_client mancante",
            file_path="prometheus_client",
        ) from exc
    _PROMETHEUS_COUNTER = Counter
    _PROMETHEUS_HISTOGRAM = Histogram
    start_http_server = _start


def _ensure_metrics_initialized() -> None:
    """Inizializza i collector Prometheus se non già fatti."""
    global _METRICS_INITIALIZED, documents_processed_total, phase_failed_total, phase_duration_seconds
    if _METRICS_INITIALIZED:
        return
    _require_prometheus()
    documents_processed_total = _PROMETHEUS_COUNTER(
        "documents_processed_total",
        "Numero di documenti processati",
        labelnames=("slug",),
    )
    phase_failed_total = _PROMETHEUS_COUNTER(
        "phase_failed_total",
        "Conteggio fasi fallite",
        labelnames=("slug", "phase"),
    )
    phase_duration_seconds = _PROMETHEUS_HISTOGRAM(
        "phase_duration_seconds",
        "Durata delle fasi in secondi",
        labelnames=("slug", "phase"),
    )
    _METRICS_INITIALIZED = True


def start_metrics_server_once(port: Optional[int] = None) -> None:
    """Avvia il server /metrics una sola volta se le metriche sono esplicitamente abilitate."""
    global _METRICS_STARTED
    if _METRICS_STARTED:
        return
    if not _metrics_requested(port):
        _log.info("observability.metrics.skipped", extra={"reason": "not_requested"})
        return

    _ensure_metrics_initialized()
    eff_port = _resolve_metrics_port(port)

    if start_http_server is None:
        raise ConfigError(
            "Metriche abilitate ma prometheus_client non inizializzato correttamente",
            file_path="prometheus_client",
        )

    try:
        start_http_server(eff_port)
        _METRICS_STARTED = True
    except Exception as exc:
        _METRICS_STARTED = False
        _log.error(
            "observability.metrics.bind_failed",
            exc_info=exc,
            extra={"port": eff_port},
        )
        raise


def record_document_processed(slug: Optional[str], count: int = 1) -> None:
    if not _METRICS_INITIALIZED or documents_processed_total is None:
        return
    try:
        documents_processed_total.labels(slug=slug or "-").inc(count)
    except Exception:
        return


def record_phase_failed(slug: Optional[str], phase: str) -> None:
    if not _METRICS_INITIALIZED or phase_failed_total is None:
        return
    try:
        phase_failed_total.labels(slug=slug or "-", phase=phase).inc()
    except Exception:
        return


def observe_phase_duration(slug: Optional[str], phase: str, duration_seconds: float) -> None:
    if not _METRICS_INITIALIZED or phase_duration_seconds is None:
        return
    try:
        phase_duration_seconds.labels(slug=slug or "-", phase=phase).observe(max(0.0, float(duration_seconds)))
    except Exception:
        return


__all__ = [
    "start_metrics_server_once",
    "record_document_processed",
    "record_phase_failed",
    "observe_phase_duration",
]
