# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from pipeline import ontology


def test_load_entities_returns_mapping() -> None:
    data = ontology.load_entities()
    assert isinstance(data, dict)
    assert "categories" in data


def test_get_all_entities_includes_progetto() -> None:
    entities = ontology.get_all_entities()
    ids = {ent["id"] for ent in entities}
    assert "progetto" in ids
    progetto = next(ent for ent in entities if ent["id"] == "progetto")
    assert progetto["category"] == "operativi"
    assert progetto["document_code"] == "PRJ-"
    assert isinstance(progetto.get("examples"), list)


def test_get_document_code_by_id() -> None:
    assert ontology.get_document_code("progetto") == "PRJ-"
    assert ontology.get_document_code("unknown-entity") is None
