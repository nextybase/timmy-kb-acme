# SPDX-License-Identifier: GPL-3.0-or-later
# src/ui/imports.py
from __future__ import annotations

import importlib
from typing import Any, Optional

from ui.utils.stubs import get_streamlit as _stub_streamlit


def import_first(*module_names: str) -> Any:
    """
    Importa e restituisce il PRIMO modulo disponibile nella lista.
    Alza ImportError se nessuno è importabile (propagando l'ultima eccezione).
    """
    last_err: Optional[BaseException] = None
    for name in module_names:
        try:
            return importlib.import_module(name)
        except BaseException as e:  # noqa: BLE001
            last_err = e
            continue
    raise ImportError(f"Impossibile importare nessuno tra: {', '.join(module_names)}") from last_err


def getattr_if_callable(module: Any, name: str) -> Any | None:
    """getattr con filtro: restituisce l'attributo solo se callabile, altrimenti None."""
    obj = getattr(module, name, None)
    return obj if callable(obj) else None


def get_streamlit() -> Any:
    """Restituisce il modulo streamlit oppure uno stub import-safe."""
    try:
        import streamlit as st

        return st
    except Exception:
        return _stub_streamlit()
