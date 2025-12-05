# SPDX-License-Identifier: GPL-3.0-or-later
"""Utility di merge profondo per configurazioni UI."""

from __future__ import annotations

from typing import Mapping, MutableMapping, TypeVar, cast

KT = TypeVar("KT")
VT = TypeVar("VT")


def deep_merge_dict(base: Mapping[KT, VT], override: Mapping[KT, VT]) -> dict[KT, VT]:
    """
    Esegue un merge ricorsivo tra dizionari, preservando le chiavi annidate.
    - Le strutture `dict`/`Mapping` vengono fuse profondamente.
    - Ogni altro valore nell'override sostituisce quello base.
    Ritorna un nuovo dict (non muta gli input).
    """
    merged: dict[KT, VT] = dict(base)
    for key, value in override.items():
        base_value = merged.get(key)
        if isinstance(base_value, MutableMapping) and isinstance(value, MutableMapping):
            merged[key] = cast(
                VT,
                deep_merge_dict(
                    cast(Mapping[KT, VT], base_value),
                    cast(Mapping[KT, VT], value),
                ),
            )
        else:
            merged[key] = value
    return merged
