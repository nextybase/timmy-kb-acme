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
from ui.clients_store import get_all as get_clients
from ui.manage import cleanup as cleanup_component
from ui.pages.registry import PagePaths
from ui.theme_enhancements import inject_theme_css

try:  # cleanup opzionale
    from tools.clean_client_workspace import perform_cleanup as _perform_cleanup
except Exception:  # pragma: no cover
    _perform_cleanup = None
from .landing_slug import _request_shutdown as _shutdown  # deterministico
from .utils import clear_active_slug, get_slug, require_active_slug
from .utils.branding import render_brand_header, render_sidebar_brand
from .utils.html import esc_text

# Root repo per branding (favicon/logo)
REPO_ROOT = Path(__file__).resolve().parents[2]


# ---------- helpers ----------
def _on_dummy_kb() -> None:
    """Apre un modal con opzioni; su 'Prosegui' esegue la CLI e mostra log/output nel modal."""
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

    def _cleanup_dummy(slug: str, *, client_name: str, status_label: str) -> tuple[int | None, Exception | None]:
        run_cleanup = cleanup_component.resolve_run_cleanup()
        perform_cleanup = _perform_cleanup or cleanup_component.resolve_perform_cleanup()
        with st.status(status_label, expanded=True) as status_widget:
            code: int | None = None
            runner_error: Exception | None = None
            try:
                if callable(perform_cleanup):
                    results = perform_cleanup(slug, client_name=client_name)
                    code = int(results.get("exit_code", 1)) if isinstance(results, dict) else 1
                elif callable(run_cleanup):
                    code = int(run_cleanup(slug, True))
                else:
                    raise RuntimeError("Funzioni cleanup non disponibili")
            except Exception as exc:  # noqa: BLE001
                runner_error = exc

            if runner_error is not None:
                status_widget.update(label="Pulizia fallita", state="error")
                st.error(f"Errore durante il cleanup: {runner_error}")
                return None, runner_error
            if code is None:
                status_widget.update(label="Risultato non disponibile", state="error")
                st.error("Risultato della cancellazione non disponibile.")
                return None, None
            if code == 0:
                status_widget.update(label="Pulizia completata", state="complete")
                st.success(f"Workspace dummy '{slug}' eliminato (locale + Drive).")
            elif code == 3:
                status_widget.update(label="Pulizia parziale (Drive non eliminato)", state="error")
                st.error("Workspace locale e DB rimossi ma Drive non eliminato per permessi/driver.")
            elif code == 4:
                status_widget.update(label="Rimozione locale incompleta", state="error")
                st.error("Rimozione locale incompleta: verifica file bloccati e riprova.")
            else:
                status_widget.update(label="Completato con avvisi", state="error")
                st.error("Operazione completata con avvisi o errori parziali.")

            return code, None

    def _run_and_render(cmd: list[str]) -> None:
        st.caption("Esecuzione comando:")
        st.code(" ".join(shlex.quote(t) for t in cmd), language="bash")
        timeout_seconds = 120
        with st.status(f"Genero dataset dummy per '{slug}'", expanded=True) as status_widget:
            try:
                result = subprocess.run(  # noqa: S603 - slug sanificato, shell disabilitata
                    cmd,
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=timeout_seconds,
                )
            except subprocess.TimeoutExpired:
                status_widget.update(label="CLI in timeout (120s)", state="error")
                st.error(
                    "Vision non ha completato entro 120 secondi. Interrompo senza fallback automatico. "
                    "Riprova con l'opzione esplicita '--no-vision' se vuoi saltare la Vision."
                )
                return
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
                st.success("Operazione completata.")
            else:
                status_widget.update(label=f"CLI terminata con codice {result.returncode}", state="error")
                st.error("La generazione della Dummy KB non e' andata a buon fine.")

        st.divider()
        st.button("Chiudi", type="secondary")

    def _render_modal_body() -> None:
        st.subheader("Opzioni generazione")
        no_drive = st.checkbox("Disabilita Drive", value=False, help="Salta provisioning/upload su Google Drive")
        no_vision = st.checkbox(
            "Disabilita Vision (genera YAML basici)",
            value=False,
            help="Crea semantic_mapping.yaml e cartelle_raw.yaml senza chiamare Vision",
        )
        deep_testing = st.checkbox(
            "Attiva testing profondo",
            value=False,
            help="Esegue Dummy KB con Vision/Drive reali (usa il flag --deep-testing).",
        )
        st.caption(
            "Il deep testing usa Vision/Drive reali e può fallire se i secrets/permessi non sono pronti. "
            "Verifica la pagina Secrets Healthcheck prima di attivarlo."
        )
        cleanup = st.button("Cancella dummy (locale + Drive)", type="secondary")
        proceed = st.button("Prosegui", type="primary")
        if cleanup:
            _cleanup_dummy(slug, client_name=f"Dummy {slug}", status_label="Pulizia dummy in corso.")
        if proceed:
            cmd = [sys.executable, "-m", "tools.gen_dummy_kb", "--slug", slug]
            if no_drive:
                cmd.append("--no-drive")
            if no_vision:
                cmd.append("--no-vision")
            if deep_testing:
                cmd.append("--deep-testing")
            _run_and_render(cmd)

    open_modal = st.dialog("Generazione Dummy KB", width="large")
    runner = open_modal(_render_modal_body)
    if callable(runner):
        runner()


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
