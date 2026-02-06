# SPDX-License-Identifier: GPL-3.0-or-later
# tests/test_layout_enricher_parametrized.py
from __future__ import annotations

import pytest

from semantic.layout_enricher import suggest_layout, to_kebab


@pytest.mark.parametrize(
    "vision_text,allowed_prefixes",
    [
        (
            "Strategia e dati: "
            "strategy"
            "governance "
            "strategy"
            "roadmap "
            "strategy"
            "kpi "
            "data"
            "governance "
            "data"
            "dataset "
            "data"
            "quality.",
            {"strategy", "data"},
        ),
        (
            "Processi: "
            "operations"
            "processi "
            "operations"
            "delivery "
            "operations"
            "kpi "
            "data"
            "dataset "
            "data"
            "quality "
            "data"
            "governance.",
            {"operations", "data"},
        ),
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
