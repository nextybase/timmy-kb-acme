# SPDX-License-Identifier: GPL-3.0-or-later
# src/ui/pages/manage.py
from __future__ import annotations

import inspect
from pathlib import Path
from typing import Any, Callable, Optional, TypeVar, cast

import streamlit as st
import yaml

from pipeline.logging_utils import get_structured_logger
from pipeline.path_utils import ensure_within_and_resolve, read_text_safe
from pipeline.yaml_utils import yaml_read
from semantic.tags_io import write_tags_reviewed_from_nlp_db
from storage.tags_store import derive_db_path_from_yaml_path
from ui.chrome import render_chrome_then_require
from ui.clients_store import get_state as get_client_state
from ui.utils import set_slug
from ui.utils.core import safe_write_text
from ui.utils.status import status_guard
from ui.utils.workspace import count_pdfs_safe, iter_pdfs_safe, resolve_raw_dir

LOGGER = get_structured_logger("ui.manage")


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
_run_cleanup = _safe_get("timmykb.tools.clean_client_workspace:run_cleanup")  # noqa: F401

# Arricchimento semantico (estrazione tag ? stub + YAML)
_run_tags_update = _safe_get("ui.services.tags_adapter:run_tags_update")


# ---------------- Helpers ----------------
def _repo_root() -> Path:
    # manage.py -> pages -> ui -> src -> REPO_ROOT
    return Path(__file__).resolve().parents[3]


def _clients_db_path() -> Path:
    return _repo_root() / "clients_db" / "clients.yaml"


def _workspace_root(slug: str) -> Path:
    """Restituisce la radice workspace sicura per lo slug (validato)."""
    raw_dir = Path(resolve_raw_dir(slug))  # valida slug + path safety, tipizzato per mypy
    return raw_dir.parent


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
    except Exception as exc:
        LOGGER.warning(
            "ui.manage.clients.load_error",
            extra={"error": str(exc), "path": str(_clients_db_path())},
        )
    return []


T = TypeVar("T")


def _call_best_effort(fn: Callable[..., T], **kwargs: Any) -> T:
    """Chiama fn con kwargs, degradando a posizionali in caso di firma diversa."""
    try:
        return fn(**kwargs)
    except TypeError:
        try:
            sig = inspect.signature(fn)
            bound = sig.bind_partial(**kwargs)
            return fn(*bound.args, **bound.kwargs)
        except Exception:
            keys = ("slug", "overwrite", "require_env")
            args = [kwargs[k] for k in keys if k in kwargs]
            return fn(*args)


# -----------------------------------------------------------
# Modal editor per semantic/tags_reviewed.yaml
# -----------------------------------------------------------
def _open_tags_editor_modal(slug: str) -> None:
    base_dir = _workspace_root(slug)
    yaml_path = Path(ensure_within_and_resolve(base_dir, base_dir / "semantic" / "tags_reviewed.yaml"))
    yaml_parent = yaml_path.parent
    try:
        initial_text = read_text_safe(yaml_parent, yaml_path, encoding="utf-8")
    except Exception:
        initial_text = "version: 2\nkeep_only_listed: true\ntags: []\n"

    # evento apertura editor
    LOGGER.info("ui.manage.tags.open", extra={"slug": slug})

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
                LOGGER.warning("ui.manage.tags.yaml.invalid", extra={"slug": slug, "error": str(exc)})
                return
            try:
                LOGGER.info("ui.manage.tags.yaml.valid", extra={"slug": slug})
                yaml_parent.mkdir(parents=True, exist_ok=True)
                safe_write_text(yaml_path, content, encoding="utf-8", atomic=True)
                st.toast("`tags_reviewed.yaml` salvato.")
                LOGGER.info("ui.manage.tags.save", extra={"slug": slug, "path": str(yaml_path)})
                st.rerun()
            except Exception as exc:
                st.error(f"Errore nel salvataggio: {exc}")
                LOGGER.warning("ui.manage.tags.save.error", extra={"slug": slug, "error": str(exc)})
        if col_b.button("Chiudi"):
            st.rerun()

    if dialog_factory:
        _dialog_fn = dialog_factory("Modifica tags_reviewed.yaml")(_editor_body)
        _dialog_fn()
    else:
        with st.container(border=True):
            st.subheader("Modifica tags_reviewed.yaml")
            _editor_body()


