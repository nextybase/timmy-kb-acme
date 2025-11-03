# SPDX-License-Identifier: GPL-3.0-only
# tests/test_retriever_config.py
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from timmykb.retriever import QueryParams, choose_limit_for_budget, with_config_candidate_limit, with_config_or_budget


def test_with_config_candidate_limit_precedence() -> None:
    # default params -> prende dal config
    p = QueryParams(db_path=None, project_slug="p", scope="s", query="q")
    cfg = {"retriever": {"candidate_limit": 2000}}
    out = with_config_candidate_limit(p, cfg)
    assert out.candidate_limit == 2000
    # valore esplicito diverso dal default -> non sovrascrivere
    p2 = QueryParams(db_path=None, project_slug="p", scope="s", query="q", candidate_limit=1234)
    out2 = with_config_candidate_limit(p2, cfg)
    assert out2.candidate_limit == 1234


def test_choose_limit_for_budget_mapping() -> None:
    assert choose_limit_for_budget(0) == 4000
    assert choose_limit_for_budget(150) == 1000
    assert choose_limit_for_budget(250) == 2000
    assert choose_limit_for_budget(350) == 4000
    assert choose_limit_for_budget(800) == 8000


def test_with_config_or_budget_auto() -> None:
    p = QueryParams(db_path=None, project_slug="p", scope="s", query="q")
    cfg = {"retriever": {"auto_by_budget": True, "latency_budget_ms": 250, "candidate_limit": 9999}}
    out = with_config_or_budget(p, cfg)
    assert out.candidate_limit == 2000  # budget prioritario su candidate_limit


# --- APPEND --- Proprietà di monotonicità e casi addizionali di precedence ---


def test_choose_limit_for_budget_zero_budget_returns_default() -> None:
    # Caso sentinella: 0 ms => usa il default del sistema, non parte della monotonicità
    assert choose_limit_for_budget(0) == 4000


def test_choose_limit_for_budget_is_monotonic_for_positive_budgets() -> None:
    # Monotonicità per budget strettamente positivi
    budgets = list(range(1, 1001, 5))
    limits = [choose_limit_for_budget(b) for b in budgets]
    assert all(
        curr >= prev for prev, curr in zip(limits, limits[1:], strict=False)
    ), "choose_limit_for_budget deve essere non decrescente per budget > 0"


def _typed_params(**over: Any) -> QueryParams:
    """
    Costruisce QueryParams forzando i tipi corretti per evitare warning Pylance:
    - db_path: Path|None
    - project_slug/scope/query: str
    - k/candidate_limit: int
    Ignora eventuali chiavi extra.
    """
    base: Dict[str, Any] = dict(
        db_path=None,
        project_slug="p",
        scope="s",
        query="q",
        k=8,
        candidate_limit=4000,
    )
    base.update(over or {})

    dbp = base.get("db_path", None)
    db_path = dbp if isinstance(dbp, Path) or dbp is None else None

    def _as_str(x: Any, default: str) -> str:
        return default if x is None else str(x)

    def _as_int(x: Any, default: int) -> int:
        try:
            return int(x)
        except Exception:
            return default

    return QueryParams(
        db_path=db_path,
        project_slug=_as_str(base.get("project_slug"), "p"),
        scope=_as_str(base.get("scope"), "s"),
        query=_as_str(base.get("query"), "q"),
        k=_as_int(base.get("k"), 8),
        candidate_limit=_as_int(base.get("candidate_limit"), 4000),
    )


def test_with_config_or_budget_explicit_param_wins() -> None:
    # esplicito diverso dal default → deve prevalere su auto/config
    p = _typed_params(candidate_limit=1234)
    cfg = {
        "retriever": {
            "auto_by_budget": True,
            "latency_budget_ms": 250,
            "candidate_limit": "6000",
        }
    }
    out = with_config_or_budget(p, cfg)
    assert out.candidate_limit == 1234


def test_with_config_or_budget_config_value() -> None:
    # default → prende il valore da config (anche se stringa)
    p = _typed_params()
    cfg = {"retriever": {"candidate_limit": "6000"}}
    out = with_config_or_budget(p, cfg)
    assert out.candidate_limit == 6000


def test_with_config_or_budget_fallback_default() -> None:
    # default senza config → resta il default del dataclass
    p = _typed_params()
    out = with_config_or_budget(p, None)
    assert out.candidate_limit == QueryParams.__dataclass_fields__["candidate_limit"].default  # type: ignore[index]
