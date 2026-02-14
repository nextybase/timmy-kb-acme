# SPDX-License-Identifier: GPL-3.0-or-later
# src/ui/pages/manage.py
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Callable, Optional, cast

from pipeline.logging_utils import get_structured_logger
from pipeline.path_utils import ensure_within_and_resolve, read_text_safe
from pipeline.workspace_layout import WorkspaceLayout
from storage.tags_store import import_tags_yaml_to_db
from ui.chrome import render_chrome_then_require
from ui.clients_store import get_all as get_clients
from ui.clients_store import get_state as get_client_state
from ui.clients_store import set_state as set_client_state
from ui.gating import reset_gating_cache as _reset_gating_cache
from ui.manage import _helpers as manage_helpers
from ui.manage import drive as drive_component
from ui.manage import tags as tags_component
from ui.pages.registry import PagePaths
from ui.utils import set_slug
from ui.utils.config import get_drive_env_config, get_tags_env_config
from ui.utils.core import safe_write_text
from ui.utils.route_state import clear_tab, get_slug_from_qp, get_tab, set_tab  # noqa: F401
from ui.utils.status import status_guard
from ui.utils.stubs import get_streamlit
from ui.utils.ui_controls import column_button as _column_button
from ui.utils.workspace import count_markdown_safe, get_ui_workspace_layout

LOGGER = get_structured_logger("ui.manage")
st = get_streamlit()


def _warn_once(key: str, event: str, *, extra: dict[str, object]) -> None:
    if st.session_state.get(key):
        return
    st.session_state[key] = True
    LOGGER.warning(event, extra=extra)


def _safe_rerun() -> None:
    rerun_fn = getattr(st, "rerun", None)
    if callable(rerun_fn):
        try:
            rerun_fn()
        except Exception as exc:  # pragma: no cover - degradazione silenziosa
            LOGGER.warning("ui.manage.safe_rerun_failed", extra={"error": repr(exc)})


_MANAGE_FILE = Path(__file__).resolve()


def _clients_db_path() -> Path:
    """Percorso al registro clienti (supporto test/log)."""
    path = manage_helpers.clients_db_path(_MANAGE_FILE)
    if isinstance(path, Path):
        return path
    return Path(path)


def _load_clients() -> list[dict[str, Any]]:
    """Carica il registro clienti. In strict UI non deve degradare a 'vuoto' in caso di errore."""
    try:
        entries = get_clients()
        result: list[dict[str, Any]] = []
        for entry in entries:
            to_dict = getattr(entry, "to_dict", None)
            if callable(to_dict):
                result.append(cast(dict[str, Any], to_dict()))
            elif isinstance(entry, dict):
                result.append(dict(entry))
            else:
                result.append(vars(entry))
        return result
    except Exception as exc:
        # Strict-only: non "fingiamo" che non esistano clienti (entropia: falso negativo).
        LOGGER.error(
            "ui.manage.clients.load_error",
            extra={"error": str(exc), "path": str(_clients_db_path()), "decision": "STOP"},
        )
        st.error("Impossibile caricare il registro clienti (clients_db). Operazione bloccata in modalità strict.")
        st.caption(f"Dettaglio: {exc}")
        stop_fn = getattr(st, "stop", None)
        if callable(stop_fn):
            stop_fn()
        raise RuntimeError("clients_db non leggibile: abort UI manage in strict mode.") from exc


def _resolve_layout(slug: str) -> WorkspaceLayout | None:
    """Risoluzione cvb per il WorkspaceLayout (fraintende slug)."""
    try:
        return get_ui_workspace_layout(slug, require_drive_env=False)
    except Exception as exc:
        LOGGER.warning("ui.manage.layout_resolution_failed", extra={"slug": slug, "error": str(exc)})
        # Nota: qui ritorniamo None perché il caller fa hard-cut (_render_missing_layout).
        # Tenere la decisione "STOP" nel punto in cui l'UI interrompe realmente.
        return None


def _call_strict(fn: Callable[..., Any], **kwargs: Any) -> Any:
    """Compat per i test esistenti: delega alla versione strict."""
    return manage_helpers.call_strict(fn, logger=LOGGER, **kwargs)


