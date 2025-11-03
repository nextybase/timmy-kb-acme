# SPDX-License-Identifier: GPL-3.0-or-later
# src/ui/pages/manage.py
from __future__ import annotations

import inspect
import os
from pathlib import Path
from typing import Any, Callable, Optional, TypeVar, cast

import yaml

from pipeline.exceptions import ConfigError
from pipeline.logging_utils import get_structured_logger
from pipeline.path_utils import ensure_within_and_resolve, read_text_safe
from ui.chrome import render_chrome_then_require
from ui.clients_store import get_all as get_clients
from ui.clients_store import get_state as get_client_state
from ui.utils.route_state import clear_tab, get_slug_from_qp, get_tab, set_tab  # noqa: F401
from ui.utils.stubs import get_streamlit
from ui.utils.ui_controls import column_button as _column_button
from ui.utils.ui_controls import columns3 as _columns3

try:
    from ui.clients_store import set_state as set_client_state
except (ImportError, AttributeError):  # pragma: no cover - fallback per stub di test

    def set_client_state(slug: str, new_state: str) -> bool:
        return False


from storage.tags_store import import_tags_yaml_to_db
from ui.utils import set_slug
from ui.utils.core import safe_write_text
from ui.utils.status import status_guard
from ui.utils.workspace import count_pdfs_safe, resolve_raw_dir

try:
    from ui.gating import reset_gating_cache as _reset_gating_cache
except Exception:  # pragma: no cover - fallback per test headless

    def _reset_gating_cache(_slug: str | None = None) -> None:
        return


LOGGER = get_structured_logger("ui.manage")
st = get_streamlit()


def _safe_rerun() -> None:
    rerun_fn = getattr(st, "rerun", None)
    if callable(rerun_fn):
        try:
            rerun_fn()
        except Exception:
            pass


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
    """Carica l'elenco clienti delegando allo store centrale."""
    try:
        return [entry.to_dict() for entry in get_clients()]
    except Exception as exc:
        LOGGER.warning(
            "ui.manage.clients.load_error",
            extra={"error": str(exc), "path": str(_clients_db_path())},
        )
        return []


T = TypeVar("T")


def _call_best_effort(fn: Callable[..., T], **kwargs: Any) -> T:
    """Chiama fn con kwargs garantendo corrispondenza con la firma dichiarata."""
    sig = inspect.signature(fn)
    try:
        sig.bind(**kwargs)
    except TypeError:
        LOGGER.error(
            "ui.manage.signature_mismatch",
            extra={"fn": getattr(fn, "__name__", repr(fn)), "kwargs": sorted(kwargs)},
        )
        raise
    return fn(**kwargs)


# ---------------- Action handlers ----------------
def _handle_tags_raw_save(
    slug: str,
    content: str,
    csv_path: Path,
    semantic_dir: Path,
) -> bool:
    header = (content.splitlines() or [""])[0]
    header_tokens = {token.strip().lower() for token in header.split(",")}
    if "suggested_tags" not in header_tokens:
        st.error("CSV non valido: manca la colonna 'suggested_tags'.")
        LOGGER.warning("ui.manage.tags_raw.invalid_header", extra={"slug": slug})
        return False

    semantic_dir.mkdir(parents=True, exist_ok=True)
    safe_write_text(csv_path, content, encoding="utf-8", atomic=True)
    st.toast("`tags_raw.csv` salvato.")
    LOGGER.info("ui.manage.tags_raw.saved", extra={"slug": slug, "path": str(csv_path)})
    return True


