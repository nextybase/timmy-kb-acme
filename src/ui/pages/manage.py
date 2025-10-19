# SPDX-License-Identifier: GPL-3.0-or-later
# src/ui/pages/manage.py
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Optional, TypeVar

import streamlit as st
import yaml

from pipeline.file_utils import safe_write_text
from pipeline.path_utils import read_text_safe
from pipeline.yaml_utils import yaml_read
from ui.chrome import render_chrome_then_require
from ui.clients_store import get_state as get_client_state
from ui.utils import set_slug
from ui.utils.status import status_guard


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
_render_drive_diff = _safe_get("ui.services.drive:render_drive_diff")
_invalidate_drive_index = _safe_get("ui.services.drive:invalidate_drive_index")
_emit_readmes_for_raw = _safe_get("ui.services.drive_runner:emit_readmes_for_raw")

# Download & pre-analisi (nuovo servizio estratto)
_plan_raw_download = _safe_get("ui.services.drive_runner:plan_raw_download")
_download_with_progress = _safe_get("ui.services.drive_runner:download_raw_from_drive_with_progress")
_download_simple = _safe_get("ui.services.drive_runner:download_raw_from_drive")

# Tool di pulizia workspace (locale + DB + Drive)
_run_cleanup = _safe_get("src.tools.clean_client_workspace:run_cleanup")  # noqa: F401

# Arricchimento semantico (estrazione tag → stub + YAML)
_run_tags_update = _safe_get("ui.services.tags_adapter:run_tags_update")


# -----------------------------------------------------------
# Modal editor per semantic/tags_reviewed.yaml
# -----------------------------------------------------------
def _open_tags_editor_modal(slug: str) -> None:
    base_dir = _repo_root() / "output" / f"timmy-kb-{slug}"
    yaml_path = base_dir / "semantic" / "tags_reviewed.yaml"
    yaml_parent = yaml_path.parent
    try:
        initial_text = read_text_safe(yaml_parent, yaml_path, encoding="utf-8")
    except Exception:
        initial_text = "version: 2\nkeep_only_listed: true\ntags: []\n"

    dialog_factory = getattr(st, "dialog", None)

    def _editor_body() -> None:
        caption_fn = getattr(st, "caption", None)
        if callable(caption_fn):
            caption_fn("Modifica e salva il file `semantic/tags_reviewed.yaml`.")
        content = st.text_area(
            "Contenuto YAML",
            value=initial_text,
            height=420,
            key="tags_yaml_editor",
            label_visibility="collapsed",
        )
        col_a, col_b = st.columns(2)
        if col_a.button("Salva", type="primary"):
            try:
                yaml.safe_load(content)
            except Exception as exc:
                st.error(f"YAML non valido: {exc}")
                return
            try:
                yaml_parent.mkdir(parents=True, exist_ok=True)
                safe_write_text(yaml_path, content, encoding="utf-8", atomic=True)
                st.toast("`tags_reviewed.yaml` salvato.")
                st.rerun()
            except Exception as exc:
                st.error(f"Errore nel salvataggio: {exc}")
        if col_b.button("Chiudi"):
            st.rerun()

    if dialog_factory:
        _dialog_fn = dialog_factory("Modifica tags_reviewed.yaml")(_editor_body)
        _dialog_fn()
    else:
        with st.container(border=True):
            st.subheader("Modifica tags_reviewed.yaml")
            _editor_body()


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


T = TypeVar("T")


def _call_best_effort(fn: Callable[..., T], **kwargs: Any) -> T:
    """Chiama fn con kwargs, degradando a posizionali in caso di firma diversa."""
    try:
        return fn(**kwargs)
    except TypeError:
        args: list[Any] = []
        if "slug" in kwargs:
            args.append(kwargs["slug"])
        if "overwrite" in kwargs:
            args.append(kwargs["overwrite"])
        if "require_env" in kwargs:
            args.append(kwargs["require_env"])
        return fn(*args)


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

# Unica vista per Drive (Diff)
if _render_drive_diff is not None:
    try:
        _render_drive_diff(slug)  # usa indice cachato, degrada a vuoto
    except Exception as e:  # pragma: no cover
        st.error(f"Errore nella vista Diff: {e}")
else:
    st.info("Vista Diff non disponibile.")

# --- Genera README / Rileva PDF / Scarica da Drive → locale in 3 colonne ---
st.markdown("")

client_state = (get_client_state(slug) or "").strip().lower()
emit_btn_type = "primary" if client_state == "nuovo" else "secondary"

try:
    c1, c2, c3 = st.columns([1, 1, 1])
except TypeError:
    c1, c2, c3 = st.columns(3)

