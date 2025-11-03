# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

import re

import semantic.api as sapi


def test_term_to_pattern_caching_reduces_compilations():
    # reset cache
    sapi._term_to_pattern.cache_clear()
    info0 = sapi._term_to_pattern.cache_info()

    terms = ["data science", "c++", "ml/ops", "data+"]
    text = "intro to data science and c++ with ml/ops and data+"
    s = text.lower()

    # Prima chiamata: una miss per ciascun termine unico
    for t in terms:
        pat = sapi._term_to_pattern(t)
        assert isinstance(pat, re.Pattern)
        assert pat.search(s)

    info1 = sapi._term_to_pattern.cache_info()
    assert info1.misses == info0.misses + len(terms)

    # Chiamate ripetute: dovrebbero produrre solo hit
    for _ in range(20):
        for t in terms:
            sapi._term_to_pattern(t)

    info2 = sapi._term_to_pattern.cache_info()
    # Almeno (20 * len(terms)) hit aggiuntivi
    assert info2.hits >= info1.hits + 20 * len(terms)


def test_term_to_pattern_cache_clear_and_results_stable():
    sapi._term_to_pattern.cache_clear()
    infoA = sapi._term_to_pattern.cache_info()

    t = "machine learning"
    s = "intro to machine    learning basics".lower()

    # Prima invocazione: miss
    p1 = sapi._term_to_pattern(t)
    assert p1.search(s)
    infoB = sapi._term_to_pattern.cache_info()
    assert infoB.misses == infoA.misses + 1

    # Seconda invocazione: hit
    p2 = sapi._term_to_pattern(t)
    assert p2.search(s)
    infoC = sapi._term_to_pattern.cache_info()
    assert infoC.hits == infoB.hits + 1

    # Invalida cache e verifica che si registri una nuova miss
    sapi._term_to_pattern.cache_clear()
    infoD = sapi._term_to_pattern.cache_info()
    p3 = sapi._term_to_pattern(t)
    assert p3.search(s)
    infoE = sapi._term_to_pattern.cache_info()
    assert infoE.misses == infoD.misses + 1
