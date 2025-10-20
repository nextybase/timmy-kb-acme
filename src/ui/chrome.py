# ui/chrome.py
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import os
import shlex
import signal
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Optional, cast

import streamlit as st

from pipeline.context import validate_slug
from pipeline.yaml_utils import yaml_read
from ui.landing_slug import _request_shutdown as _shutdown  # deterministico
from ui.theme.css import inject_theme_css
from ui.utils import clear_active_slug, get_slug, require_active_slug
from ui.utils.branding import render_brand_header, render_sidebar_brand
from ui.utils.html import esc_text

# Root repo per branding (favicon/logo)
REPO_ROOT = Path(__file__).resolve().parents[2]


# ---------- helpers ----------
def _on_dummy_kb() -> None:
    """Esegue lo script CLI per generare la Dummy KB e mostra log/output."""
    slug = (get_slug() or "dummy").strip().lower() or "dummy"
    try:
        validate_slug(slug)
    except Exception as exc:
        st.error(f"Slug non valido: {exc}")
        return

    script = (REPO_ROOT / "src" / "tools" / "gen_dummy_kb.py").resolve()
    if not script.exists():
        st.error(f"Script CLI non trovato: {script}")
        return

    cmd = [sys.executable, str(script), "--slug", slug]

    with st.status(f"Genero dataset dummy per '{slug}'…", expanded=True) as status_widget:
        st.code(" ".join(shlex.quote(token) for token in cmd), language="bash")
        try:
            result = subprocess.run(  # noqa: S603 - slug sanificato, shell disabilitata
                cmd,
                capture_output=True,
                text=True,
                check=False,
            )
        except Exception as exc:
            status_widget.update(label="Errore di esecuzione CLI", state="error")
            st.error(f"Impossibile avviare lo script: {exc}")
            return

        if result.stdout:
            with st.expander("Output CLI", expanded=False):
                st.text(result.stdout)
        if result.stderr:
            with st.expander("Errori CLI", expanded=False):
                st.text(result.stderr)

        if result.returncode == 0:
            status_widget.update(label="Dummy generato correttamente.", state="complete")
            st.toast("Dataset dummy creato. Verifica clients_db/output per i dettagli.")
        else:
            status_widget.update(label=f"CLI terminata con codice {result.returncode}", state="error")
            st.error("La generazione della Dummy KB non è andata a buon fine.")


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
            return ""
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
                    getattr(st, "switch_page", lambda *_args, **_kwargs: None)("src/ui/pages/manage.py")
                except Exception:
                    try:
                        qp = getattr(st, "query_params", {})
                        try:
                            if isinstance(qp, dict):
                                qp.pop("slug", None)
                                qp["tab"] = "manage"
                        except Exception:
                            pass
                        getattr(st, "rerun", lambda: None)()
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

        btn = _call(
            "button",
            "Genera Dummy",
            key="btn_dummy",
            disabled=False,  # sempre attivo anche senza slug
            help="Genera un workspace demo completo (CLI, output/timmy-kb-<slug>)",
            width="stretch",
        )
        if btn:
            _on_dummy_kb()

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

        _call("divider")
        btn_help = _call(
            "button",
            "Guida UI",
            key="btn_help_ui",
            type="secondary",
            width="stretch",
            help="Apri la guida dell'interfaccia nella stessa scheda.",
        )
        if btn_help:
            try:
                getattr(st, "switch_page", lambda *_args, **_kwargs: None)("src/ui/pages/guida_ui.py")
            except Exception:
                try:
                    qp = getattr(st, "query_params", {})
                    if isinstance(qp, dict):
                        qp["tab"] = "guida"
                except Exception:
                    pass
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
