# SPDX-License-Identifier: GPL-3.0-or-later
# ui/utils/status.py
from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator

try:
    import streamlit as st
except Exception:  # pragma: no cover
    st = None


@contextmanager
def status_guard(label: str, *, error_label: str | None = None, **kwargs: Any) -> Iterator[Any]:
    """
    Wrapper unico per st.status che aggiorna automaticamente il messaggio di errore,
    con fallback stub quando Streamlit o st.status non sono disponibili.
    """
    clean_label = label.rstrip(" .…")
    error_prefix = error_label or (f"Errore durante {clean_label}" if clean_label else "Errore")
    status_cm = getattr(st, "status", None) if st is not None else None

    if not callable(status_cm):

        @contextmanager
        def _noop_cm(*_args: Any, **_kwargs: Any) -> Iterator[Any]:
            class _StatusStub:
                def update(self, *args: Any, **kwargs: Any) -> None:
                    return None

            yield _StatusStub()

        status_cm = _noop_cm

    with status_cm(label, **kwargs) as status:
        try:
            yield status
        except Exception as exc:
            if status is not None and hasattr(status, "update"):
                status.update(label=f"{error_prefix}: {exc}", state="error")
            raise
