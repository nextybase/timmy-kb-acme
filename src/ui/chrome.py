# ui/chrome.py
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Optional, cast

import streamlit as st

from pipeline.yaml_utils import yaml_read
from ui.landing_slug import _request_shutdown as _shutdown  # deterministico
from ui.services.drive import invalidate_drive_index
from ui.theme.css import inject_theme_css
from ui.utils import clear_active_slug, get_slug, require_active_slug
from ui.utils.branding import render_brand_header, render_sidebar_brand
from ui.utils.html import esc_text

# Root repo per branding (favicon/logo)
REPO_ROOT = Path(__file__).resolve().parents[2]


# ---------- helpers ----------
def _on_dummy_kb() -> None:
    """Mostra istruzioni per generare la Dummy KB via CLI (nessun side-effect dalla UI)."""
    slug = get_slug() or "dummy"
    st.info(
        f"Esegui da terminale:\n\n`py src/tools/gen_dummy_kb.py --slug {slug}`\n\n"
        "Questa azione può richiedere risorse/tempo: per questo si esegue solo via CLI."
    )


def _on_exit() -> None:
    _shutdown(None)  # compat con firma (_request_shutdown(log))


# ---------- layout ----------
def header(slug: str | None) -> None:
    """
    Header della UI.
    Nota: l'unica chiamata a `st.set_page_config(...)` sta nell'entrypoint.
    Qui iniettiamo solo il CSS brand e rendiamo l'header.
    """
    inject_theme_css(st)  # CSS brand early-inject (tema gestito nativamente)

    subtitle = f"Cliente: {slug}" if slug else "Nuovo cliente"
    render_brand_header(
        st_module=st,
        repo_root=REPO_ROOT,
        subtitle=subtitle,
        include_anchor=True,
        show_logo=False,
    )


def sidebar(slug: str | None) -> None:
    """Sidebar con brand, stato cliente e azioni rapide."""

    def _repo_root() -> Path:
        return Path(__file__).resolve().parents[2]

    def _clients_db_path() -> Path:
        return _repo_root() / "clients_db" / "clients.yaml"

    def _client_display_name(active_slug: Optional[str]) -> str:
        if not active_slug:
            return "—"
        try:
            db_path = _clients_db_path()
            if db_path.exists():
                data = yaml_read(db_path.parent, db_path)
                if isinstance(data, list):
                    records = data
                elif isinstance(data, dict):
                    records = [{**(value or {}), "slug": key} for key, value in data.items()]
                else:
                    records = []
                for record in records:
                    if (record or {}).get("slug", "").strip().lower() == active_slug.strip().lower():
                        name = (record or {}).get("nome", "") or ""
                        return name.strip() or active_slug
        except Exception:
            pass
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
                return fn(*args, **kwargs)
            return None

        has_slug = bool(slug)

        render_sidebar_brand(st_module=st, repo_root=REPO_ROOT)

        display_name = esc_text(_client_display_name(slug))
        _call(
            "html",
            f"""
            <div style="font-size:1.05rem;font-weight:700;margin:0 0 .5rem 0;">
              Cliente attivo: <span style="font-weight:800">{display_name}</span>
            </div>
            """,
        )
        if not has_slug:
            _call(
                "html",
                """
                <a href="/manage" target="_self"
                   style="display:block;width:100%;text-align:center;
                          padding:.55rem .9rem;border-radius:.6rem;
                          background:#0f62fe;color:#fff;text-decoration:none;
                          box-shadow:0 1px 2px rgba(0,0,0,.08);">
                   Seleziona cliente
                </a>
                """,
            )

        _call("subheader", "Azioni rapide")

        _call(
            "link_button",
            "Guida UI",
            url="https://github.com/nextybase/timmy-kb-acme/blob/main/docs/guida_ui.md",
            width="stretch",
        )

        btn = _call(
            "button",
            "Aggiorna Drive",
            key="btn_drive_refresh",
            help="Richiede un cliente selezionato",
            disabled=not has_slug,
            width="stretch",
        )
        if btn:
            invalidate_drive_index(slug)
            getattr(st, "toast", lambda *_a, **_k: None)("Cache Drive aggiornata.")

        btn = _call(
            "button",
            "Dummy KB",
            key="btn_dummy",
            disabled=not has_slug,
            help="Genera un dataset demo per il cliente corrente",
            width="stretch",
        )
        if btn:
            _on_dummy_kb()

        btn = _call(
            "button",
            "Esci",
            key="btn_exit",
            type="primary",
            width="stretch",
        )
        if btn:
            _on_exit()

        _call("markdown", "---")
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


def render_chrome_then_require(*, allow_without_slug: bool = False) -> str | None:
    """
    Renderizza header + sidebar e ritorna lo slug attivo.

    Args:
        allow_without_slug: se False (default), richiede uno slug valido (blocca la pagina
            come require_active_slug). Se True, non blocca e ritorna lo slug (o None).
    """
    slug = cast(Optional[str], get_slug())
    header(slug)
    sidebar(slug)
    if allow_without_slug:
        return slug
    return cast(str, require_active_slug())
