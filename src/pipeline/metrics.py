#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""
Metriche Prometheus (opzionali) per Timmy KB.

Espone:
- Counter `documents_processed_total` (labels: slug)
- Counter `phase_failed_total` (labels: slug, phase)
- Histogram `phase_duration_seconds` (labels: slug, phase)

L'endpoint /metrics viene esposto tramite `start_metrics_server_once()`
se la libreria `prometheus_client` è installata. In caso contrario, le
funzioni sono no-op per non bloccare il runtime.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Optional, cast

_log = logging.getLogger("pipeline.metrics")

_PROM_AVAILABLE = False
_METRICS_STARTED = False
_METRICS_DISABLED_EMITTED = False


def _log_metrics_disabled(reason: str, extra: Optional[dict[str, Any]] = None) -> None:
    global _METRICS_DISABLED_EMITTED
    if _METRICS_DISABLED_EMITTED:
        return
    _METRICS_DISABLED_EMITTED = True
    _log.warning("observability.metrics.disabled", extra={"reason": reason, **(extra or {})})


try:
    from prometheus_client import Counter, Histogram, start_http_server

    _PROM_AVAILABLE = True
except Exception:  # pragma: no cover - opzionale
    _log_metrics_disabled("prometheus_client_missing")
    Counter = cast(Any, None)
    Histogram = cast(Any, None)
    start_http_server = cast(Any, None)

if _PROM_AVAILABLE:
    documents_processed_total = Counter(
        "documents_processed_total",
        "Numero di documenti processati",
        labelnames=("slug",),
    )
    phase_failed_total = Counter(
        "phase_failed_total",
        "Conteggio fasi fallite",
        labelnames=("slug", "phase"),
    )
    phase_duration_seconds = Histogram(
        "phase_duration_seconds",
        "Durata delle fasi in secondi",
        labelnames=("slug", "phase"),
    )
else:  # pragma: no cover - no-op fallback
    documents_processed_total = None
    phase_failed_total = None
    phase_duration_seconds = None


def start_metrics_server_once(port: Optional[int] = None) -> None:
    """Avvia il server /metrics una sola volta (se prometheus_client è disponibile)."""
    global _METRICS_STARTED
    if _METRICS_STARTED or not _PROM_AVAILABLE or start_http_server is None:
        if not _PROM_AVAILABLE or start_http_server is None:
            _log_metrics_disabled("prometheus_client_unavailable")
        return
    try:
        env_port = os.getenv("TIMMY_METRICS_PORT")
        eff_port_str = str(port) if port is not None else (env_port or "8000")
        eff_port = int(eff_port_str)
    except (ValueError, TypeError):
        eff_port = 8000
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
        raise


def record_document_processed(slug: Optional[str], count: int = 1) -> None:
    if not _PROM_AVAILABLE or documents_processed_total is None:
        _log_metrics_disabled("prometheus_client_unavailable")
        return
    try:
        documents_processed_total.labels(slug=slug or "-").inc(count)
    except Exception:
        return


def record_phase_failed(slug: Optional[str], phase: str) -> None:
    if not _PROM_AVAILABLE or phase_failed_total is None:
        _log_metrics_disabled("prometheus_client_unavailable")
        return
    try:
        phase_failed_total.labels(slug=slug or "-", phase=phase).inc()
    except Exception:
        return


def observe_phase_duration(slug: Optional[str], phase: str, duration_seconds: float) -> None:
    if not _PROM_AVAILABLE or phase_duration_seconds is None:
        _log_metrics_disabled("prometheus_client_unavailable")
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
