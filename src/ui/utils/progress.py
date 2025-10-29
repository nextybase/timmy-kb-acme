# SPDX-License-Identifier: GPL-3.0-or-later
# src/ui/utils/progress.py
from __future__ import annotations

from typing import Callable, Iterable, TypeVar

from ui.utils.stubs import get_streamlit

T = TypeVar("T")


def run_with_progress(items: Iterable[T], *, label: str, on_each: Callable[[T], None]) -> None:
    """
    Esegue on_each su ogni item mostrando una progress bar resiliente.
    In assenza di runtime Streamlit reale, degrada a no-op visivo.
    """
    st = get_streamlit()
    items_list = list(items)
    total = max(len(items_list), 1)
    pb = getattr(st, "progress", None)
    i = 0
    if callable(pb):
        p = pb(0, text=label)
        for it in items_list:
            on_each(it)
            i += 1
            try:
                p.progress(min(i, total) / total, text=f"{label} ({i}/{total})")
            except Exception:
                pass
        try:
            p.progress(1.0, text=f"{label} (completato)")
        except Exception:
            pass
    else:
        for it in items_list:
            on_each(it)