# --- piccoli helper per compat con stub di test ---
def _columns3() -> tuple[Any, Any, Any]:
    """Restituisce sempre 3 colonne, facendo padding se lo stub ne crea <3."""
    make = getattr(st, "columns", None)
    if not callable(make):
        return (st, st, st)
    try:
        cols = list(make([1, 1, 1]))
    except Exception:
        try:
            cols = list(make(3))
        except Exception:
            return (st, st, st)
    if not cols:
        return (st, st, st)
    while len(cols) < 3:
        cols.append(cols[-1])
    return cast(Any, cols[0]), cast(Any, cols[1]), cast(Any, cols[2])


def _btn(container: Any, *args: Any, **kwargs: Any) -> bool:
    """Chiama button sul container se esiste, altrimenti degrada a st.button."""
    fn = getattr(container, "button", None)
    if callable(fn):
        try:
            return bool(fn(*args, **kwargs))
        except Exception:
            pass
    fallback = getattr(st, "button", None)
    return bool(fallback(*args, **kwargs)) if callable(fallback) else False


def _column_button(container: Any, label: str, **kwargs: Any) -> bool:
    fn = getattr(container, "button", None)
    if callable(fn):
        try:
            return bool(fn(label, **kwargs))
        except TypeError as exc:
            if "width" in str(exc):
                kwargs.pop("width", None)
                return bool(fn(label, **kwargs))
            raise
    fallback = getattr(st, "button", None)
    if callable(fallback):
        try:
            return bool(fallback(label, **kwargs))
        except TypeError as exc:
            if "width" in str(exc):
                kwargs.pop("width", None)
                return bool(fallback(label, **kwargs))
            raise
    return False


# ---------------- UI ----------------

slug = render_chrome_then_require(allow_without_slug=True)

if not slug:
    st.subheader("Seleziona cliente")
    clients = _load_clients()

    if not clients:
        st.info("Nessun cliente registrato. Crea il primo dalla pagina **Nuovo cliente**.")
        st.html('<a href="/new?tab=new" target="_self">? Crea nuovo cliente</a>')
        st.stop()

    options: list[tuple[str, str]] = []
    for client in clients:
        slug_value = (client.get("slug") or "").strip()
        if not slug_value:
            continue
        name = (client.get("nome") or slug_value).strip()
        state = (client.get("stato") or "n/d").strip()
        label = f"{name} ({slug_value}) - {state}"
        options.append((label, slug_value))

    if not options:
        st.info("Nessun cliente valido trovato nel registro.")
        st.stop()

    labels = [label for label, _ in options]
    selected_label = st.selectbox("Cliente", labels, index=0, key="manage_select_slug")
    if _column_button(st, "Usa questo cliente", type="primary", width="stretch"):
        chosen = dict(options).get(selected_label)
        if chosen:
            set_slug(chosen)
        st.rerun()

    st.stop()

slug = cast(str, slug)


def _render_status_block(
    pdf_count: int | None = None,
    service_ok: bool | None = None,
    semantic_dir: Path | None = None,
) -> None:
    if pdf_count is None:
        pdf_count = globals().get("pdf_count", 0)
    if service_ok is None:
        service_ok = bool(globals().get("service_ok"))
    if semantic_dir is None:
        semantic_dir = cast(Path, globals().get("semantic_dir"))
        if semantic_dir is None:
            raise RuntimeError("semantic_dir non disponibile per _render_status_block")

    info_fn = getattr(st, "info", None)
    if callable(info_fn):
        info_fn("Arricchimento semantico: usa la pagina **Semantica** per i workflow dedicati avanzati.")
    db_path = semantic_dir / "tags.db"
    db_exists = db_path.exists()
    info_msg = (
        f"PDF in raw/: **{pdf_count}** - Servizio estrazione: **{'OK' if service_ok else 'mancante'}** "
        f"- tags.db: **{'presente' if db_exists else 'assente'}**"
    )
    caption_fn = getattr(st, "caption", None)
    if callable(caption_fn):
        caption_fn(info_msg)
    elif callable(info_fn):
        info_fn(info_msg)
    if not db_exists:
        warn_fn = getattr(st, "warning", None)
        if callable(warn_fn):
            warn_fn("`semantic/tags.db` non trovato: estrai e valida i tag prima dell'arricchimento semantico.")