def _render_missing_layout(slug: str) -> None:
    """Messaggio e pulsante per layout assente o non risolvibile."""
    st.error("Impossibile risolvere il layout workspace: il runtime UI è sempre fail-fast e non crea layout impliciti.")
    st.caption(
        "Usa /new per creare un nuovo cliente (bootstrap_client_workspace) oppure rigenera il dummy con "
        "tools/gen_dummy_kb.py prima di aprire la UI."
    )
    stop_fn = getattr(st, "stop", None)
    if callable(stop_fn):
        stop_fn()
    raise RuntimeError(
        "Workspace dummy mancante o incompleto: genera il dummy con tools/gen_dummy_kb.py prima di aprire la UI."
    )


# Services (gestiscono cache e bridging verso i component)
_render_drive_diff = manage_helpers.safe_get("ui.services.drive:render_drive_diff", strict=True)
_invalidate_drive_index = manage_helpers.safe_get("ui.services.drive:invalidate_drive_index", strict=True)
_emit_readmes_for_raw = manage_helpers.safe_get("ui.services.drive_runner:emit_readmes_for_raw", strict=True)

# Download & pre-analisi (nuovo servizio estratto)
_plan_raw_download = manage_helpers.safe_get("ui.services.drive_runner:plan_raw_download", strict=True)
_download_with_progress = manage_helpers.safe_get(
    "ui.services.drive_runner:download_raw_from_drive_with_progress", strict=True
)
_download_simple = manage_helpers.safe_get("ui.services.drive_runner:download_raw_from_drive", strict=True)

# Arricchimento semantico (estrazione tag ? stub + YAML)
_run_tags_update = manage_helpers.safe_get("ui.services.tags_adapter:run_tags_update", strict=True)
# Tag KG Builder (Knowledge Graph dei tag)
_run_tag_kg_builder = manage_helpers.safe_get("ui.services.tag_kg_builder:run_tag_kg_builder", strict=True)


# ---------------- Action handlers ----------------
def _handle_tags_raw_save(
    slug: str,
    content: str,
    csv_path: Path,
    semantic_dir: Path,
) -> bool:
    result = tags_component.handle_tags_raw_save(
        slug,
        content,
        csv_path,
        semantic_dir,
        st=st,
        logger=LOGGER,
        write_fn=safe_write_text,
    )
    return bool(result)


def _enable_tags_stub(
    slug: str,
    semantic_dir: Path,
    yaml_path: Path,
) -> bool:
    result = tags_component.enable_tags_stub(
        slug,
        semantic_dir,
        yaml_path,
        st=st,
        logger=LOGGER,
        set_client_state=set_client_state,
        reset_gating_cache=_reset_gating_cache,
        read_fn=read_text_safe,
        write_fn=safe_write_text,
        import_yaml_fn=import_tags_yaml_to_db,
    )
    return bool(result)


def _enable_tags_service(
    slug: str,
    semantic_dir: Path,
    csv_path: Path,
    yaml_path: Path,
) -> bool:
    result = tags_component.enable_tags_service(
        slug,
        semantic_dir,
        csv_path,
        yaml_path,
        st=st,
        logger=LOGGER,
        set_client_state=set_client_state,
        reset_gating_cache=_reset_gating_cache,
    )
    return bool(result)


def _handle_tags_raw_enable(
    slug: str,
    semantic_dir: Path,
    csv_path: Path,
    yaml_path: Path,
) -> bool:
    tags_cfg = get_tags_env_config()
    run_tags_fn = cast(Optional[Callable[[str], Any]], _run_tags_update)
    result = tags_component.handle_tags_raw_enable(
        slug,
        semantic_dir,
        csv_path,
        yaml_path,
        st=st,
        logger=LOGGER,
        tags_mode=tags_cfg.normalized,
        run_tags_fn=run_tags_fn,
        set_client_state=set_client_state,
        reset_gating_cache=_reset_gating_cache,
        read_fn=read_text_safe,
        write_fn=safe_write_text,
        import_yaml_fn=import_tags_yaml_to_db,
    )
    return bool(result)