with c1:
    if st.button("Genera README in raw/ (Drive)", key="btn_emit_readmes", type=emit_btn_type, width="stretch"):
        emit_fn = _emit_readmes_for_raw
        if emit_fn is None:
            st.error(
                "Funzione non disponibile. Abilita gli extra Drive: "
                "`pip install .[drive]` e configura `SERVICE_ACCOUNT_FILE` / `DRIVE_ID`."
            )
        else:
            try:
                with status_guard(
                    "Genero i README nelle sottocartelle di raw/ su Drive…",
                    expanded=True,
                    error_label="Errore durante la generazione dei README",
                ) as status_widget:
                    try:
                        # NIENTE creazione struttura, NIENTE split: solo emissione PDF da semantic_mapping.yaml
                        result = _call_best_effort(emit_fn, slug=slug, ensure_structure=False, require_env=True)
                    except TypeError:
                        result = _call_best_effort(emit_fn, slug=slug, ensure_structure=False)
                    count = len(result or {})
                    if status_widget is not None and hasattr(status_widget, "update"):
                        status_widget.update(label=f"README creati/aggiornati: {count}", state="complete")

                try:
                    if _invalidate_drive_index is not None:
                        _invalidate_drive_index(slug)
                    st.toast("README generati su Drive.")
                    st.rerun()
                except Exception:
                    pass
            except Exception as e:  # pragma: no cover
                st.error(f"Impossibile generare i README: {e}")

with c2:
    base_dir = _repo_root() / "output" / f"timmy-kb-{slug}"
    raw_dir = base_dir / "raw"
    semantic_dir = base_dir / "semantic"
    try:
        has_pdfs = raw_dir.exists() and any(p.suffix.lower() == ".pdf" for p in raw_dir.rglob("*.pdf"))
    except Exception:
        has_pdfs = False

    disabled_semantic = (not has_pdfs) or (_run_tags_update is None)
    button_type = "primary" if has_pdfs else "secondary"

    open_semantic = st.button(
        "Avvia arricchimento semantico",
        key="btn_semantic_start",
        type=button_type,
        width="stretch",
        disabled=disabled_semantic,
        help="Estrae tag dai PDF in raw/, genera tags_raw.csv e lo stub/YAML tags_reviewed.",
    )
    if open_semantic:
        if _run_tags_update is None:
            st.error("Servizio di estrazione tag non disponibile.")
        else:
            try:
                _run_tags_update(slug)
                _open_tags_editor_modal(slug)
            except Exception as exc:  # pragma: no cover
                st.error(f"Estrazione tag non riuscita: {exc}")
    st.info("Arricchimento semantico: usa la pagina **Semantica** per i workflow dedicati avanzati.")
    if (_run_tags_update is not None) and (not has_pdfs):
        st.info("Nessun PDF rilevato in raw/: carica i documenti prima di procedere con l'arricchimento.")

    _caption = getattr(st, "caption", None)
    if callable(_caption):
        _caption("")
    if (semantic_dir / "tags_reviewed.yaml").exists():
        if st.button("Modifica `tags_reviewed.yaml`", key="btn_edit_tags_yaml", type="secondary"):
            _open_tags_editor_modal(slug)

with c3:
    if st.button("Scarica PDF da Drive → locale", key="btn_drive_download", type="secondary", width="stretch"):

        def _modal() -> None:
            st.write(
                "Questa operazione scarica i file dalle cartelle di Google Drive nelle cartelle locali corrispondenti."
            )
            st.write("Stiamo verificando la presenza di file preesistenti nella cartelle locali.")

            conflicts, labels = [], []
            try:
                plan_fn = _plan_raw_download
                if plan_fn is None:
                    raise RuntimeError("plan_raw_download non disponibile in ui.services.drive_runner.")
                conflicts, labels = _call_best_effort(plan_fn, slug=slug, require_env=True)
            except Exception as e:
                st.error(f"Impossibile preparare il piano di download: {e}")
                return

            if conflicts:
                with st.expander(f"File già presenti in locale ({len(conflicts)})", expanded=True):
                    st.markdown("\n".join(f"- `{x}`" for x in sorted(conflicts)))
            else:
                st.info("Nessun conflitto rilevato: nessun file verrebbe sovrascritto.")

            with st.expander(f"Anteprima destinazioni ({len(labels)})", expanded=False):
                st.markdown("\n".join(f"- `{x}`" for x in sorted(labels)))

            cA, cB = st.columns(2)
            if cA.button("Annulla", key="dl_cancel", width="stretch"):
                return
            if cB.button("Procedi e scarica", key="dl_proceed", type="primary", width="stretch"):
                try:
                    with status_guard(
                        "Scarico file da Drive…",
                        expanded=True,
                        error_label="Errore durante il download",
                    ) as status_widget:
                        download_fn = _download_with_progress or _download_simple
                        if download_fn is None:
                            raise RuntimeError("Funzione di download non disponibile.")
                        try:
                            paths = _call_best_effort(
                                download_fn,
                                slug=slug,
                                require_env=True,
                                overwrite=bool(conflicts),
                            )
                        except TypeError:
                            paths = _call_best_effort(download_fn, slug=slug, overwrite=bool(conflicts))
                        count = len(paths or [])
                        if status_widget is not None and hasattr(status_widget, "update"):
                            status_widget.update(
                                label=f"Download completato. File nuovi/aggiornati: {count}.", state="complete"
                            )

                    try:
                        if _invalidate_drive_index is not None:
                            _invalidate_drive_index(slug)
                        st.toast("Allineamento Drive→locale completato.")
                        st.rerun()
                    except Exception:
                        pass
                except Exception as e:
                    st.error(f"Errore durante il download: {e}")

        dialog_builder = getattr(st, "dialog", None)
        if callable(dialog_builder):
            open_modal = dialog_builder("Scarica da Google Drive nelle cartelle locali", width="large")
            runner = open_modal(_modal)
            (runner if callable(runner) else _modal)()
        else:
            _modal()
