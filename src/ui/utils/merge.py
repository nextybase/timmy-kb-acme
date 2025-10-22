# SPDX-License-Identifier: GPL-3.0-or-later
"""Utility di merge profondo per configurazioni UI."""

from __future__ import annotations

from typing import Any, Dict


def deep_merge_dict(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """
    Esegue un merge ricorsivo tra dizionari, preservando le chiavi annidate.
    - Le strutture `dict` vengono fuse profondamente.
    - Ogni altro valore nell'override sostituisce quello base.
    Ritorna un nuovo dict (non muta gli input).
    """
    merged: Dict[str, Any] = dict(base)
    for key, value in override.items():
        base_value = merged.get(key)
        if isinstance(base_value, dict) and isinstance(value, dict):
            merged[key] = deep_merge_dict(base_value, value)
        else:
            merged[key] = value
    return merged
