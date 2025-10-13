# SPDX-License-Identifier: GPL-3.0-or-later
# src/ui/pages/manage.py
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Optional

import streamlit as st

from pipeline.yaml_utils import yaml_read
from ui.chrome import render_chrome_then_require
from ui.utils import set_slug
from ui.utils.workspace import has_raw_pdfs


def _safe_get(fn_path: str) -> Optional[Callable[..., Any]]:
    """Importa una funzione se disponibile, altrimenti None. Formato: 'pkg.mod:func'."""
    try:
        pkg, func = fn_path.split(":")
        mod = __import__(pkg, fromlist=[func])
        fn = getattr(mod, func, None)
        return fn if callable(fn) else None
    except Exception:
        return None


# Services (gestiscono cache e bridging verso i component)
_render_drive_tree = _safe_get("ui.services.drive:render_drive_tree")
_render_drive_diff = _safe_get("ui.services.drive:render_drive_diff")
_emit_readmes_for_raw = _safe_get("ui.services.drive_runner:emit_readmes_for_raw")

# Tool di pulizia workspace (locale + DB + Drive)
# run_cleanup(slug: str, assume_yes: bool = False) -> int
_run_cleanup = _safe_get("src.tools.clean_client_workspace:run_cleanup")


# ---------------- Helpers ----------------


def _repo_root() -> Path:
    # manage.py -> pages -> ui -> src -> REPO_ROOT
    return Path(__file__).resolve().parents[3]


def _clients_db_path() -> Path:
    return _repo_root() / "clients_db" / "clients.yaml"


def _load_clients() -> list[dict[str, Any]]:
    """Carica l'elenco clienti dal DB (lista di dict normalizzata)."""
    try:
        path = _clients_db_path()
        if not path.exists():
            return []
        data = yaml_read(path.parent, path)
        if isinstance(data, list):
            return [dict(item) for item in data if isinstance(item, dict)]
        if isinstance(data, dict):
            normalized: list[dict[str, Any]] = []
            for slug_key, payload in data.items():
                record = dict(payload) if isinstance(payload, dict) else {}
                record.setdefault("slug", slug_key)
                normalized.append(record)
            return normalized
    except Exception:
        pass
    return []


# ---------------- UI ----------------

slug = render_chrome_then_require(allow_without_slug=True)

if not slug:
    st.subheader("Seleziona cliente")
    clients = _load_clients()

    if not clients:
        st.info("Nessun cliente registrato. Crea il primo dalla pagina **Nuovo cliente**.")
        st.html('<a href="/new?tab=new" target="_self">➕ Crea nuovo cliente</a>')
        st.stop()

    options: list[tuple[str, str]] = []
    for client in clients:
        slug_value = (client.get("slug") or "").strip()
        if not slug_value:
            continue
        name = (client.get("nome") or slug_value).strip()
        state = (client.get("stato") or "n/d").strip()
        label = f"{name} ({slug_value}) — {state}"
        options.append((label, slug_value))

    if not options:
        st.info("Nessun cliente valido trovato nel registro.")
        st.stop()

    labels = [label for label, _ in options]
    selected_label = st.selectbox("Cliente", labels, index=0, key="manage_select_slug")
    if st.button("Usa questo cliente", type="primary", width="stretch"):
        chosen = dict(options).get(selected_label)
        if chosen:
            set_slug(chosen)
        st.rerun()

    st.stop()

# Da qui in poi: slug presente → viste operative
if _render_drive_tree is not None:
    try:
        _render_drive_tree(slug)  # restituisce anche indice cachato
    except Exception as e:  # pragma: no cover
        st.error(f"Errore nella vista Drive: {e}")
else:
    st.info("Vista Drive non disponibile.")

if _render_drive_diff is not None:
    try:
        _render_drive_diff(slug)  # usa indice cachato, degrada a vuoto
    except Exception as e:  # pragma: no cover
        st.error(f"Errore nella vista Diff: {e}")
else:
    st.info("Vista Diff non disponibile.")

# --- Azione: Genera README nelle cartelle raw/ (sempre visibile) ---
st.markdown("")
if st.button("Genera README in raw/ (Drive)", key="btn_emit_readmes"):
    if _emit_readmes_for_raw is None:
        st.error(
            "Funzione non disponibile. Abilita gli extra Drive: "
            "`pip install .[drive]` e configura `SERVICE_ACCOUNT_FILE` / `DRIVE_ID`."
        )
    else:
        try:
            with st.status("Genero README nelle sottocartelle di raw/…", expanded=True):
                # Call “tollerante” a firme diverse
                try:
                    result = _emit_readmes_for_raw(slug=slug, ensure_structure=True, require_env=True)
                except TypeError:
                    result = _emit_readmes_for_raw(slug, ensure_structure=True)  # fallback a firma più semplice
            n = len(result or {})
            st.success(f"README creati/aggiornati: {n}")
        except Exception as e:  # pragma: no cover
            st.error(f"Impossibile generare i README: {e}")

st.markdown("")
if st.button("Rileva PDF in raw/", key="btn_probe_raw", width="stretch"):
    ready, raw_path = has_raw_pdfs(slug)
    if ready:
        st.success(f"PDF rilevati in `{raw_path}`.")
    else:
        st.warning(f"Nessun PDF trovato in `{raw_path}`.")
