# SPDX-License-Identifier: GPL-3.0-only
"""Helper di tracing Otel per inbox Timmy."""

from __future__ import annotations

import contextlib
import logging
import os
import random
from typing import Any, ContextManager, Iterator, Literal, Mapping

from pipeline.observability_config import get_tracing_state

_log = logging.getLogger("pipeline.tracing")
_TRACING_DISABLED_EMITTED: set[str] = set()


def _log_tracing_disabled(reason: str, extra: Mapping[str, Any] | None = None) -> None:
    if reason in _TRACING_DISABLED_EMITTED:
        return
    _TRACING_DISABLED_EMITTED.add(reason)
    payload = {"reason": reason}
    if extra:
        payload.update(extra)
    _log.warning("observability.tracing.disabled", extra=payload)


try:
    from opentelemetry import trace as _otel_trace
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    _OTEL_IMPORT_OK = True
except Exception:  # pragma: no cover
    _OTEL_IMPORT_OK = False
    _log_tracing_disabled("opentelemetry_missing")

_TRACING_READY = False
_TRACER_NAME = "timmy_kb"
_raw_sampling = os.getenv("TIMMY_DECISION_SPAN_SAMPLING", "1.0")
try:
    _DECISION_SPAN_SAMPLING = float(_raw_sampling)
except ValueError:
    _DECISION_SPAN_SAMPLING = 1.0


def _is_enabled() -> bool:
    if not _OTEL_IMPORT_OK:
        _log_tracing_disabled("opentelemetry_missing")
        return False
    state = get_tracing_state()
    enabled = bool(getattr(state, "effective_enabled", False))
    if not enabled:
        _log_tracing_disabled("disabled_by_config")
    return enabled


def ensure_tracer(*, context: Mapping[str, Any] | None = None, enable_tracing: bool = True) -> None:
    """Inizializza il tracer globale (idempotente)."""
    global _TRACING_READY
    if not enable_tracing:
        _log_tracing_disabled("disabled_by_flag", extra={"context_provided": bool(context)})
        return
    if _TRACING_READY or not _is_enabled():
        return
    endpoint = os.getenv("TIMMY_OTEL_ENDPOINT")
    if not endpoint:
        _log_tracing_disabled("missing_endpoint")
        return
    service = os.getenv("TIMMY_SERVICE_NAME", "timmy-kb")
    env = os.getenv("TIMMY_ENV", "dev")
    resource = Resource.create({"service.name": service, "deployment.environment": env})
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint)))
    _otel_trace.set_tracer_provider(provider)
    _TRACING_READY = True


def is_tracing_active() -> bool:
    return _TRACING_READY or _is_enabled()


class _NoopSpan:
    """Span no-op usato quando il tracing è disabilitato."""

    def __enter__(self) -> "_NoopSpan":
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> Literal[False]:
        return False

    def set_attribute(self, *_: Any, **__kwargs: Any) -> "_NoopSpan":
        return self

    def record_exception(self, *_: Any, **__kwargs: Any) -> "_NoopSpan":
        return self

    def add_event(self, *_: Any, **__kwargs: Any) -> "_NoopSpan":
        return self


@contextlib.contextmanager
def _span_context(name: str, *, attributes: Mapping[str, Any] | None = None) -> Iterator[_otel_trace.Span | _NoopSpan]:
    ensure_tracer()
    if not _TRACING_READY or not _OTEL_IMPORT_OK:
        _log_tracing_disabled("tracer_not_ready", extra={"otel_import_ok": _OTEL_IMPORT_OK})
        yield _NoopSpan()
        return
    tracer = _otel_trace.get_tracer(_TRACER_NAME)
    with tracer.start_as_current_span(name, attributes=dict(attributes or {})) as span:
        yield span


def _normalize_attrs(attrs: Mapping[str, Any] | None) -> dict[str, Any]:
    result: dict[str, Any] = {}
    if not attrs:
        return result
    for key, value in attrs.items():
        if value is not None:
            result[key] = value
    return result


def start_root_trace(
    journey: str,
    *,
    slug: str | None,
    run_id: str | None,
    entry_point: str,
    env: str,
    trace_kind: str,
    extra: Mapping[str, Any] | None = None,
) -> ContextManager[_otel_trace.Span | _NoopSpan]:
    attrs = {
        "slug": slug,
        "run_id": run_id,
        "trace_kind": trace_kind,
        "entry_point": entry_point,
        "env": env,
        "journey": journey,
    }
    attrs.update(_normalize_attrs(extra))
    return _span_context(f"timmy_kb.{journey}", attributes=attrs)


def start_phase_span(
    phase: str,
    *,
    slug: str | None,
    run_id: str | None,
    trace_kind: str,
    attributes: Mapping[str, Any] | None = None,
) -> ContextManager[_otel_trace.Span | _NoopSpan]:
    base_attrs = {
        "slug": slug,
        "run_id": run_id,
        "phase": phase,
        "trace_kind": trace_kind,
    }
    base_attrs.update(_normalize_attrs(attributes))
    return _span_context(f"phase:{phase}", attributes=base_attrs)


def start_decision_span(
    decision_type: str,
    *,
    slug: str | None,
    run_id: str | None,
    trace_kind: str,
    phase: str | None = None,
    file_path_relative: str | None = None,
    dataset_area: str | None = None,
    er_entity_type: str | None = None,
    er_relation_type: str | None = None,
    policy_id: str | None = None,
    risk_level: str | None = None,
    hilt_involved: bool | None = None,
    decision_channel: str | None = None,
    petrov_action: str | None = None,
    model_version: str | None = None,
    attributes: Mapping[str, Any] | None = None,
    extra_attributes: Mapping[str, Any] | None = None,
) -> ContextManager[_otel_trace.Span | _NoopSpan]:
    if _DECISION_SPAN_SAMPLING < 1.0 and random.random() > _DECISION_SPAN_SAMPLING:
        return contextlib.nullcontext(_NoopSpan())
    base_attrs: dict[str, Any] = {
        "decision_type": decision_type,
        "slug": slug,
        "run_id": run_id,
        "trace_kind": trace_kind,
    }
    if phase:
        base_attrs["phase"] = phase
    if file_path_relative:
        base_attrs["file_path_relative"] = file_path_relative
    if dataset_area:
        base_attrs["dataset_area"] = dataset_area
    if er_entity_type:
        base_attrs["er_entity_type"] = er_entity_type
    if er_relation_type:
        base_attrs["er_relation_type"] = er_relation_type
    if policy_id:
        base_attrs["policy_id"] = policy_id
    if risk_level:
        base_attrs["risk_level"] = risk_level
    if hilt_involved is not None:
        base_attrs["hilt_involved"] = hilt_involved
    if decision_channel:
        base_attrs["decision_channel"] = decision_channel
    if petrov_action:
        base_attrs["petrov_action"] = petrov_action
    if model_version:
        base_attrs["model_version"] = model_version
    for extra in (attributes, extra_attributes):
        base_attrs.update(_normalize_attrs(extra))
    return _span_context(f"decision:{decision_type}", attributes=base_attrs)


def infer_trace_kind(stage: str) -> str:
    lower = (stage or "").lower()
    if lower.startswith("ingest"):
        return "ingest"
    if lower.startswith("semantic") or lower.startswith("tag") or lower.startswith("pre_onboarding"):
        return "onboarding"
    if lower.startswith("index") or lower.startswith("reindex"):
        return "reindex"
    return "onboarding"


__all__ = [
    "start_root_trace",
    "start_phase_span",
    "start_decision_span",
    "ensure_tracer",
    "infer_trace_kind",
    "is_tracing_active",
]
