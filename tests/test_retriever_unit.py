# tests/test_retriever_unit.py
# Test unitari mirati per:
# - cosine() iterator-safe (Sequence non indicizzabili, lunghezze diverse, norme nulle)
# - SSoT/precedenza candidate_limit
#   (with_config_candidate_limit / with_config_or_budget / preview_effective_candidate_limit)

import math
from collections import deque

import pytest

from src.retriever import (
    QueryParams,
    cosine,
    preview_effective_candidate_limit,
    with_config_candidate_limit,
    with_config_or_budget,
)

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


def _default_params():
    # Usa i default del dataclass (candidate_limit=4000 by design)
    return QueryParams(
        db_path=None,
        project_slug="acme",
        scope="kb",
        query="test",
        # k default = 8 nel dataclass
        # candidate_limit default = 4000 nel dataclass
    )


def test_with_config_candidate_limit_explicit_not_overridden():
    params = _default_params()
    # Esplicito diverso dal default => non va sovrascritto
    params = params.__class__(**{**params.__dict__, "candidate_limit": 777})
    cfg = {"retriever": {"candidate_limit": 1234}}
    out = with_config_candidate_limit(params, cfg)
    assert out.candidate_limit == 777


def test_with_config_candidate_limit_uses_config_when_default():
    params = _default_params()  # candidate_limit rimane al default del dataclass
    cfg = {"retriever": {"candidate_limit": 1234}}
    out = with_config_candidate_limit(params, cfg)
    assert out.candidate_limit == 1234


def test_with_config_candidate_limit_falls_back_to_default_when_cfg_missing():
    params = _default_params()
    out = with_config_candidate_limit(params, {})  # nessun retriever.candidate_limit
    assert out.candidate_limit == 4000  # default del dataclass


def test_with_config_or_budget_explicit_wins_even_with_auto_budget():
    params = _default_params()
    params = params.__class__(**{**params.__dict__, "candidate_limit": 9000})
    cfg = {
        "retriever": {
            "auto_by_budget": True,
            "latency_budget_ms": 150,
            "candidate_limit": 1111,
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
def test_with_config_or_budget_auto_budget_thresholds(budget_ms, expected):
    params = _default_params()  # default -> eleggibile a override
    cfg = {"retriever": {"auto_by_budget": True, "latency_budget_ms": budget_ms}}
    out = with_config_or_budget(params, cfg)
    assert out.candidate_limit == expected


def test_with_config_or_budget_uses_config_when_no_auto_budget():
    params = _default_params()  # default -> eleggibile a override
    cfg = {"retriever": {"candidate_limit": 2222}}
    out = with_config_or_budget(params, cfg)
    assert out.candidate_limit == 2222


def test_with_config_or_budget_falls_back_to_default():
    params = _default_params()
    cfg = {}  # niente auto, niente candidate_limit
    out = with_config_or_budget(params, cfg)
    assert out.candidate_limit == 4000


def test_preview_effective_candidate_limit_reports_sources_correctly():
    # 1) explicit
    p_explicit = _default_params()
    p_explicit = p_explicit.__class__(**{**p_explicit.__dict__, "candidate_limit": 777})
    lim, source, budget = preview_effective_candidate_limit(p_explicit, {})
    assert (lim, source, budget) == (777, "explicit", 0)

    # 2) auto_by_budget
    p_auto = _default_params()
    cfg_auto = {"retriever": {"auto_by_budget": True, "latency_budget_ms": 260}}
    lim, source, budget = preview_effective_candidate_limit(p_auto, cfg_auto)
    assert (lim, source, budget) == (2000, "auto_by_budget", 260)

    # 3) config
    p_cfg = _default_params()
    cfg = {"retriever": {"candidate_limit": 3333}}
    lim, source, budget = preview_effective_candidate_limit(p_cfg, cfg)
    assert (lim, source, budget) == (3333, "config", 0)

    # 4) default
    p_def = _default_params()
    lim, source, budget = preview_effective_candidate_limit(p_def, {})
    assert (lim, source, budget) == (4000, "default", 0)
