# SPDX-License-Identifier: GPL-3.0-or-later
# src/ui/pages/manage.py
from __future__ import annotations

import csv
import io
import re
from pathlib import Path
from typing import Any, Callable, cast

from pipeline.logging_utils import get_structured_logger
from pipeline.path_utils import ensure_within_and_resolve, read_text_safe
from pipeline.workspace_layout import WorkspaceLayout
from storage.tags_store import load_tags_db
from ui.chrome import render_chrome_then_require
from ui.clients_store import get_all as get_clients
from ui.clients_store import get_state as get_client_state
from ui.clients_store import set_state as set_client_state
from ui.gating import compute_gates
from ui.gating import reset_gating_cache as _reset_gating_cache
from ui.gating import visible_page_specs
from ui.manage import _helpers as manage_helpers
from ui.manage import drive as drive_component
from ui.manage import tags as tags_component
from ui.pages.registry import PagePaths
from ui.utils import set_slug
from ui.utils.config import get_drive_env_config
from ui.utils.core import safe_write_text
from ui.utils.route_state import clear_tab, get_slug_from_qp, get_tab, set_tab  # noqa: F401
from ui.utils.status import status_guard
from ui.utils.stubs import get_streamlit
from ui.utils.ui_controls import column_button as _column_button
from ui.utils.workspace import count_markdown_safe, count_pdfs_safe, get_ui_workspace_layout

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
    st.error(
        "Impossibile risolvere il layout workspace: il runtime UI è sempre fail-fast " "e non crea layout impliciti."
    )
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

# Tag onboarding (estrazione/generazione tag semantici)
_run_tag_onboarding = manage_helpers.safe_get("timmy_kb.cli.tag_onboarding:tag_onboarding_main", strict=True)
# Conversione locale RAW -> normalized
_run_raw_ingest = manage_helpers.safe_get("timmy_kb.cli.raw_ingest:run_raw_ingest", strict=True)


# ---------------- Action handlers ----------------
def _save_tags_draft_csv(
    slug: str,
    content: str,
    csv_path: Path,
    semantic_dir: Path,
) -> bool:
    result = tags_component.save_tags_draft_csv(
        slug,
        content,
        csv_path,
        semantic_dir,
        st=st,
        logger=LOGGER,
        write_fn=safe_write_text,
    )
    return bool(result)


