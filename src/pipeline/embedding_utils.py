# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

"""Utility di normalizzazione embeddings (SSoT) e validazione vettori.

Contratto output:
- Dato un input eterogeneo (batch o singolo vettore), restituisce SEMPRE
  un batch come ``list[list[float]]``. I vettori interni possono essere vuoti
  se l'input non contiene elementi numerici validi.

Formati supportati in input (senza dipendenze runtime extra):
- ``list[list[float]]`` (o sottotipi sequence-like)
- ``numpy.ndarray`` 2D o 1D (usando ``.tolist()`` se presente)
- ``list[np.ndarray]``
- singolo vettore come ``deque``/generatore/``list[float]``

Note:
- Non lancia eccezioni su forme "strane"; degrada in modo conservativo
  materializzando liste. Il cast a ``float`` è best-effort (non influenza artefatti/gate/ledger/exit code).
- Usa ``is_numeric_vector`` per verificare se un vettore è utilizzabile
  per calcoli (tutti gli elementi numerici finiti e lunghezza > 0).
"""

import math
from typing import Any, Iterable, List

__all__ = ["normalize_embeddings", "is_numeric_vector"]


def _is_seq_like(x: Any) -> bool:
    return hasattr(x, "__len__") and hasattr(x, "__getitem__") and not isinstance(x, (str, bytes))


def _to_list(x: Any) -> List[float]:
    try:
        base = x.tolist() if hasattr(x, "tolist") else list(x)
    except Exception:
        base = [x]
    try:
        return [float(v) for v in base]
    except Exception:
        # Fallback: non forzare il cast, ma garantisci la lista
        return list(base)


def _iter_floats_safe(seq: Iterable[Any]) -> Iterable[float]:
    for v in seq:
        try:
            fv = float(v)
        except Exception:
            # ignora elementi non numerici
            continue
        if not math.isfinite(fv):
            continue
        yield fv


def is_numeric_vector(vec: Any) -> bool:
    """True se ``vec`` è una sequenza di numeri finiti con len > 0.

    - Accetta sequence-like o iterabili; ignora elementi non numerici/non finiti.
    - Considera non valido se, dopo il filtro, la dimensione è 0.
    """
    try:
        if not _is_seq_like(vec):
            vec = list(vec)
    except Exception:
        return False
    filtered = list(_iter_floats_safe(vec))
    return len(filtered) > 0


def normalize_embeddings(raw: Any) -> List[List[float]]:
    """Normalizza ``raw`` in ``list[list[float]]`` evitando doppi livelli.

    Regole:
    - Se ``raw`` espone ``.tolist()``, usa il risultato come base.
    - Se non è sequence-like ma è iterabile, materializza ``list(raw)``.
    - Determina se ``raw`` è già un batch guardando il primo elemento.
    - Converte ogni vettore interno in ``list[float]`` (usando ``.tolist()`` se presente),
      filtrando elementi non numerici/non finiti.
    """
    try:
        outer = raw.tolist() if hasattr(raw, "tolist") else raw
    except Exception:
        outer = raw

    if not _is_seq_like(outer):
        try:
            outer = list(outer)
        except Exception:
            outer = [outer]

    # Batch vs vettore singolo
    is_batch = False
    try:
        first = outer[0]
    except Exception:
        first = None
    if first is not None:
        is_batch = _is_seq_like(first) or hasattr(first, "tolist")
    if not is_batch:
        outer = [outer]

    # Converte ogni vettore in list[float] filtrando i non numerici
    out: List[List[float]] = []
    for v in outer:
        try:
            base = v.tolist() if hasattr(v, "tolist") else v
        except Exception:
            base = v
        try:
            if not _is_seq_like(base):
                base = list(base)
        except Exception:
            base = [base]
        floats = list(_iter_floats_safe(base))
        out.append(list(floats))
    return out
