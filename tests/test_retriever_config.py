from __future__ import annotations

from src.retriever import (
    QueryParams,
    choose_limit_for_budget,
    with_config_candidate_limit,
    with_config_or_budget,
)


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
