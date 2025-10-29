# SPDX-License-Identifier: GPL-3.0-or-later
# src/ui/utils/compat.py
from __future__ import annotations

from typing import Callable

from ui.pages.registry import url_path_for
from ui.utils.stubs import get_streamlit


def nav_to(page_path: str) -> None:
    """
    Naviga verso una pagina Streamlit. Preferisce switch_page(page_path),
    altrimenti imposta ?tab=<url_path> e forza rerun come fallback.
    """
    st = get_streamlit()
    sp = getattr(st, "switch_page", None)
    if callable(sp):
        try:
            sp(page_path)
            return
        except Exception:
            pass
    qp = getattr(st, "query_params", None)
    if isinstance(qp, dict):
        up = url_path_for(page_path)
        if up:
            qp["tab"] = up
            try:
                getattr(st, "rerun", lambda: None)()
            except Exception:
                return


def open_dialog(title: str, render_body: Callable[[], None], *, width: str = "large") -> None:
    """
    Apre un modal se supportato, altrimenti renderizza inline il corpo.
    """
    st = get_streamlit()
    dialog_builder = getattr(st, "dialog", None)
    if callable(dialog_builder):
        opener = dialog_builder(title, width=width)
        runner = opener(render_body)
        if callable(runner):
            runner()
        return
    render_body()  # fallback inline
