# SPDX-License-Identifier: GPL-3.0-or-later
# src/ui/utils/progress.py
from __future__ import annotations

from typing import Callable, Iterable, TypeVar

from ui.utils.streamlit_baseline import require_streamlit_feature
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
    pb = require_streamlit_feature(st, "progress")
    p = pb(0, text=label)
    i = 0
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
