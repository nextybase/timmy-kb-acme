# SPDX-License-Identifier: GPL-3.0-or-later
# src/ui/pages/cleanup.py
from __future__ import annotations

from typing import cast

from ui.utils.stubs import get_streamlit

st = get_streamlit()

from ui.chrome import render_chrome_then_require
from ui.clients_store import load_clients as _load_clients
from ui.manage import cleanup as cleanup_component
from ui.utils import resolve_raw_dir, set_slug
from ui.utils.route_state import clear_tab, get_slug_from_qp, get_tab, set_tab  # noqa: F401

_run_cleanup = cleanup_component.resolve_run_cleanup()
_perform_cleanup = cleanup_component.resolve_perform_cleanup()


def _redirect_home() -> None:
    """Redirect immediato alla home nella stessa scheda."""
    try:
        set_tab("home")
    except Exception:
        pass
    st.rerun()


# ---- UI chrome ----
slug = render_chrome_then_require(allow_without_slug=True)
if not slug:
    st.info("Seleziona o inserisci uno slug cliente dalla pagina **Gestisci cliente**.")
    st.stop()

slug = cast(str, slug)

st.subheader("Cleanup")
st.write("Strumenti di pulizia del workspace e **cancellazione definitiva** del cliente.")

# --- Esito ultima operazione (mostrato nel main dopo la chiusura del modal) ---
_last = st.session_state.pop("__cleanup_done", None)
if isinstance(_last, dict) and _last.get("text"):
    level = (_last.get("level") or "success").strip().lower()
    if level == "warning":
        st.warning(_last["text"])
    elif level == "error":
        st.error(_last["text"])
    else:
        st.success(_last["text"])

# --- Riepilogo di ciò che verrà cancellato ---
st.markdown("---")
st.markdown("### Cosa verrà cancellato")

client_name = cleanup_component.client_display_name(slug, _load_clients)
raw_folders = cleanup_component.list_raw_subfolders(slug, resolve_raw_dir)

st.markdown(f"**Cliente:** {client_name}  \n" f"**Google Drive:** `{slug}`")

if raw_folders:
    raw_list = ", ".join(f"`{name}`" for name in raw_folders)
    st.markdown(f"**Cartelle RAW:** {raw_list}")
else:
    st.markdown("**Cartelle RAW:** *(nessuna cartella trovata o RAW non presente)*")

# --- Danger zone: cancellazione cliente ---
st.markdown("---")
st.markdown("### Danger zone")


def _open_confirm_dialog() -> None:
    """Apre il modal di conferma e gestisce l'esecuzione del cleanup."""
    cleanup_component.open_cleanup_modal(
        st=st,
        slug=slug,
        client_name=client_name,
        set_slug=set_slug,
        run_cleanup=_run_cleanup,
        perform_cleanup=_perform_cleanup,
    )


if st.button(
    "Cancella cliente…",
    key="cleanup_open_confirm",
    type="secondary",
    help="Rimozione completa: locale, DB e Drive",
    width="stretch",
):
    _open_confirm_dialog()
