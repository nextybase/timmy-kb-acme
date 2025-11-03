# SPDX-License-Identifier: GPL-3.0-only
# tests/test_layout_enricher_parametrized.py
from __future__ import annotations

import pytest

from timmykb.semantic.layout_enricher import suggest_layout, to_kebab


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Analisi Dati_AI!", "analisi-dati-ai"),
        ("  STRATEGIA__GO-TO Market  ", "strategia-go-to-market"),
        ("Operazioni & Processi", "operazioni-processi"),
    ],
)
def test_to_kebab_cases(raw, expected):
    assert to_kebab(raw) == expected


@pytest.mark.parametrize(
    "vision_text,allowed_prefixes",
    [
        ("Strategia e dati: governance e KPI.", {"strategy", "data"}),
        ("Ops: processi e delivery; dati e dataset.", {"operations", "data"}),
    ],
)
def test_suggest_layout_respects_allowed_prefixes(vision_text, allowed_prefixes):
    base_yaml = {"strategy": {"overview": {}}, "data": {"datasets": {}}, "operations": {}}
    constraints = {
        "max_depth": 3,
        "max_nodes": 20,
        "allowed_prefixes": sorted(list({"strategy", "data", "operations"})),
        "semantic_mapping": {
            "strategy": ["strategia"],
            "data": ["dati", "dataset"],
            "operations": ["ops", "processi"],
        },
    }
    proposal = suggest_layout(base_yaml, vision_text, constraints)
    assert isinstance(proposal, dict) and proposal
    for top in proposal.keys():
        assert top.split("-")[0] in allowed_prefixes
