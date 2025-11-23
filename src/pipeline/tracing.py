# SPDX-License-Identifier: GPL-3.0-only
"""Helper di tracing Otel per inbox Timmy."""

from __future__ import annotations

import contextlib
import os
from typing import TYPE_CHECKING, Any, ContextManager, Mapping

if TYPE_CHECKING:
    from pipeline.observability_config import ObservabilitySettings

try:
    from opentelemetry import trace as _otel_trace
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    _OTEL_IMPORT_OK = True
except Exception:  # pragma: no cover
    _OTEL_IMPORT_OK = False

_TRACING_READY = False
_TRACER_NAME = "timmykb"


def _load_settings() -> "ObservabilitySettings":
    try:
        from pipeline.observability_config import load_observability_settings

        return load_observability_settings()
    except Exception:

        class _FallbackSettings:
            stack_enabled = False
            tracing_enabled = False
            redact_logs = True
            log_level = "INFO"

        return _FallbackSettings()  # type: ignore[return-value]


def _is_enabled() -> bool:
    return _OTEL_IMPORT_OK and bool(os.getenv("TIMMY_OTEL_ENDPOINT")) and _load_settings().tracing_enabled


def ensure_tracer(*, context: Mapping[str, Any] | None = None, enable_tracing: bool = True) -> None:
    """Inizializza il tracer globale (idempotente)."""
    global _TRACING_READY
    if not enable_tracing or _TRACING_READY or not _is_enabled():
        return
    endpoint = os.getenv("TIMMY_OTEL_ENDPOINT")
    if not endpoint:
        return
    service = os.getenv("TIMMY_SERVICE_NAME", "timmy-kb")
    env = os.getenv("TIMMY_ENV", "dev")
    slug = ""
    if context:
        try:
            slug_val = getattr(context, "slug", None)
        except Exception:
            slug_val = None
        if slug_val is None and isinstance(context, Mapping):
            slug_val = context.get("slug")
        slug = str(slug_val or "")
    resource = Resource.create({"service.name": service, "deployment.environment": env, "customer.slug": slug})
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

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> bool:
        return False

    def set_attribute(self, *_: Any, **__kwargs: Any) -> "_NoopSpan":
        return self

    def record_exception(self, *_: Any, **__kwargs: Any) -> "_NoopSpan":
        return self

    def add_event(self, *_: Any, **__kwargs: Any) -> "_NoopSpan":
        return self


@contextlib.contextmanager
def _span_context(
    name: str, *, attributes: Mapping[str, Any] | None = None
) -> ContextManager[_otel_trace.Span | _NoopSpan]:
    ensure_tracer()
    if not _TRACING_READY or not _OTEL_IMPORT_OK:
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
    return _span_context(f"timmykb.{journey}", attributes=attrs)


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
    phase: str | None,
    attributes: Mapping[str, Any] | None = None,
) -> ContextManager[_otel_trace.Span | _NoopSpan]:
    base_attrs = {
        "decision_type": decision_type,
        "slug": slug,
        "run_id": run_id,
        "trace_kind": trace_kind,
    }
    if phase:
        base_attrs["phase"] = phase
    base_attrs.update(_normalize_attrs(attributes))
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