def _open_tags_draft_modal(slug: str, layout: WorkspaceLayout) -> None:
    repo_root_dir = layout.repo_root_dir
    tags_component.open_tags_draft_modal(
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


def _render_drive_download_report_box() -> None:
    report = st.session_state.get("__drive_download_last_report")
    if not isinstance(report, dict):
        return
    status = str(report.get("status") or "").strip().lower()
    if status not in {"ok", "partial", "error"}:
        return

    icon_map = {
        "ok": "🟢",
        "partial": "🟡",
        "error": "🔴",
    }
    label_map = {
        "ok": "completato",
        "partial": "completato con avvisi",
        "error": "fallito",
    }
    icon = icon_map.get(status, "⚪")
    label = label_map.get(status, "stato non disponibile")
    title = f"{icon} Report download da Drive: {label}"

    def _sanitize_reason(raw: str) -> str:
        text = raw.strip()
        low = text.lower()
        if "not downloadable" in low or "only files with binary content can be downloaded" in low:
            return "File non scaricabile direttamente da Drive (probabile file Google Docs)."
        if "mime" in low:
            return "Formato file non supportato per questo download."
        if "403" in low or "forbidden" in low:
            return "Permessi insufficienti per scaricare il file."
        if "404" in low or "not found" in low:
            return "File non trovato su Drive."
        if "429" in low or "rate limit" in low:
            return "Limite richieste raggiunto: riprova tra poco."
        if "500" in low or "503" in low:
            return "Errore temporaneo del servizio Drive."
        return "Errore durante il download del file."

    def _extract_file_issues(message: str) -> list[tuple[str, str]]:
        details = message
        if "Dettagli:" in details:
            details = details.split("Dettagli:", 1)[1]
        chunks = [piece.strip() for piece in re.split(r";\s*", details) if piece.strip()]
        issues: list[tuple[str, str]] = []
        file_pattern = re.compile(
            r"(?P<file>(?:[A-Za-z0-9_.-]+/)*[A-Za-z0-9_.-]+\.[A-Za-z0-9_.-]+)\s*:\s*(?P<reason>.+)"
        )
        for chunk in chunks:
            match = file_pattern.search(chunk)
            if not match:
                continue
            file_name = match.group("file").strip()
            reason_raw = match.group("reason").strip()
            issues.append((file_name, _sanitize_reason(reason_raw)))
        return issues

    with st.expander(title, expanded=False):
        downloaded_count = report.get("downloaded_count")
        overwrite = report.get("overwrite")
        message = str(report.get("message") or "").strip()

        if isinstance(downloaded_count, int):
            st.write(f"File nuovi/aggiornati: **{downloaded_count}**")
        if isinstance(overwrite, bool):
            st.write(f"Sovrascrittura file esistenti: **{'Si' if overwrite else 'No'}**")
        if message:
            issues = _extract_file_issues(message)
            if issues:
                st.write("File con problemi:")
                st.markdown("\n".join(f"- `{name}`: {reason}" for name, reason in issues))
            else:
                st.write(_sanitize_reason(message))


def _render_tag_onboarding_report_box(slug: str, layout: WorkspaceLayout, client_state: str) -> None:
    if client_state == "finito":
        return

    semantic_dir = layout.semantic_dir
    tags_raw_csv = semantic_dir / "tags_raw.csv"
    tags_db = semantic_dir / "tags.db"
    has_tags_raw = tags_raw_csv.exists()
    has_tags_db_file = tags_db.exists()

    def _csv_tag_set() -> set[str]:
        if not has_tags_raw:
            return set()
        try:
            raw_text = read_text_safe(semantic_dir, tags_raw_csv, encoding="utf-8") or ""
            reader = csv.reader(io.StringIO(raw_text))
            header = next(reader, None)
            if not header or "suggested_tags" not in header:
                return set()
            idx = header.index("suggested_tags")
            found: set[str] = set()
            for row in reader:
                if idx >= len(row):
                    continue
                for token in (row[idx] or "").split(","):
                    tag = token.strip().lower()
                    if tag:
                        found.add(tag)
            return found
        except Exception:
            return set()

    def _db_tag_set() -> set[str]:
        if not has_tags_db_file:
            return set()
        try:
            payload = load_tags_db(str(tags_db))
            tags = payload.get("tags") if isinstance(payload, dict) else None
            if not isinstance(tags, list):
                return set()
            found: set[str] = set()
            for item in tags:
                if not isinstance(item, dict):
                    continue
                name = str(item.get("name") or "").strip().lower()
                if name:
                    found.add(name)
            return found
        except Exception:
            return set()

    csv_tags = _csv_tag_set()
    db_tags = _db_tag_set()
    db_ready = bool(csv_tags) and csv_tags.issubset(db_tags)
    db_status = "pronto" if db_ready else "vuoto"

    report = st.session_state.get("__tag_onboarding_last_report")
    if not isinstance(report, dict):
        if not has_tags_raw:
            return
        report = {
            "status": "ok",
        }

    status = str(report.get("status") or "").strip().lower()
    if status not in {"ok", "error"}:
        status = "ok" if has_tags_raw else "error"
    icon = "🟢" if status == "ok" else "🔴"
    label = "completato" if status == "ok" else "fallito"
    title = f"{icon} Report creazione tag semantici: {label}"
    with st.expander(title, expanded=(status == "error")):
        c1, c2 = st.columns(2)
        with c1:
            if _column_button(st, "Edit", key=f"btn_edit_tags_raw_{slug}", type="secondary", width="stretch"):
                _open_tags_draft_modal(slug, layout)
        with c2:
            st.write("")
        st.markdown("Output:")
        st.markdown(f"- `tags_raw.csv`: {'presente' if has_tags_raw else 'mancante'}")
        st.markdown(f"- `tags.db`: {db_status}")


def _is_page_visible(page_path: str) -> bool:
    """True se la pagina e' disponibile nella navigazione corrente (gate inclusi)."""
    try:
        groups = visible_page_specs(compute_gates())
    except Exception as exc:  # pragma: no cover - difesa runtime UI
        LOGGER.warning(
            "ui.manage.page_visibility_check_failed",
            extra={"page_path": page_path, "error": str(exc)},
        )
        return False
    for specs in groups.values():
        for spec in specs:
            if getattr(spec, "path", None) == page_path:
                return True
    return False


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
    readme_done_state = client_state in {"pronto", "arricchito", "finito"}

    repo_root_dir = layout.repo_root_dir
    normalized_dir = layout.normalized_dir
    semantic_dir = layout.semantic_dir

    md_count = count_markdown_safe(normalized_dir)
    has_markdown = md_count > 0
    raw_pdf_count = count_pdfs_safe(layout.raw_dir, use_cache=True, cache_ttl_s=3.0)
    has_raw_pdfs = raw_pdf_count > 0
    service_ok = _run_raw_ingest is not None
    prerequisites_ok = has_raw_pdfs and service_ok
    semantic_help = (
        "Converte i PDF in raw/ in Markdown in normalized/."
        if prerequisites_ok
        else "Disponibile solo quando raw/ contiene PDF e la conversione raw_ingest è disponibile."
    )

    st.subheader("Azioni sul workspace")
    emit_disabled = _emit_readmes_for_raw is None
    drive_env = get_drive_env_config()
    download_disabled = _plan_raw_download is None or not drive_env.download_ready
    semantic_disabled = not prerequisites_ok
    download_status = str(st.session_state.get("__drive_download_last_status") or "").strip().lower()
    show_download_report_box = download_status in {"ok", "partial", "error"}

    col_emit, col_download, col_semantic = st.columns(3)

    with col_emit:
        # Contratto: fase C (manuale) della pipeline A/B/C descritta in system/ops/runbook_drive_provisioning.md.
        # Il bottone garantisce fail-fast e publish deterministico della struttura Drive, come previsto dal doc.
        if show_download_report_box:
            _render_drive_download_report_box()
        if readme_done_state:
            emit_disabled = True
        if emit_disabled and not readme_done_state:
            _warn_once(
                "manage_readme_unavailable",
                "ui.manage.readme.unavailable",
                extra={"slug": slug, "service": "ui.services.drive_runner:emit_readmes_for_raw"},
            )
            st.caption(
                "Provisioning della struttura Drive non disponibile: installa gli extra Drive "
                "e configura le credenziali richieste."
            )
        emit_label = "✅ Genera struttura Drive" if readme_done_state else "Genera struttura Drive"
        if _column_button(
            st,
            emit_label,
            key="btn_emit_readmes",
            type=emit_btn_type,
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
                    if client_state == "nuovo":
                        set_client_state(slug, "pronto")
                        _reset_gating_cache(slug)
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
            "Converti PDF",
            key="btn_convert_pdf_action",
            type="secondary",
            width="stretch",
            disabled=semantic_disabled,
            help=semantic_help,
        ):
            if not has_raw_pdfs:
                st.error(
                    f"Nessun PDF rilevato in `{layout.raw_dir}`. "
                    "Scarica o copia i PDF nelle sottocartelle di raw/ prima di procedere."
                )
            elif _run_raw_ingest is None:
                st.error("Servizio di conversione non disponibile (raw_ingest).")
            else:
                try:
                    with status_guard(
                        "Converto i PDF da raw/ a normalized...",
                        expanded=True,
                        error_label="Errore durante la conversione PDF",
                    ):
                        manage_helpers.call_strict(
                            _run_raw_ingest,
                            logger=LOGGER,
                            slug=slug,
                            source="local",
                            local_path=str(layout.raw_dir),
                            non_interactive=True,
                        )
                    st.toast("Conversione completata: normalized/ aggiornato.")
                    _safe_rerun()
                except Exception as exc:  # pragma: no cover
                    LOGGER.exception(
                        "ui.manage.raw_ingest.run_failed",
                        extra={"slug": slug, "error": str(exc)},
                    )
                    st.error(f"Conversione PDF non riuscita: {exc}")

    kg_help = (
        "Esegue tag_onboarding su `normalized/`: genera `semantic/tags_raw.csv` "
        "e prepara la validazione verso `semantic/tags.db`."
    )
    kg_disabled = _run_tag_onboarding is None or client_state not in {"pronto", "arricchito"} or not has_markdown
    if _run_tag_onboarding is None:
        kg_help = "Tag onboarding non disponibile: servizio `timmy_kb.cli.tag_onboarding` mancante."
    elif client_state not in {"pronto", "arricchito"}:
        kg_help = "Disponibile dallo stato cliente 'pronto' in poi."
    elif not has_markdown:
        kg_help = "Disponibile dopo la conversione PDF (servono file Markdown in `normalized/`)."

    if _column_button(
        st,
        "Crea Tag semantici",
        key="btn_build_kg_action",
        type="secondary",
        width="stretch",
        disabled=kg_disabled,
        help=kg_help,
    ):
        try:
            with status_guard(
                "Genero tag semantici da `normalized/` (CSV + DB)...",
                expanded=True,
                error_label="Errore durante la creazione dei tag semantici",
            ):
                manage_helpers.call_strict(
                    _run_tag_onboarding,
                    logger=LOGGER,
                    slug=slug,
                    non_interactive=True,
                    proceed_after_csv=True,
                )
            semantic_dir = layout.semantic_dir
            expected_outputs = [
                semantic_dir / "tags_raw.csv",
            ]
            output_rows = [f"`{p.name}`: {'presente' if p.exists() else 'mancante'}" for p in expected_outputs]
            st.session_state["__tag_onboarding_last_report"] = {
                "status": "ok",
                "outputs": output_rows,
                "details": "Bozza tag creata: usa Edit -> Valida per confermare i tag e validare il vocabolario.",
            }
            st.toast("Bozza tag creata (`tags_raw.csv`). Usa Edit -> Valida per creare `tags.db`.")
            _safe_rerun()
        except Exception as exc:  # pragma: no cover
            LOGGER.exception(
                "ui.manage.tag_onboarding.run_failed",
                extra={"slug": slug, "error": str(exc)},
            )
            st.session_state["__tag_onboarding_last_report"] = {
                "status": "error",
                "outputs": [],
                "details": str(exc),
            }
            st.error(
                "Creazione tag semantici non riuscita " f"(attesi: `semantic/tags_raw.csv`, `semantic/tags.db`): {exc}"
            )

    _render_tag_onboarding_report_box(slug, layout, client_state)

    # helper sections removed
    if client_state in {"arricchito", "finito"} and _is_page_visible(PagePaths.SEMANTICS):
        # Sostituisce anchor HTML interno con API native di navigazione
        link_label = "📌 Prosegui con l'arricchimento semantico"
        st.page_link(PagePaths.SEMANTICS, label=link_label)
    _render_status_block(md_count=md_count, service_ok=service_ok, semantic_dir=semantic_dir)
