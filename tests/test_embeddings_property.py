# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

"""Property/fuzz tests per normalizzazione embeddings e cosine.

Obiettivi:
- normalize_embeddings non deve lanciare su input eterogenei
- i vettori numerici normalizzati rispettano i contratti base di cosine
"""

from collections import deque
from typing import Any, Sequence

import numpy as np
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from hypothesis.extra.numpy import arrays as np_arrays

from timmykb.pipeline.embedding_utils import is_numeric_vector, normalize_embeddings
from timmykb.retriever import cosine


def _gen_like(seq: Sequence[float]) -> Any:
    # Genera formati alternativi per il singolo vettore
    choice = np.random.randint(0, 4)
    if choice == 0:
        return list(seq)
    if choice == 1:
        return np.array(seq)
    if choice == 2:
        return deque(seq)
    # generatore
    return (x for x in seq)


@settings(deadline=None, suppress_health_check=[HealthCheck.filter_too_much], max_examples=60)
@given(
    st.one_of(
        # batch: lista di liste (rettangolare o ragged); non deve esplodere
        st.lists(
            st.lists(st.floats(allow_nan=False, allow_infinity=False), min_size=0, max_size=6),
            min_size=0,
            max_size=4,
        ),
        # singolo vettore in vari formati
        st.lists(st.floats(allow_nan=False, allow_infinity=False), min_size=0, max_size=12).map(_gen_like),
        # ndarray 2D ben formata (usa strategy numpy per evitare ValueError su shape non omogenea)
        st.tuples(st.integers(min_value=0, max_value=3), st.integers(min_value=0, max_value=8)).flatmap(
            lambda hw: np_arrays(dtype=float, shape=hw)
        ),
        # valori "strani" o non numerici
        st.one_of(st.none(), st.integers(), st.text(min_size=0, max_size=10)),
    )
)
def test_normalize_never_raises_and_shapes(raw: Any) -> None:
    out = normalize_embeddings(raw)
    assert isinstance(out, list)
    for v in out:
        assert isinstance(v, list)
        # se numerico e non vuoto, cosine con se stesso ~ 1.0
        if is_numeric_vector(v):
            if all((x == 0.0 for x in v)):
                assert cosine(v, v) == 0.0
            else:
                assert cosine(v, v) == pytest.approx(1.0, rel=1e-6, abs=1e-6)


@settings(deadline=None, max_examples=80)
@given(
    st.lists(st.floats(allow_nan=False, allow_infinity=False), min_size=1, max_size=16),
    st.lists(st.floats(allow_nan=False, allow_infinity=False), min_size=1, max_size=16),
)
def test_cosine_bounds(a: list[float], b: list[float]) -> None:
    # Limita un po' le dimensioni per runtime del test
    s = cosine(a, b)
    assert -1.0 <= s <= 1.0
