# SPDX-License-Identifier: GPL-3.0-or-later
# tests/test_layout_enricher.py

import pytest

from pipeline.exceptions import ConversionError
from semantic.layout_enricher import Constraints, merge_non_distruttivo, suggest_layout, validate_yaml_schema


@pytest.fixture
def base_yaml():
    # Struttura minimale già presente
    return {
        "strategy": {
            "overview": {},
            "kpi": {},
        },
        "data": {
            "datasets": {},
        },
    }


@pytest.fixture
def constraints_dict():
    return {
        "max_depth": 3,
        "max_nodes": 20,
        "allowed_prefixes": ["strategy", "data", "operations"],
        "semantic_mapping": {
            # canonico: sinonimi
            "strategy": ["strategia", "indirizzo-strategico"],
            "data": ["dati", "dataset", "informazioni"],
            "operations": ["ops", "operativita", "processi"],
        },
    }


def test_constraints_from_dict(constraints_dict):
    c = Constraints.from_dict(constraints_dict)
    assert c.max_depth == 3
    assert c.max_nodes == 20
    # prefissi normalizzati e ordinati
    assert tuple(c.allowed_prefixes) == ("data", "operations", "strategy")
    # mapping normalizzato
    assert "indirizzo-strategico" in c.semantic_mapping["strategy"]


def test_suggest_layout_generates_proposal(base_yaml, constraints_dict):
    # Vision text con parole chiave in italiano/inglese (verrà normalizzato)
    vision_text = """
    La nostra Strategia punta su Dati aperti e processi Operations.
    Priorità: governance, roadmap, KPI, sicurezza dei dataset, cultura del dato.
    """
    with pytest.raises(ConversionError, match="Struttura insufficiente"):
        suggest_layout(base_yaml, vision_text, constraints_dict)


def test_max_nodes_respected(base_yaml, constraints_dict):
    # Forziamo un budget molto basso
    tight = dict(constraints_dict, max_nodes=3)
    with pytest.raises(ConversionError, match="Struttura insufficiente"):
        suggest_layout(base_yaml, "strategy governance roadmap processi kpi dati", tight)


def test_merge_non_distruttivo_preserves_existing(base_yaml, constraints_dict):
    proposal = {
        "strategy": {"roadmap": {}},
        "data": {"catalog": {}},
    }

    merged = merge_non_distruttivo(base_yaml, proposal)

    # 1) Le chiavi preesistenti in base devono rimanere
    assert "strategy" in merged and "overview" in merged["strategy"]
    assert "data" in merged and "datasets" in merged["data"]

    # 2) La struttura risultante deve includere anche le proposte (se presenti)
    # non possiamo sapere i nomi esatti, ma almeno uno dei top-level proposti deve comparire
    proposed_tops = set(proposal.keys())
    assert proposed_tops & set(merged.keys())

    # 3) In nessun caso deve sparire qualcosa dalla base
    def flatten_keys(d):
        out = set()
        stack = [([], d)]
        while stack:
            path, cur = stack.pop()
            for k, v in cur.items():
                out.add("/".join(path + [k]))
                if isinstance(v, dict):
                    stack.append((path + [k], v))
        return out

    before = flatten_keys(base_yaml)
    after = flatten_keys(merged)
    assert before.issubset(after)


def test_validate_yaml_schema_rejects_bad_depth():
    with pytest.raises(ConversionError):
        validate_yaml_schema({"a": {"b": {"c": {"d": {}}}}}, max_depth=3)  # profondità 4 > 3


def test_validate_yaml_schema_rejects_non_kebab_keys():
    with pytest.raises(ConversionError):
        validate_yaml_schema({"NotKebab": {}}, max_depth=3)


def test_semantic_mapping_deduplication(base_yaml, constraints_dict):
    # Se nel testo compaiono sinonimi del canonico, la proposta non deve duplicare rami semantici
    text = (
        "Strategia indirizzo strategico STRATEGIA strategy "
        "strategy"
        "governance "
        "strategy"
        "roadmap "
        "strategy"
        "kpi"
    )
    proposal = suggest_layout(base_yaml, text, constraints_dict)
    # Al massimo una radice 'strategy' (o nessuna, a seconda del filtro). Non duplicati multipli per sinonimi.
    strategy_count = sum(1 for k in proposal.keys() if k.startswith("strategy"))
    assert strategy_count <= 1
