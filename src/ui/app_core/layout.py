# src/ui/app_core/layout.py
# SPDX-License-Identifier: GPL-3.0-or-later
"""Helper di layout Streamlit per header e sidebar (routing Page/navigation)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional, Protocol

__all__ = [
    "render_client_header",
    "render_sidebar_branding",
    "render_sidebar_quick_actions",
    "render_sidebar_skiplink_and_quicknav",
]


class ActionCallback(Protocol):
    def __call__(self) -> None: ...


def render_client_header(
    *,
    st_module: Any,
    repo_root: Path,
    slug: Optional[str],
    state: Optional[str] = None,
) -> None:
    """
    Header principale della pagina.

    Args:
        st_module: modulo Streamlit (passa `st`).
        repo_root: root del repository (firma allineata agli entrypoint UI).
        slug: identificativo cliente corrente (se presente).
        state: eventuale stato/phase normalizzato (se presente).
    """
    del repo_root  # parametro non usato qui, mantenuto per compatibilità

    # Ancorina sicura per skiplink
    try:
        st_module.html("<a id='top'></a>")
    except Exception:
        pass

    st_module.title("Timmy-KB - Onboarding")

    parts: list[str] = []
    if slug:
        parts.append(f"Cliente: {slug}")
    if state:
        parts.append(f"Stato: {state}")
    if parts:
        st_module.caption(" · ".join(parts))


def render_sidebar_branding(
    *,
    st_module: Any,
    repo_root: Path,
) -> None:
    """
    Sezione "branding" nella sidebar. Mantiene un profilo minimale e robusto.
    """
    del repo_root  # parametro riservato per uniformità delle firme

    with st_module.sidebar:
        st_module.subheader("Onboarding")
        st_module.text("Interfaccia di gestione Timmy-KB")
        st_module.divider()


def render_sidebar_quick_actions(
    *,
    st_module: Any,
    slug: Optional[str],
    refresh_callback: Optional[ActionCallback] = None,
    generate_dummy_callback: Optional[ActionCallback] = None,
    request_shutdown_callback: Optional[ActionCallback] = None,
    logger: Optional[Any] = None,
) -> None:
    """
    Quick actions standard nella sidebar.
    Le callback sono opzionali; se presenti, vengono invocate con gestione errori.
    """

    def _safe_call(cb: Optional[ActionCallback], label: str) -> None:
        if cb is None:
            st_module.sidebar.info(f"{label}: non disponibile")
            return
        try:
            cb()
            try:
                st_module.toast(f"{label}: completata")
            except Exception:
                pass
            if logger:
                logger.info("ui.sidebar.action_done", extra={"action": label, "slug": slug})
        except Exception as exc:  # pragma: no cover
            if logger:
                logger.exception("ui.sidebar.action_failed", extra={"action": label, "slug": slug, "error": str(exc)})
            st_module.sidebar.error(f"{label}: errore: {exc}")

    with st_module.sidebar:
        st_module.subheader("Azioni rapide")

        c2, c3 = st_module.columns(2)
        with c2:
            if st_module.button("Dummy KB", key="qa_dummy"):
                _safe_call(generate_dummy_callback, "Dummy KB")
        with c3:
            if st_module.button("Esci", key="qa_exit"):
                _safe_call(request_shutdown_callback, "Esci")

        st_module.divider()


def render_sidebar_skiplink_and_quicknav(*, st_module: Any) -> None:
    """Utility di accessibilità e quick-nav senza HTML personalizzato."""
    with st_module.sidebar:
        st_module.subheader("Navigazione")
        # Skiplink sicuro verso l'ancora in header
        try:
            st_module.html("<a href='#top'>Vai al contenuto</a>")
        except Exception:
            st_module.write("[Vai al contenuto](#top)")
