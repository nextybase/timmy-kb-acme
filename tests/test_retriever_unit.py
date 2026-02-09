# SPDX-License-Identifier: GPL-3.0-or-later
# tests/test_retriever_unit.py
# Test unitari mirati per:
# - cosine() iterator-safe (Sequence non indicizzabili, lunghezze diverse, norme nulle)
# - SSoT/precedenza candidate_limit
#   (with_config_candidate_limit / with_config_or_budget / preview_effective_candidate_limit)

import math
import time
from collections import deque
from pathlib import Path
from typing import Any, Callable, Iterable

import pytest

import timmy_kb.cli.retriever as retriever
from tests.conftest import DUMMY_SLUG
from timmy_kb.cli.retriever import (
    QueryParams,
    cosine,
    preview_effective_candidate_limit,
    with_config_candidate_limit,
    with_config_or_budget,
)

pytestmark = pytest.mark.unit

# ----------------------------- Test cosine (iterator-safe) -----------------------------


def test_cosine_perfect_match_with_deque():
    # deque è Sequence ma non necessariamente slice-friendly; zip deve bastare
    a = deque([1.0, 2.0, 3.0, 4.0])
    b = deque([1.0, 2.0, 3.0, 4.0])
    val = cosine(a, b)
    assert abs(val - 1.0) < 1e-12


def test_cosine_length_mismatch_truncates_min_len():
    # Vettori di lunghezza diversa -> zip tronca al min
    # dot = 1*1 + 1*0 = 1; ||a|| = sqrt(1^2+1^2+0^2)=sqrt(2); ||b|| = sqrt(1^2+0^2)=1
    a = [1.0, 1.0, 0.0]
    b = (1.0, 0.0)  # tuple per variare tipo
    val = cosine(a, b)
    assert abs(val - (1.0 / math.sqrt(2.0))) < 1e-12


def test_cosine_zero_norm_returns_zero():
    # Norma nulla => 0.0
    a = [0.0, 0.0, 0.0]
    b = [1.0, 2.0, 3.0]
    assert cosine(a, b) == 0.0
    assert cosine(b, a) == 0.0


# ----------------------- Test SSoT / precedence candidate_limit -----------------------


def test_cosine_large_generator_handles_massive_input():
    size = 200_000

    def factory() -> Iterable[float]:
        for i in range(size):
            yield float((i % 11) - 5)

    val = cosine(factory(), factory())
    assert val == pytest.approx(1.0, rel=1e-12)


def test_cosine_scales_huge_magnitudes():
    size = 4096
    huge = 1e308

    def make_vec(sign: float):
        return (huge * sign for _ in range(size))

    same = cosine(make_vec(1.0), make_vec(1.0))
    opposite = cosine(make_vec(1.0), make_vec(-1.0))
    assert same == pytest.approx(1.0, rel=1e-12)
    assert opposite == pytest.approx(-1.0, rel=1e-12)


@pytest.fixture
def default_params(kb_sqlite_path: Path) -> Callable[..., QueryParams]:
    def _build(**over: Any) -> QueryParams:
        return QueryParams(
            db_path=kb_sqlite_path,
            slug=DUMMY_SLUG,
            scope="kb",
            query="test",
            k=8,
            candidate_limit=4000,
            **over,
        )

    return _build


def test_with_config_candidate_limit_explicit_not_overridden(default_params):
    params = default_params()
    # Esplicito diverso dal default => non va sovrascritto
    params = params.__class__(**{**params.__dict__, "candidate_limit": 777})
    cfg = {"retriever": {"throttle": {"candidate_limit": 1234}}}
    out = with_config_candidate_limit(params, cfg)
    assert out.candidate_limit == 777


def test_with_config_candidate_limit_uses_config_when_default(default_params):
    params = default_params()  # candidate_limit rimane al default del dataclass
    cfg = {"retriever": {"throttle": {"candidate_limit": 1234}}}
    out = with_config_candidate_limit(params, cfg)
    assert out.candidate_limit == 1234