if slug:
    # Da qui in poi: slug presente ? viste operative

    # Unica vista per Drive (Diff)
    if _render_drive_diff is not None:
        try:
            _render_drive_diff(slug)  # usa indice cachato, degrada a vuoto
        except Exception as e:  # pragma: no cover
            st.error(f"Errore nella vista Diff: {e}")
    else:
        st.info("Vista Diff non disponibile.")

    # --- Genera README / Rileva PDF / Scarica da Drive ? locale in 3 colonne ---
    _markdown = getattr(st, "markdown", None)
    if callable(_markdown):
        _markdown("")

    c1, c2, c3 = _columns3()

    client_state = (get_client_state(slug) or "").strip().lower()
    emit_btn_type = "primary" if client_state == "nuovo" else "secondary"

    # Colonna 1 â€“ README su Drive
    if _column_button(c1, "Genera README in raw/ (Drive)", key="btn_emit_readmes", type=emit_btn_type, width="stretch"):
        emit_fn = _emit_readmes_for_raw
        if emit_fn is None:
            st.error(
                "Funzione non disponibile. Abilita gli extra Drive: "
                "`pip install .[drive]` e configura `SERVICE_ACCOUNT_FILE` / `DRIVE_ID`."
            )
        else:
            try:
                with status_guard(
                    "Genero i README nelle sottocartelle di raw/ su Driveâ€¦",
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

    # Colonna 2  -  Arricchimento semantico (estrazione tag)
    base_dir = _workspace_root(slug)
    raw_dir = Path(ensure_within_and_resolve(base_dir, base_dir / "raw"))
    semantic_dir = Path(ensure_within_and_resolve(base_dir, base_dir / "semantic"))

    has_pdfs = any(iter_pdfs_safe(raw_dir))
    pdf_count = count_pdfs_safe(raw_dir)
    run_tags_fn = cast(Optional[Callable[[str], Any]], _run_tags_update)
    service_ok = run_tags_fn is not None

    open_semantic = _column_button(
        c2,
        "Avvia arricchimento semantico",
        key="btn_semantic_start",
        type="primary",
        width="stretch",
        help="Estrae tag dai PDF in raw/, genera tags_raw.csv e lo stub (in DB). Lo YAML si pubblica a parte.",
    )
    if open_semantic:
        if run_tags_fn is None:
            st.error(
                "Servizio di estrazione tag non disponibile.",
            )
            st.stop()
        elif not has_pdfs:
            st.error(f"Nessun PDF rilevato in `{raw_dir}`. Allinea i documenti da Drive o carica PDF manualmente.")
            st.stop()
        else:
            try:
                run_tags_fn(slug)
                _open_tags_editor_modal(slug)
            except Exception as exc:  # pragma: no cover
                st.error(f"Estrazione tag non riuscita: {exc}")

    if _column_button(
        c2,
        "Pubblica tag revisionati (da DB)",
        key="btn_publish_tags",
        type="secondary",
        width="stretch",
        help="Esporta semantic/tags_reviewed.yaml a partire dal DB NLP (terms/aliases).",
    ):
        try:
            base_dir = _workspace_root(slug)
            semantic_dir = Path(ensure_within_and_resolve(base_dir, base_dir / "semantic"))
            yaml_path = Path(ensure_within_and_resolve(semantic_dir, semantic_dir / "tags_reviewed.yaml"))
            db_path = Path(derive_db_path_from_yaml_path(yaml_path))
            out = write_tags_reviewed_from_nlp_db(semantic_dir, db_path, LOGGER)
            st.toast(f"`tags_reviewed.yaml` pubblicato: {out}")
            _open_tags_editor_modal(slug)
        except Exception as exc:  # pragma: no cover
            st.error(f"Pubblicazione non riuscita: {exc}")
    _render_status_block(pdf_count=pdf_count, service_ok=service_ok, semantic_dir=semantic_dir)

    # Colonna 3 â€“ Scarica da Drive ? locale
    if _column_button(c3, "Scarica PDF da Drive ? locale", key="btn_drive_download", type="secondary", width="stretch"):

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
                message = f"Impossibile preparare il piano di download: {e}"
                HttpErrorType: type[BaseException] | None
                try:
                    from googleapiclient.errors import HttpError as _HttpError
                except Exception:
                    HttpErrorType = None
                else:
                    HttpErrorType = _HttpError

                if HttpErrorType is not None and isinstance(e, HttpErrorType) and getattr(e, "resp", None):
                    status = getattr(getattr(e, "resp", None), "status", None)
                else:
                    status = None

                if status == 500:
                    st.error(
                        f"{message}\n"
                        "Potrebbe trattarsi di un errore temporaneo del servizio Drive. "
                        "Riprovare tra qualche minuto e, se il problema persiste, scaricare i PDF manualmente da Drive "
                        "e copiarli nella cartella `raw/`."
                    )
                else:
                    st.error(message)
                return

            if conflicts:
                with st.expander(f"File giÃ  presenti in locale ({len(conflicts)})", expanded=True):
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
                        "Scarico file da Driveâ€¦",
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
                        st.toast("Allineamento Drive?locale completato.")
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
