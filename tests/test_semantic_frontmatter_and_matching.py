# tests/test_semantic_frontmatter_and_matching.py
from __future__ import annotations

from typing import Dict, Set

# Testiamo helper interni (consapevolmente) per coprire le regressioni:
from src.semantic.api import _as_list_str, _guess_tags_for_name, _merge_frontmatter

# ------------------------------ Frontmatter: normalizzazione tag ------------------------------


def test_as_list_str_normalizes_scalar_and_tuple():
    assert _as_list_str(None) == []
    assert _as_list_str("foo") == ["foo"]
    assert _as_list_str(("foo", "bar")) == ["foo", "bar"]
    assert _as_list_str(["a", "a", ""]) == ["a", "a"]  # no dedup qui: è responsabilità del merge
    # conversione di tipi non stringa ma “stampabili”
    assert _as_list_str(123) == ["123"]
    assert _as_list_str({1, 2}) in (["1", "2"], ["2", "1"])  # l’ordine dei set non è garantito


def test_merge_frontmatter_handles_scalar_tuple_and_dedups_sorted():
    meta = {"tags": "foo"}  # scalar → lista
    merged = _merge_frontmatter(meta, title=None, tags=["bar", "foo"])
    assert merged["tags"] == ["bar", "foo"]  # dedup + sort

    meta2 = {"tags": ("z", "a")}
    merged2 = _merge_frontmatter(meta2, title=None, tags=["a", "m"])
    assert merged2["tags"] == ["a", "m", "z"]

    meta3 = {}  # nessun campo tags
    merged3 = _merge_frontmatter(meta3, title="T", tags=["a"])
    assert merged3["title"] == "T"
    assert merged3["tags"] == ["a"]


# ------------------------------ Boundary matching (riduzione falsi positivi)
# ------------------------------


def _vocab() -> Dict[str, Dict[str, Set[str]]]:
    # Dizionario minimamente valido per _guess_tags_for_name:
    # {canonico: {"aliases": {alias1, alias2}}}
    return {
        "ai": {"aliases": {"artificial intelligence"}},
        "finance": {"aliases": set()},
        "data": {"aliases": {"dataset", "data-set"}},
    }


def test_guess_tags_for_name_respects_word_boundaries_basic():
    vocab = _vocab()
    # 'ai' NON deve matchare 'finance' (prima succedeva con substring)
    assert _guess_tags_for_name("compliance.md", vocab) == []
    assert _guess_tags_for_name("finance.md", vocab) == ["finance"]
    # match su confine parola, separatori vari
    hits = _guess_tags_for_name("awesome-ai_overview.md", vocab)
    assert hits == ["ai"]


def test_guess_tags_for_name_handles_compound_and_aliases():
    vocab = _vocab()
    # Alias composti: 'data-set' deve matchare come parola separata
    assert _guess_tags_for_name("building-a-data-set-guide.md", vocab) == ["data"]
    # Nessun match su sottostringa interna (es. 'ai' in 'braided')
    assert _guess_tags_for_name("braided_patterns.md", vocab) == []


def test_guess_tags_for_name_handles_punctuated_terms():
    vocab = {
        "c++": {"aliases": set()},
        "ml/ops": {"aliases": {"ml ops"}},
        "data+": {"aliases": {"data plus"}},
    }
    assert _guess_tags_for_name("intro-to-c++.md", vocab) == ["c++"]
    assert _guess_tags_for_name("guide-ml-ops.md", vocab) == ["ml/ops"]
    assert _guess_tags_for_name("data-plus-overview.md", vocab) == ["data+"]