def _enable_tags_stub(
    slug: str,
    semantic_dir: Path,
    yaml_path: Path,
) -> bool:
    try:
        semantic_dir.mkdir(parents=True, exist_ok=True)
        payload = "version: 2\nkeep_only_listed: true\ntags: []\n"
        previous = None
        try:
            previous = read_text_safe(semantic_dir, yaml_path, encoding="utf-8")
        except Exception:
            previous = None
        safe_write_text(yaml_path, payload, encoding="utf-8", atomic=True)
        if yaml_path.exists():
            try:
                import_tags_yaml_to_db(yaml_path, logger=LOGGER)
                LOGGER.info("ui.manage.tags.db_synced", extra={"slug": slug, "path": str(yaml_path)})
            except Exception as exc:
                if previous is not None:
                    safe_write_text(yaml_path, previous, encoding="utf-8", atomic=True)
                    LOGGER.warning(
                        "ui.manage.tags.rollback",
                        extra={"slug": slug, "path": str(yaml_path), "reason": "stub-db-error"},
                    )
                LOGGER.warning(
                    "ui.manage.tags.db_sync_failed",
                    extra={"slug": slug, "path": str(yaml_path), "error": str(exc)},
                )
                st.error(f"Sincronizzazione tags.db non riuscita: {exc}")
                return False
        else:
            LOGGER.warning(
                "ui.manage.tags.db_sync_skipped",
                extra={"slug": slug, "path": str(yaml_path), "reason": "file-missing"},
            )

        try:
            updated = set_client_state(slug, "arricchito")
        except Exception as exc:
            LOGGER.warning(
                "ui.manage.state.update_failed",
                extra={"slug": slug, "error": str(exc)},
            )
            updated = False

        if updated:
            st.toast("`tags_reviewed.yaml` generato (stub). Stato aggiornato a 'arricchito'.")
            _reset_gating_cache(slug)
        else:
            st.warning("Impossibile aggiornare lo stato cliente (stub): verifica clients_db/clients.yaml.")
        LOGGER.info("ui.manage.tags_yaml.published_stub", extra={"slug": slug, "path": str(yaml_path)})
        return True
    except Exception as exc:
        st.error(f"Abilitazione (stub) non riuscita: {exc}")
        LOGGER.warning(
            "ui.manage.tags_yaml.stub_error",
            extra={"slug": slug, "error": str(exc)},
        )
        return False


def _enable_tags_service(
    slug: str,
    semantic_dir: Path,
    csv_path: Path,
    yaml_path: Path,
) -> bool:
    try:
        from semantic.api import export_tags_yaml_from_db
        from semantic.tags_io import write_tags_review_stub_from_csv
        from storage.tags_store import derive_db_path_from_yaml_path

        write_tags_review_stub_from_csv(semantic_dir, csv_path, LOGGER)
        db_path = Path(derive_db_path_from_yaml_path(yaml_path))
        export_tags_yaml_from_db(semantic_dir, db_path, LOGGER)
        try:
            updated = set_client_state(slug, "arricchito")
        except Exception as exc:
            LOGGER.warning(
                "ui.manage.state.update_failed",
                extra={"slug": slug, "error": str(exc)},
            )
            updated = False
        if updated:
            st.toast("`tags_reviewed.yaml` generato. Stato aggiornato a 'arricchito'.")
            _reset_gating_cache(slug)
        else:
            st.warning("Impossibile aggiornare lo stato cliente: verifica clients_db/clients.yaml.")
        LOGGER.info("ui.manage.tags_yaml.published", extra={"slug": slug, "path": str(yaml_path)})
        return True
    except Exception as exc:
        st.error(f"Abilitazione non riuscita: {exc}")
        LOGGER.warning("ui.manage.tags_yaml.publish.error", extra={"slug": slug, "error": str(exc)})
        return False


def _handle_tags_raw_enable(
    slug: str,
    semantic_dir: Path,
    csv_path: Path,
    yaml_path: Path,
) -> bool:
    tags_mode = os.getenv("TAGS_MODE", "").strip().lower()
    if tags_mode == "stub":
        return _enable_tags_stub(slug, semantic_dir, yaml_path)
    run_tags_fn = cast(Optional[Callable[[str], Any]], _run_tags_update)
    if run_tags_fn is None and tags_mode != "stub":
        LOGGER.error(
            "ui.manage.tags.service_missing",
            extra={"slug": slug, "mode": tags_mode or "default"},
        )
        st.error("Servizio di estrazione tag non disponibile.")
        return False
    return _enable_tags_service(slug, semantic_dir, csv_path, yaml_path)


