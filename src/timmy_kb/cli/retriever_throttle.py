# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Generator, Mapping, Optional

from pipeline.logging_utils import get_structured_logger

LOGGER = get_structured_logger("timmy_kb.retriever")


@dataclass(frozen=True)
class ThrottleSettings:
    latency_budget_ms: int = 0
    parallelism: int = 1
    sleep_ms_between_calls: int = 0
    acquire_timeout_ms: int | None = None


_MAX_PARALLELISM = 32


class _ThrottleState:
    def __init__(self, parallelism: int) -> None:
        self.parallelism = max(1, parallelism)
        self._semaphore = threading.BoundedSemaphore(self.parallelism)
        self._lock = threading.Lock()
        self._cond = threading.Condition(self._lock)
        self._last_completed = 0.0

    def acquire(self, *, timeout_s: float | None = None) -> bool:
        if timeout_s is None:
            self._semaphore.acquire()
            return True
        return bool(self._semaphore.acquire(timeout=timeout_s))

    def release(self) -> None:
        self._semaphore.release()

    def wait_interval(self, sleep_ms: int, *, deadline: float | None = None) -> bool:
        if sleep_ms <= 0:
            return False

        min_interval = sleep_ms / 1000.0

        def _ready() -> bool:
            if deadline is not None and time.perf_counter() >= deadline:
                return True
            if self._last_completed == 0.0:
                return True
            return (time.perf_counter() - self._last_completed) >= min_interval

        with self._cond:
            if _ready():
                return deadline is not None and time.perf_counter() >= deadline
            timeout = None
            if deadline is not None:
                timeout = max(0.0, deadline - time.perf_counter())
            self._cond.wait_for(_ready, timeout=timeout)
            return deadline is not None and time.perf_counter() >= deadline

    def mark_complete(self) -> None:
        with self._cond:
            self._last_completed = time.perf_counter()
            self._cond.notify_all()


class _ThrottleRegistry:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._states: dict[str, _ThrottleState] = {}

    def get_state(self, key: str, parallelism: int) -> _ThrottleState:
        normalized = max(1, min(_MAX_PARALLELISM, parallelism))
        with self._lock:
            state = self._states.get(key)
            if state is None or state.parallelism != normalized:
                state = _ThrottleState(normalized)
                self._states[key] = state
        return state


_THROTTLE_REGISTRY = _ThrottleRegistry()


def reset_throttle_registry() -> None:
    """Svuota lo stato di throttling (uso test/benchmark)."""
    with _THROTTLE_REGISTRY._lock:  # pragma: no cover - helper test
        _THROTTLE_REGISTRY._states.clear()


@contextmanager
def _throttle_guard(
    key: str, settings: Optional[ThrottleSettings], *, deadline: float | None = None
) -> Generator[None, None, None]:
    if settings is None:
        yield
        return
    state = _THROTTLE_REGISTRY.get_state(key, settings.parallelism)
    timeout_s: float | None = None
    if settings.acquire_timeout_ms and settings.acquire_timeout_ms > 0:
        timeout_s = settings.acquire_timeout_ms / 1000.0
    acquired = state.acquire(timeout_s=timeout_s)
    if not acquired:
        LOGGER.warning(
            "retriever.throttle.timeout",
            extra={
                "key": key,
                "timeout_ms": settings.acquire_timeout_ms,
                "slug": key.split("::", maxsplit=1)[0],
            },
        )
        yield
        return
    try:
        deadline_hit = state.wait_interval(settings.sleep_ms_between_calls, deadline=deadline)
        if deadline_hit and deadline is not None:
            LOGGER.warning(
                "retriever.throttle.deadline",
                extra={
                    "key": key,
                    "deadline_ms": int(settings.latency_budget_ms or 0),
                    "slug": key.split("::", maxsplit=1)[0],
                },
            )
        yield
    finally:
        state.mark_complete()
        state.release()


def _coerce_retriever_section(config: Optional[Mapping[str, Any]]) -> Mapping[str, Any]:
    if not config:
        return {}
    retr = config.get("retriever")
    if isinstance(retr, Mapping):
        return retr
    return {}


def _coerce_throttle_section(retriever_section: Mapping[str, Any]) -> Mapping[str, Any]:
    throttle = retriever_section.get("throttle")
    if isinstance(throttle, Mapping):
        return throttle
    return {}


def _safe_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _build_throttle_settings(config: Optional[Mapping[str, Any]]) -> ThrottleSettings:
    retr = _coerce_retriever_section(config)
    throttle = _coerce_throttle_section(retr)
    timeout_raw = throttle.get("acquire_timeout_ms")
    timeout_val = None
    try:
        parsed = int(timeout_raw)
        timeout_val = parsed if parsed > 0 else None
    except Exception:
        timeout_val = None
    return ThrottleSettings(
        latency_budget_ms=_safe_int(throttle.get("latency_budget_ms"), _safe_int(retr.get("latency_budget_ms"), 0)),
        parallelism=_safe_int(throttle.get("parallelism"), 1),
        sleep_ms_between_calls=_safe_int(throttle.get("sleep_ms_between_calls"), 0),
        acquire_timeout_ms=timeout_val,
    )


def _normalize_throttle_settings(settings: Optional[ThrottleSettings]) -> Optional[ThrottleSettings]:
    if settings is None:
        return None
    normalized = ThrottleSettings(
        latency_budget_ms=max(0, int(settings.latency_budget_ms)),
        parallelism=max(1, min(_MAX_PARALLELISM, int(settings.parallelism))),
        sleep_ms_between_calls=max(0, int(settings.sleep_ms_between_calls)),
        acquire_timeout_ms=(None if settings.acquire_timeout_ms is None else max(0, int(settings.acquire_timeout_ms))),
    )
    if (
        normalized.latency_budget_ms == 0
        and normalized.parallelism == 1
        and normalized.sleep_ms_between_calls == 0
        and normalized.acquire_timeout_ms is None
    ):
        return None
    return normalized


def _deadline_from_settings(settings: Optional[ThrottleSettings]) -> Optional[float]:
    if settings and settings.latency_budget_ms > 0:
        return time.perf_counter() + settings.latency_budget_ms / 1000.0
    return None


def _deadline_exceeded(deadline: Optional[float]) -> bool:
    return deadline is not None and time.perf_counter() >= deadline
