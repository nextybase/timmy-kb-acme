# ui/chrome.py
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import os
import signal
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Optional, cast

import streamlit as st

from ui.clients_store import get_all as get_clients
from ui.pages.registry import PagePaths
from ui.theme_enhancements import inject_theme_css

from .landing_slug import _request_shutdown as _shutdown  # deterministico
from .utils import clear_active_slug, get_slug, require_active_slug
from .utils.branding import render_brand_header, render_sidebar_brand
from .utils.html import esc_text

# Root repo per branding (favicon/logo)
REPO_ROOT = Path(__file__).resolve().parents[2]


def _on_exit() -> None:
    _shutdown(None)  # compat con firma (_request_shutdown(log))


# ---------- layout ----------
def header(slug: str | None, *, title: str | None = None, subtitle: str | None = None) -> None:
    """
    Header della UI.
    Nota: l'unica chiamata a `st.set_page_config(...)` sta nell'entrypoint.
    Qui iniettiamo solo il CSS brand e rendiamo l'header.
    """
    inject_theme_css()  # CSS enhancement opzionale (idempotente)

    subtitle = subtitle or (f"Cliente: {slug}" if slug else None)
    render_brand_header(
        st_module=st,
        repo_root=REPO_ROOT,
        title=title,
        subtitle=subtitle,
        include_anchor=True,
        show_logo=False,
    )


def sidebar(slug: str | None) -> None:
    """Sidebar con brand, stato cliente e azioni rapide."""

    def _client_display_name(active_slug: Optional[str]) -> str:
        if not active_slug:
            return ""
        for entry in get_clients():
            try:
                if entry.slug.strip().lower() == active_slug.strip().lower():
                    return (entry.nome or "").strip() or active_slug
            except Exception:
                continue
        return active_slug

    entry: Any = getattr(st, "sidebar", None)

    @contextmanager
    def _sidebar_scope(sidebar_obj: Any) -> Iterator[Any]:
        if sidebar_obj and hasattr(sidebar_obj, "__enter__") and hasattr(sidebar_obj, "__exit__"):
            with sidebar_obj:
                yield sidebar_obj
        else:
            yield sidebar_obj or st

    with _sidebar_scope(entry) as panel:
        ui = panel or st

        def _call(method: str, *args: Any, **kwargs: Any) -> Any:
            fn = getattr(ui, method, None)
            if not callable(fn):
                fn = getattr(st, method, None)
            if callable(fn):
                try:
                    return fn(*args, **kwargs)
                except TypeError:
                    if "width" in kwargs:
                        safe_kwargs = dict(kwargs)
                        safe_kwargs.pop("width", None)
                        return fn(*args, **safe_kwargs)
                    raise
                except Exception:
                    return None
            return None

        has_slug = bool(slug)

        render_sidebar_brand(st_module=st, repo_root=REPO_ROOT)

        display_name = esc_text(_client_display_name(slug))
        _call("markdown", f"**Cliente attivo:** {display_name}")
        if not has_slug:
            # Reimposta slug e instrada verso Gestisci cliente (idempotente)
            btn_sel = _call(
                "button",
                "Seleziona cliente",
                key="btn_select_client",
                help="Vai alla pagina Gestisci cliente senza slug attivo.",
                width="stretch",
            )
            if btn_sel:
                try:
                    clear_active_slug(persist=True, update_query=True)
                except Exception:
                    pass
                try:
                    st.switch_page(PagePaths.MANAGE)
                except Exception:
                    pass

        _call("subheader", "Azioni rapide")

        btn = _call(
            "button",
            "Azzera selezione cliente",
            help="Rimuove lo slug attivo e torna alla Home",
            disabled=not has_slug,
            width="stretch",
        )
        if btn:
            clear_active_slug()
            try:
                getattr(st, "rerun", lambda: None)()
            except Exception:
                pass

        # (rimosso) Bottone "Aggiorna Drive" non più previsto dalla guida UI

        # Uscita: shutdown reale del processo Streamlit
        btn_exit = _call(
            "button",
            "Esci",
            key="btn_exit",
            type="primary",
            width="stretch",
        )
        if btn_exit:
            # Pulisci eventuale stato cliente, poi spegni il server
            try:
                clear_active_slug(persist=True, update_query=True)
            except Exception:
                pass
            try:
                st.info("Chiusura in corso…")
            except Exception:
                pass
            try:
                _shutdown(None)
            except Exception:
                try:
                    os.kill(os.getpid(), signal.SIGTERM)
                except Exception:
                    os._exit(0)
            try:
                st.stop()
            except Exception:
                pass


def render_chrome_then_require(
    *, allow_without_slug: bool = False, title: str | None = None, subtitle: str | None = None
) -> str | None:
    """
    Renderizza header + sidebar e ritorna lo slug attivo.

    Args:
        allow_without_slug: se False (default), richiede uno slug valido (blocca la pagina
            come require_active_slug). Se True, non blocca e ritorna lo slug (o None).
    """
    slug = cast(Optional[str], get_slug())
    header(slug, title=title, subtitle=subtitle)
    sidebar(slug)
    if allow_without_slug:
        return slug
    return cast(str, require_active_slug())