# -----------------------------------------------------------
# Modal editor per semantic/tags_reviewed.yaml
# -----------------------------------------------------------
def _open_tags_editor_modal(slug: str, layout: WorkspaceLayout) -> None:
    repo_root_dir = layout.repo_root_dir
    tags_component.open_tags_editor_modal(
        slug,
        repo_root_dir,
        st=st,
        logger=LOGGER,
        column_button=_column_button,
        set_client_state=set_client_state,
        reset_gating_cache=_reset_gating_cache,
        path_resolver=ensure_within_and_resolve,
        read_fn=read_text_safe,
        write_fn=safe_write_text,
        import_yaml_fn=import_tags_yaml_to_db,
    )


def _open_tags_raw_modal(slug: str, layout: WorkspaceLayout) -> None:
    repo_root_dir = layout.repo_root_dir
    tags_cfg = get_tags_env_config()
    tags_component.open_tags_raw_modal(
        slug,
        repo_root_dir,
        st=st,
        logger=LOGGER,
        column_button=_column_button,
        tags_mode=tags_cfg.normalized,
        run_tags_fn=cast(Optional[Callable[[str], Any]], _run_tags_update),
        set_client_state=set_client_state,
        reset_gating_cache=_reset_gating_cache,
        path_resolver=ensure_within_and_resolve,
        read_fn=read_text_safe,
        write_fn=safe_write_text,
        import_yaml_fn=import_tags_yaml_to_db,
    )


# --- piccoli helper per stub di test ---
# helper centralizzati in ui.utils.ui_controls (DRY)


# ---------------- UI ----------------

slug = render_chrome_then_require(allow_without_slug=True)

_cleanup_last = st.session_state.pop("__cleanup_done", None)
if isinstance(_cleanup_last, dict) and _cleanup_last.get("text"):
    level = (_cleanup_last.get("level") or "success").strip().lower()
    if level == "warning":
        st.warning(_cleanup_last["text"])
    elif level == "error":
        st.error(_cleanup_last["text"])
    else:
        st.success(_cleanup_last["text"])

if not slug:
    st.subheader("Seleziona cliente")
    # In strict UI usiamo il loader locale "non-degradabile":
    # evita il caso "errore di I/O -> clients=[] -> 'nessun cliente registrato'".
    clients = _load_clients()

    if not clients:
        st.info("Nessun cliente registrato. Crea il primo dalla pagina **Nuovo cliente**.")
        st.page_link(PagePaths.NEW_CLIENT, label="➕ Crea nuovo cliente")
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
    md_count: int,
    service_ok: bool,
    semantic_dir: Path,
) -> None:
    # status block disabilitato su richiesta: nessuna info/warning aggiuntiva
    return


