# SPDX-License-Identifier: GPL-3.0-only
import logging

import pytest

import timmykb.retriever as retriever
from timmykb.retriever import QueryParams, with_config_or_budget


def test_with_config_or_budget_clamps_candidate_limit(
    caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    params = QueryParams(db_path=None, project_slug="acme", scope="kb", query="hello")
    config = {"retriever": {"candidate_limit": 6001}}

    # isola i log ed evita chiamate reali a fetch_candidates se il test dovesse evolvere
    caplog.set_level(logging.WARNING)
    monkeypatch.setattr(retriever, "LOGGER", retriever.get_structured_logger("timmykb.retriever.test"))

    effective = with_config_or_budget(params, config)

    assert effective.candidate_limit == 5000
    assert any("limit.clamped" in record.message for record in caplog.records), caplog.text
