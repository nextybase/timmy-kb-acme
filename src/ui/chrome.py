# ui/chrome.py
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import os
import signal
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Iterator, Optional, cast

import streamlit as st

from pipeline.logging_utils import get_structured_logger
from ui.clients_store import get_all as get_clients
from ui.errors import to_user_message
from ui.pages.registry import PagePaths
from ui.theme_enhancements import inject_theme_css
from ui.utils.control_plane import ensure_runtime_strict

from .landing_slug import _request_shutdown as _shutdown  # deterministico
from .utils import clear_active_slug, get_slug, require_active_slug
from .utils.branding import render_brand_header, render_sidebar_brand
from .utils.html import esc_text

_LOGGER = get_structured_logger("ui.chrome")


def _halt_ui(action: str, exc: Exception, *, slug: str | None = None) -> None:
    extra: dict[str, object] = {"action": action}
    if slug:
        extra["slug"] = slug
    _LOGGER.exception("ui.chrome.action_failed", extra=extra, exc_info=exc)
    title, body, caption = to_user_message(exc)
    st.error(f"{title}: {body}")
    if caption:
        st.caption(caption)
    st.stop()


def _run_action(action: str, callback: Callable[[], Any], *, slug: str | None = None) -> Any:
    try:
        return callback()
    except Exception as exc:
        _halt_ui(action, exc, slug=slug)


# Root repo per branding (favicon/logo)
REPO_ROOT = Path(__file__).resolve().parents[2]


def _on_exit() -> None:
    _shutdown(None)  # firma compatibile con _request_shutdown(log)


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
                except TypeError as exc:
                    _halt_ui(f"sidebar.{method}.type_error", exc, slug=slug)
                except Exception as exc:
                    _halt_ui(f"sidebar.{method}", exc, slug=slug)
            _halt_ui(f"sidebar.{method}.missing", RuntimeError(f"sidebar method {method} missing"), slug=slug)

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
                _run_action(
                    "clear_active_slug_manage",
                    lambda: clear_active_slug(persist=True, update_query=True),
                    slug=slug,
                )
                _run_action(
                    "switch_to_manage",
                    lambda: st.switch_page(PagePaths.MANAGE),
                    slug=slug,
                )

        _call("subheader", "Azioni rapide")

        btn = _call(
            "button",
            "Azzera selezione cliente",
            help="Rimuove lo slug attivo e torna alla Home",
            disabled=not has_slug,
            width="stretch",
        )
        if btn:
            _run_action("clear_active_slug_home", clear_active_slug, slug=slug)
            _run_action("rerun_page", lambda: getattr(st, "rerun")(), slug=slug)

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
            _run_action(
                "clear_active_slug_exit",
                lambda: clear_active_slug(persist=True, update_query=True),
                slug=slug,
            )
            _run_action("shutdown_notice", lambda: st.info("Chiusura in corso…"), slug=slug)
            try:
                _shutdown(None)
            except Exception as exc:
                _LOGGER.exception(
                    "ui.chrome.shutdown_failed",
                    extra={"slug": slug or "<none>"},
                    exc_info=exc,
                )
                try:
                    os.kill(os.getpid(), signal.SIGTERM)
                except Exception as kill_exc:
                    _LOGGER.exception(
                        "ui.chrome.shutdown_kill_failed",
                        extra={"slug": slug or "<none>"},
                        exc_info=kill_exc,
                    )
                    os._exit(0)
                _halt_ui("shutdown", exc, slug=slug)
            _run_action("stop_streamlit", lambda: st.stop(), slug=slug)


def render_chrome_then_require(
    *,
    allow_without_slug: bool = False,
    title: str | None = None,
    subtitle: str | None = None,
    strict_runtime: bool = True,
    control_plane_note: str | None = None,
) -> str | None:
    """
    Renderizza header + sidebar e ritorna lo slug attivo.

    Args:
        allow_without_slug: se False (default), richiede uno slug valido (blocca la pagina
            come require_active_slug). Se True, non blocca e ritorna lo slug (o None).
    """
    if strict_runtime:
        ensure_runtime_strict()
    slug = cast(Optional[str], get_slug())
    header(slug, title=title, subtitle=subtitle)
    sidebar(slug)
    if control_plane_note:
        st.info(control_plane_note)
    if allow_without_slug:
        return slug
    return cast(str, require_active_slug())