if slug:
    # Da qui in poi: slug presente → viste operative
    layout = _resolve_layout(slug)
    if layout is None:
        _render_missing_layout(slug)
        st.stop()
    layout = cast(WorkspaceLayout, layout)

    # Unica vista per Drive (Diff)
    if _render_drive_diff is not None:
        try:
            _render_drive_diff(slug)  # usa indice cachato, degrada a vuoto
        except Exception as e:  # pragma: no cover
            LOGGER.exception("ui.manage.drive.diff_failed", extra={"slug": slug, "error": str(e)})
            st.error(f"Errore nella vista Diff: {e}")
    else:
        _warn_once(
            "manage_drive_diff_unavailable",
            "ui.manage.drive.diff_unavailable",
            extra={"slug": slug, "service": "ui.services.drive:render_drive_diff"},
        )
        st.info("Vista Diff non disponibile.")

    # --- Sezioni Gestisci cliente: download, arricchimento, README ---
    client_state = (get_client_state(slug) or "").strip().lower()
    emit_btn_type = "primary" if client_state == "nuovo" else "secondary"

    repo_root_dir = layout.repo_root_dir
    normalized_dir = layout.normalized_dir
    semantic_dir = layout.semantic_dir

    md_count = count_markdown_safe(normalized_dir)
    has_markdown = md_count > 0
    tags_cfg = get_tags_env_config()
    tags_mode = tags_cfg.normalized
    run_tags_fn = cast(Optional[Callable[[str], Any]], _run_tags_update)
    can_stub = tags_cfg.is_stub
    can_run_service = run_tags_fn is not None
    service_ok = can_stub or can_run_service
    prerequisites_ok = has_markdown and service_ok
    semantic_help = (
        "Estrae keyword dai Markdown in normalized/, genera/aggiorna tags_raw.csv e lo stub (DB). "
        "Poi puoi rivedere il CSV e abilitare lo YAML."
        if prerequisites_ok
        else (
            "Disponibile solo quando normalized/ contiene Markdown e il servizio di estrazione è attivo "
            "(puoi usare TAGS_MODE=stub per bypassare il servizio, ma servono comunque Markdown)."
        )
    )

    st.subheader("Azioni sul workspace")
    emit_disabled = _emit_readmes_for_raw is None
    drive_env = get_drive_env_config()
    download_disabled = _plan_raw_download is None or not drive_env.download_ready
    semantic_disabled = not prerequisites_ok

    col_emit, col_download, col_semantic = st.columns(3)

    with col_emit:
        # Contratto: fase C (manuale) della pipeline A/B/C descritta in system/ops/runbook_drive_provisioning.md.
        # Il bottone garantisce fail-fast e publish deterministico della struttura Drive, come previsto dal doc.
        if emit_disabled:
            _warn_once(
                "manage_readme_unavailable",
                "ui.manage.readme.unavailable",
                extra={"slug": slug, "service": "ui.services.drive_runner:emit_readmes_for_raw"},
            )
            st.caption(
                "Provisioning della struttura Drive non disponibile: installa gli extra Drive "
                "e configura le credenziali richieste."
            )
        if _column_button(
            st,
            "Genera struttura Drive",
            key="btn_emit_readmes",
            type="primary",
            width="stretch",
            disabled=emit_disabled,
        ):
            emit_fn = _emit_readmes_for_raw
            if emit_fn is None:
                st.error(
                    "Funzione non disponibile. Abilita gli extra Drive: `pip install .[drive]` "
                    "e configura `SERVICE_ACCOUNT_FILE` / `DRIVE_ID`."
                )
            else:
                try:
                    with status_guard(
                        "Provisiono la struttura Drive e pubblico i README nelle sottocartelle di raw/ su Drive…",
                        expanded=True,
                        error_label="Errore durante l'elaborazione della struttura Drive",
                    ) as status_widget:
                        result = manage_helpers.call_strict(
                            emit_fn,
                            logger=LOGGER,
                            slug=slug,
                            require_env=True,
                        )
                        count = len(result or {})
                        if status_widget is not None and hasattr(status_widget, "update"):
                            status_widget.update(label=f"README pubblicati su Drive: {count}", state="complete")

                    if _invalidate_drive_index is not None:
                        _invalidate_drive_index(slug)
                    st.toast("Struttura Drive generata e README pubblicati su Drive.")
                    _safe_rerun()
                except Exception as e:  # pragma: no cover
                    LOGGER.exception("ui.manage.drive.readme_failed", extra={"slug": slug, "error": str(e)})
                    st.error(f"Impossibile generare la struttura Drive e pubblicare i README: {e}")

    with col_download:
        default_msg = (
            "Download Drive disabilitato: configura `SERVICE_ACCOUNT_FILE` e `DRIVE_ID` o installa gli extra Drive."
        )
        if drive_env.service_account_file and not drive_env.service_account_ok:
            status_msg = f"Percorso SERVICE_ACCOUNT_FILE non valido: {drive_env.service_account_file!r}."
        else:
            status_msg = default_msg
        if download_disabled:
            reason = "service_missing" if _plan_raw_download is None else "config_incomplete"
            _warn_once(
                "manage_drive_download_unavailable",
                "ui.manage.drive.download_unavailable",
                extra={"slug": slug, "reason": reason},
            )
        drive_component.render_drive_status_message(st, download_disabled, status_msg)
        if _column_button(
            st,
            "Scarica PDF da Drive",
            key="btn_drive_download",
            type="secondary",
            width="stretch",
            disabled=download_disabled,
        ):

            def _modal() -> None:
                st.write(
                    "Questa operazione scarica i file dalle cartelle di Google Drive "
                    "nelle cartelle locali corrispondenti."
                )
                st.write("Stiamo verificando la presenza di file preesistenti nelle cartelle locali.")

                try:
                    conflicts, labels = drive_component.prepare_download_plan(
                        _plan_raw_download,
                        slug=slug,
                        logger=LOGGER,
                    )
                except Exception as e:
                    LOGGER.exception(
                        "ui.manage.drive.plan_failed",
                        extra={"slug": slug, "error": str(e)},
                    )
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
                            "Riprovare tra qualche minuto. "
                            "Il problema persiste? Scarica i PDF manualmente da Drive "
                            "e copiali nella cartella `raw/`."
                        )
                    else:
                        st.error(message)
                    return

                drive_component.render_download_plan(st, conflicts, labels)

                overwrite_label = "Sovrascrivi i file locali in conflitto"
                overwrite_help = (
                    "Se attivato, i PDF già presenti verranno riscritti. "
                    "In caso contrario verranno importati solo i file mancanti."
                )
                overwrite_toggle = st.checkbox(
                    overwrite_label,
                    value=False,
                    help=overwrite_help,
                    key=f"drive_overwrite_{slug}",
                    disabled=not conflicts,
                )
                cA, cB = st.columns(2)
                if _column_button(cA, "Annulla", key="dl_cancel"):
                    return
                if _column_button(cB, "Procedi e scarica", key="dl_proceed", type="primary"):
                    if drive_component.execute_drive_download(
                        slug,
                        conflicts,
                        download_with_progress=_download_with_progress,
                        download_simple=_download_simple,
                        invalidate_index=_invalidate_drive_index,
                        logger=LOGGER,
                        st=st,
                        status_guard=status_guard,
                        overwrite_requested=bool(overwrite_toggle),
                    ):
                        _safe_rerun()

            open_modal = st.dialog("Scarica da Google Drive nelle cartelle locali", width="large")
            runner = open_modal(_modal)
            (runner if callable(runner) else _modal)()

    with col_semantic:
        if _column_button(
            st,
            "Arricchimento semantico",
            key="btn_semantic_action",
            type="secondary",
            width="stretch",
            disabled=semantic_disabled,
            help=semantic_help,
        ):
            if not has_markdown:
                st.error(
                    f"Nessun Markdown rilevato in `{normalized_dir}`. "
                    "Esegui raw_ingest o rigenera normalized/ prima di procedere."
                )
            else:
                backend = os.getenv("TAGS_NLP_BACKEND", "spacy").strip().lower() or "spacy"
                backend_label = "SpaCy" if backend == "spacy" else backend.capitalize()
                if tags_mode == "stub":
                    _open_tags_raw_modal(slug, layout=layout)
                elif run_tags_fn is None:
                    LOGGER.error(
                        "ui.manage.tags.service_missing",
                        extra={"slug": slug, "mode": tags_mode or "default"},
                    )
                    st.error("Servizio di estrazione tag non disponibile.")
                else:
                    try:
                        st.info(f"Esecuzione NLP ({backend_label}/euristica) in corso, attendi...")
                        run_tags_fn(slug)
                        _open_tags_raw_modal(slug, layout=layout)
                    except Exception as exc:  # pragma: no cover
                        LOGGER.exception(
                            "ui.manage.tags.run_failed",
                            extra={"slug": slug, "error": str(exc)},
                        )
                        st.error(f"Estrazione tag non riuscita: {exc}")

    # helper sections removed
    if (get_client_state(slug) or "").strip().lower() == "arricchito":
        # Sostituisce anchor HTML interno con API native di navigazione
        link_label = "📌 Prosegui con l'arricchimento semantico"
        st.page_link(PagePaths.SEMANTICS, label=link_label)
    _render_status_block(md_count=md_count, service_ok=service_ok, semantic_dir=semantic_dir)