def test_with_config_or_budget_explicit_wins_even_with_auto_budget(default_params):
    params = default_params()
    params = params.__class__(**{**params.__dict__, "candidate_limit": 9000})
    cfg = {
        "retriever": {
            "auto_by_budget": True,
            "throttle": {"latency_budget_ms": 150, "candidate_limit": 1111},
        }
    }
    out = with_config_or_budget(params, cfg)
    assert out.candidate_limit == 9000  # esplicito non deve cambiare


@pytest.mark.parametrize(
    "budget_ms,expected",
    [
        (150, 1000),  # <= 180ms
        (260, 2000),  # <= 280ms
        (420, 4000),  # <= 420ms
        (450, 8000),  # > 420ms
    ],
)
def test_with_config_or_budget_auto_budget_thresholds(budget_ms, expected, default_params):
    params = default_params()  # default -> eleggibile a override
    cfg = {"retriever": {"auto_by_budget": True, "throttle": {"latency_budget_ms": budget_ms}}}
    out = with_config_or_budget(params, cfg)
    assert out.candidate_limit == expected


def test_with_config_or_budget_uses_config_when_no_auto_budget(default_params):
    params = default_params()  # default -> eleggibile a override
    cfg = {"retriever": {"throttle": {"candidate_limit": 2222}}}
    out = with_config_or_budget(params, cfg)
    assert out.candidate_limit == 2222


def test_preview_effective_candidate_limit_reports_sources_correctly(default_params):
    # 1) explicit
    p_explicit = default_params()
    p_explicit = p_explicit.__class__(**{**p_explicit.__dict__, "candidate_limit": 777})
    lim, source, budget = preview_effective_candidate_limit(p_explicit, {})
    assert (lim, source, budget) == (777, "explicit", 0)

    # 2) auto_by_budget
    p_auto = default_params()
    cfg_auto = {"retriever": {"auto_by_budget": True, "throttle": {"latency_budget_ms": 260}}}
    lim, source, budget = preview_effective_candidate_limit(p_auto, cfg_auto)
    assert (lim, source, budget) == (2000, "auto_by_budget", 260)

    # 3) config
    p_cfg = default_params()
    cfg = {"retriever": {"throttle": {"candidate_limit": 3333}}}
    lim, source, budget = preview_effective_candidate_limit(p_cfg, cfg)
    assert (lim, source, budget) == (3333, "config", 0)

    # 4) default
    p_def = default_params()
    lim, source, budget = preview_effective_candidate_limit(p_def, {})
    assert (lim, source, budget) == (4000, "default", 0)


class _DummyEmbeddingsClient:
    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [[0.1, 0.2, 0.3]]


def test_search_with_config_passes_throttle(monkeypatch: pytest.MonkeyPatch, default_params):
    params = default_params()
    captured: dict[str, object] = {}

    def _fake_search(*args, **kwargs):
        captured["throttle"] = kwargs.get("throttle")
        captured["throttle_key"] = kwargs.get("throttle_key")
        return []

    monkeypatch.setattr(retriever, "search", _fake_search)
    cfg = {"retriever": {"throttle": {"parallelism": 3, "sleep_ms_between_calls": 25, "latency_budget_ms": 150}}}
    retriever.search_with_config(params, cfg, _DummyEmbeddingsClient())

    throttle = captured["throttle"]
    assert throttle is not None
    assert throttle.parallelism == 3
    assert throttle.sleep_ms_between_calls == 25
    assert throttle.latency_budget_ms == 150
    assert captured["throttle_key"] == f"{params.slug}::{params.scope}"


def test_rank_candidates_respects_deadline():
    query = [1.0, 0.0]
    candidates = [{"embedding": [1.0, 0.0], "content": f"doc-{idx}", "meta": {}} for idx in range(1000)]
    deadline = time.perf_counter() + 0.001
    _, total, _, _, evaluated, budget_hit = retriever._rank_candidates(  # type: ignore[attr-defined]
        query,
        candidates,
        5,
        deadline=deadline,
    )
    assert total == len(candidates)
    assert budget_hit is True
    assert evaluated <= len(candidates)