def _prepare_download_plan(slug: str) -> tuple[list[str], list[str]]:
    plan_fn = _plan_raw_download
    if plan_fn is None:
        raise RuntimeError("plan_raw_download non disponibile in ui.services.drive_runner.")
    result = _call_best_effort(plan_fn, slug=slug, require_env=True)
    return cast(tuple[list[str], list[str]], result)


def _render_download_plan(conflicts: list[str], labels: list[str]) -> None:
    if conflicts:
        with st.expander(f"File gi�� presenti in locale ({len(conflicts)})", expanded=True):
            st.markdown("\n".join(f"- `{x}`" for x in sorted(conflicts)))
    else:
        st.info("Nessun conflitto rilevato: nessun file verrebbe sovrascritto.")

    with st.expander(f"Anteprima destinazioni ({len(labels)})", expanded=False):
        st.markdown("\n".join(f"- `{x}`" for x in sorted(labels)))


def _execute_drive_download(slug: str, conflicts: list[str]) -> bool:
    try:
        with status_guard(
            "Scarico file da Drive...",
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
                status_widget.update(label=f"Download completato. File nuovi/aggiornati: {count}.", state="complete")

        try:
            if _invalidate_drive_index is not None:
                _invalidate_drive_index(slug)
            st.toast("Allineamento Drive->locale completato.")
            return True
        except Exception:
            return True
    except Exception as exc:
        st.error(f"Errore durante il download: {exc}")
        return False


def _render_drive_status_message(disabled: bool, message: str) -> None:
    if disabled:
        st.info(message)


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
        if _column_button(col_a, "Salva", type="primary"):
            try:
                parsed = yaml.safe_load(content)
                if parsed is not None and not isinstance(parsed, dict):
                    raise ConfigError("Top-level YAML deve essere un mapping")
            except Exception as exc:
                st.error(f"YAML non valido: {exc}")
                LOGGER.warning("ui.manage.tags.yaml.invalid", extra={"slug": slug, "error": str(exc)})
                return
            backup_text: Optional[str] = None
            try:
                try:
                    backup_text = read_text_safe(yaml_parent, yaml_path, encoding="utf-8")
                except Exception:
                    backup_text = None
                LOGGER.info("ui.manage.tags.yaml.valid", extra={"slug": slug})
                yaml_parent.mkdir(parents=True, exist_ok=True)
                safe_write_text(yaml_path, content, encoding="utf-8", atomic=True)
                if yaml_path.exists():
                    try:
                        import_tags_yaml_to_db(yaml_path, logger=LOGGER)
                        LOGGER.info("ui.manage.tags.db_synced", extra={"slug": slug, "path": str(yaml_path)})
                    except Exception as exc:
                        if backup_text is not None:
                            safe_write_text(yaml_path, backup_text, encoding="utf-8", atomic=True)
                            LOGGER.warning(
                                "ui.manage.tags.rollback",
                                extra={"slug": slug, "path": str(yaml_path), "reason": "db-sync-error"},
                            )
                        LOGGER.warning(
                            "ui.manage.tags.db_sync_failed",
                            extra={"slug": slug, "path": str(yaml_path), "error": str(exc)},
                        )
                        st.error(f"Sincronizzazione tags.db non riuscita: {exc}")
                        return
                else:
                    LOGGER.warning(
                        "ui.manage.tags.db_sync_skipped",
                        extra={"slug": slug, "path": str(yaml_path), "reason": "file-missing"},
                    )
                st.toast("`tags_reviewed.yaml` salvato.")
                LOGGER.info("ui.manage.tags.save", extra={"slug": slug, "path": str(yaml_path)})
                _safe_rerun()
            except Exception as exc:
                if backup_text is not None:
                    safe_write_text(yaml_path, backup_text, encoding="utf-8", atomic=True)
                    LOGGER.warning(
                        "ui.manage.tags.rollback",
                        extra={"slug": slug, "path": str(yaml_path), "reason": "save-exception"},
                    )
                st.error(f"Errore nel salvataggio: {exc}")
                LOGGER.warning("ui.manage.tags.save.error", extra={"slug": slug, "error": str(exc)})
        if _column_button(col_b, "Chiudi"):
            _safe_rerun()

    if dialog_factory:
        _dialog_fn = dialog_factory("Modifica tags_reviewed.yaml")(_editor_body)
        _dialog_fn()
    else:
        with st.container(border=True):
            st.subheader("Modifica tags_reviewed.yaml")
            _editor_body()


def _open_tags_raw_modal(slug: str) -> None:
    base_dir = _workspace_root(slug)
    semantic_dir = Path(ensure_within_and_resolve(base_dir, base_dir / "semantic"))
    csv_path = Path(ensure_within_and_resolve(semantic_dir, semantic_dir / "tags_raw.csv"))
    yaml_path = Path(ensure_within_and_resolve(semantic_dir, semantic_dir / "tags_reviewed.yaml"))
    try:
        initial_text = read_text_safe(semantic_dir, csv_path, encoding="utf-8")
    except Exception:
        initial_text = "relative_path,suggested_tags,entities,keyphrases,score,sources\n"

    LOGGER.info("ui.manage.tags_raw.open", extra={"slug": slug})
    dialog_factory = getattr(st, "dialog", None)

    def _body() -> None:
        cap = getattr(st, "caption", None)
        if callable(cap):
            cap(
                "Modifica `semantic/tags_raw.csv`. **Salva raw** aggiorna il CSV; "
                "**Abilita** genera `tags_reviewed.yaml` e abilita la Semantica."
            )

        content = st.text_area(
            "Contenuto CSV",
            value=initial_text,
            height=420,
            key="tags_csv_editor",
            label_visibility="collapsed",
        )
        col_a, col_b = st.columns(2)

        if _column_button(col_a, "Salva raw", type="secondary"):
            _handle_tags_raw_save(slug, content, csv_path, semantic_dir)

        if _column_button(col_b, "Abilita", type="primary"):
            if _handle_tags_raw_enable(slug, semantic_dir, csv_path, yaml_path):
                _safe_rerun()

    if dialog_factory:
        (dialog_factory("Revisione keyword (tags_raw.csv)")(_body))()
    else:
        with st.container(border=True):
            st.subheader("Revisione keyword (tags_raw.csv)")
            _body()


# --- piccoli helper per compat con stub di test ---
# helper centralizzati in ui.utils.ui_controls (DRY)


# ---------------- UI ----------------

slug = render_chrome_then_require(allow_without_slug=True)

if not slug:
    st.subheader("Seleziona cliente")
    clients = _load_clients()

    if not clients:
        st.info("Nessun cliente registrato. Crea il primo dalla pagina **Nuovo cliente**.")
        # Sostituisce anchor HTML interno con page_link / fallback
        if hasattr(st, "page_link"):
            st.page_link("src/ui/pages/new_client.py", label="➕ Crea nuovo cliente")
        else:
            st.link_button("➕ Crea nuovo cliente", url="/new?tab=new")
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
        _safe_rerun()

    st.stop()

slug = cast(str, slug)


def _render_status_block(
    pdf_count: int,
    service_ok: bool,
    semantic_dir: Path,
) -> None:
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
    _markdown = getattr(st, "markdown", None)
    if callable(_markdown):
        _markdown("")

    c1, c2, c3 = _columns3()

    client_state = (get_client_state(slug) or "").strip().lower()
    emit_btn_type = "primary" if client_state == "nuovo" else "secondary"

    # Colonna 1 – README su Drive
    emit_disabled = _emit_readmes_for_raw is None
    _render_drive_status_message(
        emit_disabled,
        "Funzione Drive non disponibile: installa gli extra (`pip install .[drive]`) e configura le credenziali.",
    )
    if _column_button(
        c1,
        "Genera README in raw/ (Drive)",
        key="btn_emit_readmes",
        type=emit_btn_type,
        width="stretch",
        disabled=emit_disabled,
    ):
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
                    _safe_rerun()
                except Exception:
                    pass
            except Exception as e:  # pragma: no cover
                st.error(f"Impossibile generare i README: {e}")

    # Colonna 2  -  Arricchimento semantico (estrazione tag)
    base_dir = _workspace_root(slug)
    raw_dir = Path(ensure_within_and_resolve(base_dir, base_dir / "raw"))
    semantic_dir = Path(ensure_within_and_resolve(base_dir, base_dir / "semantic"))

    pdf_count = count_pdfs_safe(raw_dir)
    has_pdfs = pdf_count > 0
    run_tags_fn = cast(Optional[Callable[[str], Any]], _run_tags_update)
    tags_mode = os.getenv("TAGS_MODE", "").strip().lower()
    service_ok = run_tags_fn is not None or tags_mode == "stub"

    open_semantic = _column_button(
        c2,
        "Avvia arricchimento semantico",
        key="btn_semantic_start",
        type="primary",
        width="stretch",
        help=(
            "Estrae keyword dai PDF in raw/, genera/aggiorna tags_raw.csv e lo stub (DB). "
            "Poi puoi rivedere il CSV e abilitare lo YAML."
        ),
    )
    if open_semantic:
        if tags_mode == "stub":
            _open_tags_raw_modal(slug)
        elif run_tags_fn is None:
            LOGGER.error(
                "ui.manage.tags.service_missing",
                extra={"slug": slug, "mode": tags_mode or "default"},
            )
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
                _open_tags_raw_modal(slug)
            except Exception as exc:  # pragma: no cover
                LOGGER.exception(
                    "ui.manage.tags.run_failed",
                    extra={"slug": slug, "error": str(exc)},
                )
                st.error(f"Estrazione tag non riuscita: {exc}")

    if (get_client_state(slug) or "").strip().lower() == "arricchito":
        # Sostituisce anchor HTML interno con API native di navigazione
        if hasattr(st, "page_link"):
            st.page_link("src/ui/pages/semantics.py", label="➡️ Prosegui con l’arricchimento semantico")
        else:
            st.link_button("➡️ Prosegui con l’arricchimento semantico", url="/semantics")
    _render_status_block(pdf_count=pdf_count, service_ok=service_ok, semantic_dir=semantic_dir)

    # Colonna 3 – Scarica da Drive → locale
    download_disabled = _plan_raw_download is None or not (os.getenv("SERVICE_ACCOUNT_FILE") and os.getenv("DRIVE_ID"))
    _render_drive_status_message(
        download_disabled,
        "Download Drive disabilitato: configura `SERVICE_ACCOUNT_FILE` e `DRIVE_ID` o installa gli extra Drive.",
    )
    if _column_button(
        c3,
        "Scarica PDF da Drive → locale",
        key="btn_drive_download",
        type="secondary",
        width="stretch",
        disabled=download_disabled,
    ):

        def _modal() -> None:
            st.write(
                "Questa operazione scarica i file dalle cartelle di Google Drive nelle cartelle locali corrispondenti."
            )
            st.write("Stiamo verificando la presenza di file preesistenti nella cartelle locali.")

            try:
                conflicts, labels = _prepare_download_plan(slug)
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
                        f"{message}\\n"
                        "Potrebbe trattarsi di un errore temporaneo del servizio Drive. "
                        "Riprovare tra qualche minuto e, se il problema persiste, scaricare i PDF manualmente da Drive "
                        "e copiarli nella cartella `raw/`."
                    )
                else:
                    st.error(message)
                return

            _render_download_plan(conflicts, labels)

            cA, cB = st.columns(2)
            if _column_button(cA, "Annulla", key="dl_cancel"):
                return
            if _column_button(cB, "Procedi e scarica", key="dl_proceed", type="primary"):
                if _execute_drive_download(slug, conflicts):
                    _safe_rerun()

        dialog_builder = getattr(st, "dialog", None)
        if callable(dialog_builder):
            open_modal = dialog_builder("Scarica da Google Drive nelle cartelle locali", width="large")
            runner = open_modal(_modal)
            (runner if callable(runner) else _modal)()
        else:
            _modal()
