# SPDX-License-Identifier: GPL-3.0-or-later
import time
from contextlib import nullcontext

import pytest

import timmy_kb.cli.retriever as retriever


def test_wait_interval_returns_true_when_deadline_passed() -> None:
    state = retriever._ThrottleState(1)  # noqa: SLF001 - test interno
    state._last_completed = time.perf_counter()  # forza attesa su sleep_ms > 0  # noqa: SLF001
    start = time.perf_counter()

    hit = state.wait_interval(50, deadline=start - 0.001)

    assert hit is True


def test_throttle_guard_logs_deadline(monkeypatch, caplog: pytest.LogCaptureFixture) -> None:
    state = retriever._ThrottleState(1)  # noqa: SLF001
    state._last_completed = time.perf_counter()  # noqa: SLF001

    class _Registry:
        def get_state(self, key: str, parallelism: int) -> retriever._ThrottleState:  # noqa: SLF001
            return state

    monkeypatch.setattr(retriever, "_THROTTLE_REGISTRY", _Registry())

    settings = retriever.ThrottleSettings(
        latency_budget_ms=1,
        parallelism=1,
        sleep_ms_between_calls=50,
        acquire_timeout_ms=None,
    )
    normalized = retriever._normalize_throttle_settings(settings)  # noqa: SLF001
    deadline = retriever._deadline_from_settings(normalized)  # noqa: SLF001

    caplog.set_level("WARNING")
    with retriever._throttle_guard("k", normalized, deadline=deadline):  # noqa: SLF001
        pass

    assert any(rec.getMessage() == "retriever.throttle.deadline" for rec in caplog.records)


def test_throttle_guard_registry_rebind_is_idempotent(monkeypatch) -> None:
    old_registry = {}
    captured: list[object] = []

    def _fake_guard(_key, _settings, *, deadline=None):  # noqa: ARG001
        captured.append(retriever.throttle_mod._THROTTLE_REGISTRY)
        return nullcontext()

    monkeypatch.setattr(retriever.throttle_mod, "_THROTTLE_REGISTRY", old_registry)
    monkeypatch.setattr(retriever.throttle_mod, "_throttle_guard", _fake_guard)

    with retriever._throttle_guard("k", None, deadline=None):  # noqa: SLF001
        pass
    with retriever._throttle_guard("k", None, deadline=None):  # noqa: SLF001
        pass

    assert captured == [retriever._THROTTLE_REGISTRY, retriever._THROTTLE_REGISTRY]  # noqa: SLF001
    assert retriever.throttle_mod._THROTTLE_REGISTRY is retriever._THROTTLE_REGISTRY  # noqa: SLF001
