"""Tab Home e helper condivisi per l'onboarding Streamlit."""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any, Callable, Dict, Optional, cast

import yaml

from pipeline.context import ClientContext
from pipeline.exceptions import ConfigError, InvalidSlug
from pipeline.file_utils import safe_write_text
from pipeline.path_utils import ensure_within, ensure_within_and_resolve, read_text_safe, validate_slug
from pipeline.yaml_utils import clear_yaml_cache, yaml_read
from pre_onboarding import ensure_local_workspace_for_ui
from src.ui.app_core.logging import _setup_logging
from ui.clients_store import ClientEntry, ensure_db, load_clients, set_state, upsert_client
from ui.services.drive_runner import emit_readmes_for_raw
from ui.services.vision_provision import provision_from_vision
from ui.utils.branding import render_brand_header
from ui.utils.logging import enrich_log_extra, show_success

try:
    import streamlit as st
except Exception:  # pragma: no cover
    st = None

try:
    from streamlit.runtime.scriptrunner_utils.exceptions import RerunException
except Exception:  # pragma: no cover

    class RerunException(Exception):  # type: ignore[no-redef]
        def __init__(self, *args: Any, rerun_data: Any | None = None, **kwargs: Any) -> None:
            super().__init__(*args, **kwargs)
            self.rerun_data = rerun_data


try:
    from pipeline.drive_utils import (
        create_drive_folder,
        create_drive_structure_from_yaml,
        create_local_base_structure,
        get_drive_service,
        upload_config_to_drive_folder,
    )
except Exception:  # pragma: no cover
    create_drive_folder = None
    create_drive_structure_from_yaml = None
    create_local_base_structure = None
    get_drive_service = None
    upload_config_to_drive_folder = None

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = REPO_ROOT / "config"
OUTPUT_ROOT = REPO_ROOT / "output"
BASE_CONFIG = CONFIG_DIR / "config.yaml"

DialogDecorator = Callable[[Callable[[], None]], Callable[[], None]]
DialogFactory = Callable[[str], DialogDecorator]
ProvisionHandler = Callable[..., Dict[str, Any]]

__all__ = [
    "render_home",
    "_safe_streamlit_rerun",
    "_render_header",
    "_render_landing",
    "_render_new_client_block",
    "_workspace_dir_for",
    "_mapping_path",
    "_cartelle_path",
    "_tags_reviewed_path",
    "_render_ready",
]


def _safe_streamlit_rerun(log: Optional[logging.Logger] = None) -> None:
    """Richiede un rerun di Streamlit senza propagare errori non gestiti."""
    if st is None:
        if log:
            log.info("ui.rerun_unavailable_streamlit_none")
        return
    rerun_fn = getattr(st, "rerun", None)
    if not callable(rerun_fn):
        if log:
            log.info("ui.rerun_unavailable_no_callable")
        return
    try:
        rerun_fn()
        if log:
            log.debug("ui.rerun_invoked")
    except RerunException:
        raise
    except Exception as exc:  # pragma: no cover
        if log:
            log.info("ui.rerun_failed", extra={"error": str(exc)})


def _ui_dialog(title: str, body_fn: Callable[[], None]) -> None:
    """Compat layer per dialog/expander in Streamlit."""
    if st is None:
        return
    dlg_raw = getattr(st, "dialog", None)
    dlg = cast(Optional[DialogFactory], dlg_raw)
    if dlg is not None:
        decorator: DialogDecorator = dlg(title)

        @decorator
        def _show() -> None:
            body_fn()

        _show()
        return

    with st.expander(title, expanded=True):
        body_fn()


def _render_gate_resolution(
    slug: str,
    workspace_dir: Path,
    logger: logging.Logger,
    reason: str,
) -> None:
    """Mostra un dialog per gestire artefatti Vision già presenti."""
    if st is None:
        return

    gate_state = st.session_state.setdefault("vision_gate_reasons", {})
    busy_key = f"vision_gate_busy_{slug}"
    choice_key = f"vision_gate_choice_{slug}"
    upload_key = f"vision_gate_upl_{slug}"
    busy = bool(st.session_state.get(busy_key))

    def _set_busy(flag: bool) -> None:
        st.session_state[busy_key] = flag

    def _clear_gate_state() -> None:
        gate_state.pop(slug, None)
        st.session_state.pop(busy_key, None)
        st.session_state.pop(choice_key, None)
        st.session_state.pop(upload_key, None)

    def _trigger_rerun() -> None:
        try:
            _safe_streamlit_rerun()
        except Exception:
            pass

    def _handle_success(result: Dict[str, Any] | None, message: str) -> None:
        handled_new = _apply_new_client_gate_success(slug, workspace_dir, logger, result, message)
        if not handled_new:
            st.session_state["init_result"] = result or {}
            show_success(message)
            if "phase" in st.session_state:
                st.session_state["phase"] = "ready_to_open"
        _clear_gate_state()
        _set_busy(False)
        _trigger_rerun()

    def _body() -> None:
        st.warning(reason)
        choice = st.radio(
            "Come vuoi procedere?",
            (
                "Rigenera usando lo stesso PDF",
                "Carica un nuovo PDF e rigenera",
                "Annulla e apri gli YAML",
            ),
            key=choice_key,
        )

        if choice == "Rigenera usando lo stesso PDF":
            if st.button("Procedi", type="primary", width="stretch", disabled=busy):
                _set_busy(True)
                try:
                    with st.spinner("Rigenerazione in corso..."):
                        ctx = ClientContext.load(slug=slug, interactive=False, require_env=False, run_id=None)
                        pdf_path = cast(Path, ensure_within_and_resolve(workspace_dir, _pdf_path(workspace_dir)))
                        result = provision_from_vision(
                            ctx,
                            logger,
                            slug=slug,
                            pdf_path=pdf_path,
                            force=True,
                        )
                        _handle_success(result, "YAML rigenerati dal PDF esistente.")
                except ConfigError as exc:
                    _set_busy(False)
                    st.error(str(exc))

        elif choice == "Carica un nuovo PDF e rigenera":
            uploaded = st.file_uploader(
                "Seleziona il nuovo VisionStatement.pdf",
                type=["pdf"],
                key=upload_key,
            )
            if uploaded is not None and st.button("Carica e rigenera", type="primary", width="stretch", disabled=busy):
                data = uploaded.read()
                if not data:
                    st.warning("Il file caricato è vuoto. Riprova.")
                else:
                    _set_busy(True)
                    try:
                        with st.spinner("Caricamento e rigenerazione in corso..."):
                            try:
                                config_data = _load_config_data(workspace_dir)
                            except ConfigError:
                                config_data = {}
                            client_name = cast(str, (config_data.get("client_name") or slug))
                            ensure_local_workspace_for_ui(
                                slug=slug,
                                client_name=client_name,
                                vision_statement_pdf=data,
                            )
                            ctx = ClientContext.load(slug=slug, interactive=False, require_env=False, run_id=None)
                            pdf_path = cast(Path, ensure_within_and_resolve(workspace_dir, _pdf_path(workspace_dir)))
                            result = provision_from_vision(
                                ctx,
                                logger,
                                slug=slug,
                                pdf_path=pdf_path,
                                force=False,
                            )
                            _handle_success(result, "YAML rigenerati dal nuovo PDF.")
                    except ConfigError as exc:
                        _set_busy(False)
                        st.error(str(exc))

        else:
            if st.button("Apri YAML", type="primary", width="stretch", disabled=busy):
                _set_busy(True)
                try:
                    with st.spinner("Apertura YAML in corso..."):
                        existing = st.session_state.get("init_result") or {}
                        _handle_success(existing, "YAML disponibili per la revisione.")
                finally:
                    _set_busy(False)

    _ui_dialog("Artefatti già generati", _body)


def _render_ready(slug: str, workspace_dir: Path, logger: logging.Logger) -> None:
    """Compat layer per la schermata ready: chiede conferma prima di rigenerare gli YAML."""
    if st is None:
        return

    init_result = st.session_state.get("init_result") or {}
    st.header("Workspace pronto")
    if init_result:
        st.json(init_result, expanded=False)

    confirm_key = f"ui.ready.confirm.{slug}"
    confirm = st.checkbox(
        "Confermo di voler rigenerare gli YAML Vision",
        key=confirm_key,
        value=bool(st.session_state.get(confirm_key, False)),
    )
    st.session_state[confirm_key] = confirm

    if not st.button(
        "Rigenera YAML",
        type="primary",
        key=f"ui.ready.regenera.{slug}",
        width="stretch",
    ):
        return

    if not confirm:
        st.warning("Devi confermare per procedere con la rigenerazione.")
        return

    provision_impl: ProvisionHandler = provision_from_vision
    app_module = sys.modules.get("src.ui.app")
    if app_module is not None:
        override = getattr(app_module, "provision_from_vision", None)
        if callable(override):
            provision_impl = cast(ProvisionHandler, override)

    try:
        ctx = ClientContext.load(slug=slug, interactive=False, require_env=False, run_id=None)
        pdf_path = cast(Path, ensure_within_and_resolve(workspace_dir, _pdf_path(workspace_dir)))
        result = provision_impl(
            ctx,
            logger,
            slug=slug,
            pdf_path=pdf_path,
            force=True,
        )
    except ConfigError as exc:
        st.error(str(exc))
        logger.warning("ui.ready.regenerate_failed", extra={"slug": slug, "error": str(exc)})
        return

    st.session_state["init_result"] = result or {}
    st.success("YAML rigenerati dal PDF esistente.")
    logger.info("ui.ready.regenerate_succeeded", extra={"slug": slug})


def _apply_new_client_gate_success(
    slug: str,
    workspace_dir: Path,
    logger: logging.Logger,
    result: Dict[str, Any] | None,
    success_message: str,
) -> bool:
    """Gestisce gli stati UI quando il gate Vision viene risolto positivamente."""
    if st is None:
        return False
    slug_candidates = {
        (st.session_state.get("ui.new.slug") or "").strip(),
        (st.session_state.get("ui.new.slug_effective") or "").strip(),
    }
    slug_candidates = {s for s in slug_candidates if s}
    if slug not in slug_candidates:
        return False
    try:
        mapping_rel = _mapping_path(workspace_dir)
        cartelle_rel = _cartelle_path(workspace_dir)
        mapping_text = _load_yaml_text(workspace_dir, mapping_rel)
        cartelle_text = _load_yaml_text(workspace_dir, cartelle_rel)
    except ConfigError as exc:
        st.error(str(exc))
        logger.warning("ui.new.vision_refresh_failed", extra={"slug": slug, "error": str(exc)})
        return True

    yaml_paths: Dict[str, Any] = {}
    if isinstance(result, dict):
        yaml_paths = cast(Dict[str, Any], result.get("yaml_paths") or {})

    st.session_state["ui.new.mapping_text"] = mapping_text
    st.session_state["ui.new.cartelle_text"] = cartelle_text
    st.session_state["ui.new.yaml_paths"] = yaml_paths
    st.session_state["ui.new.workspace_dir"] = str(workspace_dir)
    st.session_state["ui.new.slug_effective"] = slug
    nome_val = (
        st.session_state.get("ui.new.nome") or st.session_state.get("ui.new.nome_effective") or slug
    ).strip() or slug
    st.session_state["ui.new.nome_effective"] = nome_val
    st.session_state["ui.new.init_done"] = True
    st.session_state.setdefault("ui.new.workspace_created", False)
    st.session_state["ui.busy.init"] = False
    show_success(success_message)
    logger.info("ui.new.vision_completed_force", extra={"slug": slug})
    try:
        set_state(slug, "nuovo")
        toast_fn = getattr(st, "toast", None)
        if callable(toast_fn):
            toast_fn("Stato cliente aggiornato a 'nuovo'.")
    except Exception as state_exc:  # pragma: no cover
        logger.warning("ui.state.update_failed", extra={"slug": slug, "error": str(state_exc)})
    return True


def _update_client_state(logger: logging.Logger, slug: str, stato: str) -> bool:
    """Prova ad aggiornare lo stato del cliente senza interrompere la UI."""
    try:
        set_state(slug, stato)
    except Exception as exc:  # pragma: no cover
        logger.warning(
            "ui.client_state_update_failed",
            extra=enrich_log_extra({"slug": slug, "target_state": stato, "error": str(exc)}),
        )
        return False
    logger.info("ui.client_state_updated", extra=enrich_log_extra({"slug": slug, "state": stato}))
    return True


def _current_client_state(slug: Optional[str]) -> str | None:
    if not slug:
        return None
    try:
        entries: list[ClientEntry] = load_clients()
    except Exception:
        return None
    for entry in entries:
        if entry.slug == slug:
            return cast(str, entry.stato)
    return None


def _render_header(slug: Optional[str]) -> None:
    """Renderizza l'header brandizzato con le info cliente attivo."""
    if st is None:
        return

    state = _current_client_state(slug) if slug else None
    state_label = (state or "n/d").upper() if slug else None

    subtitle: str | None
    if slug:
        subtitle = f"Cliente attivo: `{slug}` - stato `{state_label}`"
    else:
        subtitle = "Nessun cliente attivo. Crea o seleziona un cliente per iniziare."

    render_brand_header(
        st_module=st,
        repo_root=REPO_ROOT,
        subtitle=subtitle,
        include_anchor=True,
    )

    if not slug:
        return

    try:
        with st.sidebar:
            st.markdown("### Cliente")
            st.write(f"**Slug**: `{slug}`")
            st.write(f"**Stato**: `{state_label}`")
            st.divider()
            st.markdown("[Vai a Configurazione](#section-yaml)")
            st.markdown("[Vai a Google Drive](#section-drive)")
            st.markdown("[Vai a Semantica](#section-semantic)")
    except Exception:
        pass


def _workspace_dir_for(slug: str) -> Path:
    return OUTPUT_ROOT / f"timmy-kb-{slug}"


def _config_path(workspace_dir: Path) -> Path:
    return workspace_dir / "config" / "config.yaml"


def _semantic_dir(workspace_dir: Path) -> Path:
    return workspace_dir / "semantic"


def _mapping_path(workspace_dir: Path) -> Path:
    return _semantic_dir(workspace_dir) / "semantic_mapping.yaml"


def _cartelle_path(workspace_dir: Path) -> Path:
    return _semantic_dir(workspace_dir) / "cartelle_raw.yaml"


def _tags_reviewed_path(workspace_dir: Path) -> Path:
    return _semantic_dir(workspace_dir) / "tags_reviewed.yaml"


def _pdf_path(workspace_dir: Path) -> Path:
    return workspace_dir / "config" / "VisionStatement.pdf"


def _normalize_cartelle_yaml(cartelle_text: str, slug: str) -> str:
    """Garantisce che cartelle_raw.yaml esponga il nodo 'raw' allineato al nuovo formato."""
    try:
        data = yaml.safe_load(cartelle_text) or {}
    except Exception:
        return cartelle_text

    if not isinstance(data, dict):
        data = {}

    context = data.get("context")
    if not isinstance(context, dict):
        context = {}
    if slug:
        context.setdefault("slug", slug)
    data["context"] = context

    if isinstance(data.get("raw"), dict) and data["raw"]:
        data.pop("folders", None)
        return yaml.safe_dump(data, sort_keys=False, allow_unicode=True)

    raw_mapping: dict[str, dict[str, Any]] = {}
    folders = data.get("folders")
    if isinstance(folders, list):
        for entry in folders:
            if not isinstance(entry, dict):
                continue
            key = str(entry.get("key") or entry.get("name") or "").strip()
            if not key:
                continue
            raw_mapping[key] = {}
    data["raw"] = raw_mapping
    data.pop("folders", None)
    return yaml.safe_dump(data, sort_keys=False, allow_unicode=True)


def _load_yaml_text_optional(workspace_dir: Path, rel: Path) -> str | None:
    try:
        return _load_yaml_text(workspace_dir, rel)
    except ConfigError:
        return None


def _copy_base_config(workspace_dir: Path, slug: str, logger: logging.Logger) -> Path:
    config_dir = cast(Path, ensure_within_and_resolve(workspace_dir, workspace_dir / "config"))
    config_dir.mkdir(parents=True, exist_ok=True)
    target = cast(Path, ensure_within_and_resolve(config_dir, config_dir / "config.yaml"))
    if not BASE_CONFIG.exists():
        raise ConfigError(f"File di configurazione base non trovato: {BASE_CONFIG}")
    if not target.exists():
        content = read_text_safe(REPO_ROOT, BASE_CONFIG, encoding="utf-8")
        safe_write_text(target, content, encoding="utf-8", atomic=True)
        logger.info("ui.config.copied", extra={"slug": slug, "path": str(target)})
    return target


def _render_debug_expander(workspace_dir: Path) -> None:
    """Mostra un expander 'Debug' con eventuali file di diagnostica Vision."""
    if st is None:
        return
    try:
        sem_dir = cast(Path, ensure_within_and_resolve(workspace_dir, _mapping_path(workspace_dir).parent))
        resp_path = cast(Path, ensure_within_and_resolve(sem_dir, sem_dir / ".vision_last_response.json"))
        err_path = cast(Path, ensure_within_and_resolve(sem_dir, sem_dir / ".vision_last_error.txt"))
    except ConfigError:
        with st.expander("Debug", expanded=False):
            st.info("Nessun debug disponibile")
        return

    shown = False
    with st.expander("Debug", expanded=False):
        if resp_path.exists():
            try:
                content = read_text_safe(workspace_dir, resp_path, encoding="utf-8")
                st.caption(f"File: `{resp_path}`")
                st.code(content, language="json")
                shown = True
            except Exception:
                pass
        if err_path.exists():
            try:
                content = read_text_safe(workspace_dir, err_path, encoding="utf-8")
                st.caption(f"File: `{err_path}`")
                st.code(content, language="text")
                shown = True
            except Exception:
                pass
        if not shown:
            st.info("Nessun debug disponibile")


def _load_config_data(workspace_dir: Path) -> Dict[str, Any]:
    cfg_path = _config_path(workspace_dir)
    data = yaml_read(workspace_dir, cfg_path)
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ConfigError("config.yaml non valido: atteso un dizionario")
    return data


def _load_yaml_text(workspace_dir: Path, rel: Path) -> str:
    target = cast(Path, ensure_within_and_resolve(workspace_dir, rel))
    if not target.exists():
        raise ConfigError(f"File non trovato: {target}")
    return cast(str, read_text_safe(workspace_dir, target, encoding="utf-8"))


def _validate_yaml_dict(content: str, label: str) -> Dict[str, Any]:
    try:
        parsed = yaml.safe_load(content) or {}
    except yaml.YAMLError as exc:
        raise ConfigError(f"{label}: YAML non valido ({exc})")
    if not isinstance(parsed, dict):
        raise ConfigError(f"{label}: atteso un dizionario alla radice.")
    return parsed


def _save_yaml_text(workspace_dir: Path, rel: Path, content: str) -> None:
    target = cast(Path, ensure_within_and_resolve(workspace_dir, rel))
    safe_write_text(target, content, encoding="utf-8", atomic=True)
    clear_yaml_cache()


def _run_create_local_structure(slug: str, workspace_dir: Path, logger: logging.Logger) -> None:
    if create_local_base_structure is None:
        raise RuntimeError("Funzionalità locali non disponibili: installa i moduli 'pipeline.drive_utils'.")
    ctx = ClientContext.load(slug=slug, interactive=False, require_env=False, run_id=None)
    cartelle = cast(Path, ensure_within_and_resolve(workspace_dir, _cartelle_path(workspace_dir)))
    create_local_base_structure(ctx, cartelle)
    logger.info("ui.workspace.local_structure", extra=enrich_log_extra({"slug": slug, "yaml": str(cartelle)}))


def _run_drive_structure(slug: str, workspace_dir: Path, logger: logging.Logger) -> Dict[str, str]:
    if not (
        get_drive_service and create_drive_folder and create_drive_structure_from_yaml and upload_config_to_drive_folder
    ):
        raise RuntimeError(
            "Funzionalità Drive non disponibili: installa gli extra o configura i servizi (pipeline.drive_utils)."
        )

    ctx = ClientContext.load(slug=slug, interactive=False, require_env=True, run_id=None)
    service = get_drive_service(ctx)
    drive_parent_id = ctx.env.get("DRIVE_ID")
    if not drive_parent_id:
        raise ConfigError("Variabile DRIVE_ID non impostata nell'ambiente.")
    cartelle = cast(Path, ensure_within_and_resolve(workspace_dir, _cartelle_path(workspace_dir)))
    redact = bool(getattr(ctx, "redact_logs", False))
    client_folder_id = create_drive_folder(service, slug, parent_id=drive_parent_id, redact_logs=redact)
    created_map = cast(
        Dict[str, str],
        create_drive_structure_from_yaml(service, cartelle, client_folder_id, redact_logs=redact),
    )
    upload_config_to_drive_folder(service, ctx, parent_id=client_folder_id, redact_logs=redact)
    logger.info(
        "ui.workspace.drive_structure",
        extra={"slug": slug, "client_folder_id": client_folder_id, "raw": created_map.get("raw")},
    )
    return created_map


def _run_generate_readmes(slug: str, logger: logging.Logger) -> Dict[str, str]:
    result = cast(
        Dict[str, str],
        emit_readmes_for_raw(
            slug=slug,
            base_root=OUTPUT_ROOT,
            require_env=True,
            ensure_structure=True,
        ),
    )
    logger.info("ui.workspace.readmes", extra=enrich_log_extra({"slug": slug, "count": len(result)}))
    return result


def _open_workspace(slug: str, workspace_dir: Path, logger: logging.Logger) -> None:
    try:
        cartelle_rel = _cartelle_path(workspace_dir)
        current_text = _load_yaml_text(workspace_dir, cartelle_rel)
        normalized = _normalize_cartelle_yaml(current_text, slug)
        if normalized != current_text:
            _save_yaml_text(workspace_dir, cartelle_rel, normalized)
            try:
                logger.info("ui.cartelle.normalized", extra={"slug": slug})
            except Exception:
                pass
    except ConfigError:
        pass

    client_yaml = workspace_dir / "semantic" / "cartelle_raw.yaml"
    global_yaml = CONFIG_DIR / "cartelle_raw.yaml"
    backup_yaml = CONFIG_DIR / "cartelle_raw.yaml.ui.bak"

    with st.spinner("Creazione workspace..."):
        swapped = False
        try:
            ensure_within(CONFIG_DIR, global_yaml)
            ensure_within(CONFIG_DIR, backup_yaml)
            ensure_within(workspace_dir, client_yaml)

            if client_yaml.is_file():
                client_text = read_text_safe(workspace_dir, client_yaml, encoding="utf-8")
                normalized_text = _normalize_cartelle_yaml(client_text, slug)
                if normalized_text != client_text:
                    safe_write_text(client_yaml, normalized_text, encoding="utf-8", atomic=True)
                if global_yaml.exists():
                    original_text = read_text_safe(CONFIG_DIR, global_yaml, encoding="utf-8")
                    safe_write_text(backup_yaml, original_text, encoding="utf-8", atomic=True)
                safe_write_text(global_yaml, normalized_text, encoding="utf-8", atomic=True)
                swapped = True
                try:
                    logger.info("ui.cartelle.swap_applied", extra={"slug": slug})
                except Exception:
                    pass

            _run_create_local_structure(slug, workspace_dir, logger)
            _run_drive_structure(slug, workspace_dir, logger)
            _run_generate_readmes(slug, logger)
        finally:
            if swapped:
                try:
                    if backup_yaml.exists():
                        restored_text = read_text_safe(CONFIG_DIR, backup_yaml, encoding="utf-8")
                        safe_write_text(global_yaml, restored_text, encoding="utf-8", atomic=True)
                        backup_yaml.unlink(missing_ok=True)
                    else:
                        global_yaml.unlink(missing_ok=True)
                    try:
                        logger.info("ui.cartelle.swap_restored", extra={"slug": slug})
                    except Exception:
                        pass
                except Exception:
                    st.warning("Ripristino file di configurazione globale non riuscito.")

    _update_client_state(logger, slug, "inizializzato")
    st.success("Workspace inizializzato. Hai accesso agli editor YAML qui sotto.")
    try:
        logger.info("ui.workspace.opened", extra={"slug": slug})
    except Exception:
        pass


def _back_to_landing() -> None:
    for key in list(st.session_state.keys()):
        if key not in {"phase"}:
            st.session_state.pop(key, None)
    st.session_state["phase"] = "landing"


def _render_landing(logger: logging.Logger) -> None:
    st.session_state.setdefault("ui.mode", "landing")
    st.session_state.setdefault("ui.show_manage_select", False)
    st.session_state.setdefault("ui.manage_slug", None)

    _, col_center, _ = st.columns([1, 2, 1])
    with col_center:
        new_clicked = st.button(
            "Nuovo Cliente",
            type="primary",
            width="stretch",
            help="Avvia la procedura per registrare un nuovo cliente.",
        )
        manage_clicked = st.button(
            "Gestisci cliente",
            width="stretch",
            help="Mostra l'elenco dei clienti disponibili.",
        )

    if new_clicked:
        st.session_state["ui.mode"] = "new"
        st.session_state["ui.show_manage_select"] = False
        st.session_state["ui.manage_slug"] = None
        logger.info("ui.landing.mode_set", extra={"mode": "new"})

    if manage_clicked:
        st.session_state["ui.mode"] = "manage"
        st.session_state["ui.show_manage_select"] = True
        logger.info("ui.landing.show_manage_select")

    mode = st.session_state["ui.mode"]

    if mode == "new":
        _render_new_client_block(logger)
        return

    if mode == "manage":
        from .manage import _render_manage_client_block

        _render_manage_client_block(logger)
        return


def _render_new_client_block(logger: logging.Logger) -> None:
    st.session_state.setdefault("ui.new.slug", "")
    st.session_state.setdefault("ui.new.nome", "")
    st.session_state.setdefault("ui.new.pdf_loaded", False)
    st.session_state.setdefault("ui.new.init_done", False)
    st.session_state.setdefault("ui.new.workspace_dir", "")
    st.session_state.setdefault("ui.new.workspace_created", False)
    st.session_state.setdefault("ui.busy.init", False)
    st.session_state.setdefault("ui.busy.create_workspace", False)

    st.subheader("Nuovo Cliente")
    uploaded_pdf_obj = st.session_state.get("ui.new.vision_pdf")
    uploaded_pdf_widget = st.file_uploader(
        "VisionStatement.pdf",
        type=["pdf"],
        key="ui.new.vision_pdf",
        help="Carica il VisionStatement.pdf del cliente (obbligatorio).",
    )
    if uploaded_pdf_widget is not None:
        uploaded_pdf_obj = uploaded_pdf_widget

    pdf_loaded = False
    if uploaded_pdf_obj is not None:
        size_attr = getattr(uploaded_pdf_obj, "size", None)
        try:
            pdf_loaded = size_attr is None or int(size_attr) > 0
        except Exception:
            pdf_loaded = True
    st.session_state["ui.new.pdf_loaded"] = pdf_loaded

    with st.form("landing_new_client_form"):
        slug_value = st.text_input(
            "Slug (kebab-case)",
            key="ui.new.slug",
            placeholder="acme-sicilia",
            help="Inserisci uno slug unico in formato kebab-case.",
        )
        name_value = st.text_input(
            "Nome cliente",
            key="ui.new.nome",
            placeholder="Acme S.p.A.",
            help="Inserisci il nome completo del cliente.",
        )

        slug_trimmed = slug_value.strip()
        name_trimmed = name_value.strip()

        slug_valid = False
        if slug_trimmed:
            try:
                validate_slug(slug_trimmed)
            except InvalidSlug as exc:
                st.error("Slug non valido")
                st.caption(f"Dettaglio: {exc}")
            else:
                slug_valid = True
        elif slug_value:
            st.error("Slug non valido")
            st.caption("Lo slug non può contenere solo spazi.")

        name_valid = bool(name_trimmed)
        if name_value and not name_valid:
            st.error("Nome cliente non valido")
            st.caption("Il nome non può contenere solo spazi.")

        busy_init = bool(st.session_state.get("ui.busy.init"))
        init_clicked = st.form_submit_button(
            "Inizializza workspace",
            type="primary",
            width="stretch",
            disabled=busy_init,
            help="Genera i file YAML in semantic/ a partire dalla Vision.",
        )

    if init_clicked:
        if not slug_valid:
            st.error("Inserisci uno slug valido (kebab-case).")
            return
        if not name_valid:
            st.error("Inserisci il nome del cliente.")
            return
        if not pdf_loaded:
            st.error("Carica il Vision Statement (PDF) prima di iniziare.")
            return

        st.session_state["ui.busy.init"] = True
        st.session_state.pop("ui.new.mapping_text", None)
        st.session_state.pop("ui.new.cartelle_text", None)
        st.session_state.pop("ui.new.yaml_paths", None)
        st.session_state["ui.new.init_done"] = False
        st.session_state["ui.new.workspace_created"] = False

        slug_trimmed = st.session_state.get("ui.new.slug", "").strip()
        name_trimmed = st.session_state.get("ui.new.nome", "").strip()
        uploaded_pdf_obj = st.session_state.get("ui.new.vision_pdf")

        pdf_bytes: bytes | None = None
        if uploaded_pdf_obj is not None:
            try:
                pdf_bytes = uploaded_pdf_obj.getvalue() or None
            except Exception:
                pdf_bytes = None
        if not pdf_bytes:
            st.error("PDF non disponibile. Carica il file e riprova.")
            st.session_state["ui.busy.init"] = False
            return

        workspace_dir = _workspace_dir_for(slug_trimmed)
        workspace_dir.mkdir(parents=True, exist_ok=True)
        try:
            with st.spinner("Inizializzazione Vision in corso..."):
                _copy_base_config(workspace_dir, slug_trimmed, logger)
                ensure_local_workspace_for_ui(
                    slug=slug_trimmed,
                    client_name=name_trimmed,
                    vision_statement_pdf=pdf_bytes,
                )
                ctx = ClientContext.load(
                    slug=slug_trimmed,
                    interactive=False,
                    require_env=False,
                    run_id=None,
                )
                base_dir = cast(Path, ctx.base_dir) if ctx.base_dir is not None else workspace_dir
                pdf_path = cast(Path, ensure_within_and_resolve(base_dir, base_dir / "config" / "VisionStatement.pdf"))
                result = provision_from_vision(ctx, logger, slug=slug_trimmed, pdf_path=pdf_path)

            mapping_rel = _mapping_path(workspace_dir)
            cartelle_rel = _cartelle_path(workspace_dir)
            mapping_text = _load_yaml_text(workspace_dir, mapping_rel)
            cartelle_text = _load_yaml_text(workspace_dir, cartelle_rel)

            st.session_state["ui.new.mapping_text"] = mapping_text
            st.session_state["ui.new.cartelle_text"] = cartelle_text
            st.session_state["ui.new.yaml_paths"] = result.get("yaml_paths") if isinstance(result, dict) else {}
            st.session_state["ui.new.workspace_dir"] = str(workspace_dir)
            st.session_state["ui.new.slug_effective"] = slug_trimmed
            st.session_state["ui.new.nome_effective"] = name_trimmed
            st.session_state["ui.new.init_done"] = True
            st.success("Artefatti Vision generati. Verifica gli YAML prima di creare il workspace.")
            logger.info("ui.new.vision_completed", extra={"slug": slug_trimmed})
            try:
                set_state(slug_trimmed, "nuovo")
                logger.info("ui.state.updated", extra={"slug": slug_trimmed, "state": "nuovo"})
                st.toast("Stato cliente aggiornato a 'nuovo'.")
            except Exception as state_exc:  # pragma: no cover
                logger.warning("ui.state.update_failed", extra={"slug": slug_trimmed, "error": str(state_exc)})
        except (ConfigError, RuntimeError) as exc:
            text = str(exc)
            file_path_attr = getattr(exc, "file_path", None)
            file_path = str(file_path_attr) if file_path_attr else ""
            if isinstance(exc, ConfigError) and file_path.endswith(".vision_hash"):
                gate_state = st.session_state.setdefault("vision_gate_reasons", {})
                gate_state[slug_trimmed] = text
                logger.info("ui.new.vision_gate_hit", extra={"slug": slug_trimmed, "error": text})
            else:
                st.error("Inizializzazione Vision non riuscita")
                st.caption(f"Dettaglio: {text}")
                logger.warning("ui.new.vision_failed", extra={"slug": slug_trimmed, "error": text})
                _render_debug_expander(workspace_dir)
        except Exception:  # pragma: no cover
            st.error("Errore inaspettato durante l'inizializzazione del workspace.")
            logger.exception("ui.new.vision_failed_unexpected", extra={"slug": slug_trimmed})
        finally:
            st.session_state["ui.busy.init"] = False

    init_done = bool(st.session_state.get("ui.new.init_done"))

    gate_state = st.session_state.get("vision_gate_reasons", {})
    gate_reason = None
    gate_slug = (st.session_state.get("ui.new.slug") or "").strip()
    if isinstance(gate_state, dict) and gate_slug:
        gate_reason = gate_state.get(gate_slug)
    if gate_reason:
        workspace_gate = _workspace_dir_for(gate_slug)
        _render_gate_resolution(gate_slug, workspace_gate, logger, gate_reason)

    init_done = bool(st.session_state.get("ui.new.init_done"))
    workspace_dir_str = st.session_state.get("ui.new.workspace_dir") or ""
    if not init_done or not workspace_dir_str:
        return

    workspace_dir = Path(workspace_dir_str)
    mapping_rel = _mapping_path(workspace_dir)
    cartelle_rel = _cartelle_path(workspace_dir)
    mapping_key = "ui.new.mapping_text"
    cartelle_key = "ui.new.cartelle_text"

    if mapping_key not in st.session_state or cartelle_key not in st.session_state:
        try:
            st.session_state[mapping_key] = _load_yaml_text(workspace_dir, mapping_rel)
            st.session_state[cartelle_key] = _load_yaml_text(workspace_dir, cartelle_rel)
        except ConfigError as exc:
            st.error("YAML non disponibile")
            st.caption(f"Dettaglio: {exc}")
            return

    st.subheader("YAML Vision (modificabili)")
    st.caption(f"Slug: `{st.session_state.get('ui.new.slug_effective', '')}`")
    st.caption(f"semantic_mapping.yaml: `{mapping_rel}`")
    st.caption(f"cartelle_raw.yaml: `{cartelle_rel}`")

    with st.form("ui.new.yaml_editor_form"):
        st.text_area("semantic/semantic_mapping.yaml", key=mapping_key, height=320)
        st.text_area("semantic/cartelle_raw.yaml", key=cartelle_key, height=320)
        if st.form_submit_button("Salva YAML", type="primary", width="stretch"):
            try:
                _validate_yaml_dict(st.session_state[mapping_key], "semantic_mapping.yaml")
                _validate_yaml_dict(st.session_state[cartelle_key], "cartelle_raw.yaml")
                _save_yaml_text(workspace_dir, mapping_rel, st.session_state[mapping_key])
                _save_yaml_text(workspace_dir, cartelle_rel, st.session_state[cartelle_key])
                show_success("YAML aggiornati.")
            except ConfigError as exc:
                st.error("Salvataggio YAML non riuscito")
                st.caption(f"Dettaglio: {exc}")

    slug_effective = st.session_state.get("ui.new.slug_effective", "")
    nome_effective = st.session_state.get("ui.new.nome_effective", slug_effective)
    busy_create = bool(st.session_state.get("ui.busy.create_workspace"))

    create_clicked = st.button(
        "Crea Workspace",
        key=f"ui.new.create_workspace_btn.{slug_effective}",
        type="primary",
        width="stretch",
        disabled=busy_create,
        help="Crea la struttura su Drive e completa le cartelle locali.",
    )

    if create_clicked:
        if not slug_effective:
            st.error("Slug non disponibile. Re-inizializza il workspace.")
            return

        st.session_state["ui.busy.create_workspace"] = True
        try:
            mapping_text = st.session_state.get(mapping_key, "")
            cartelle_text = st.session_state.get(cartelle_key, "")
            _validate_yaml_dict(mapping_text, "semantic_mapping.yaml")
            _validate_yaml_dict(cartelle_text, "cartelle_raw.yaml")
            _save_yaml_text(workspace_dir, mapping_rel, mapping_text)
            _save_yaml_text(workspace_dir, cartelle_rel, cartelle_text)

            with st.spinner("Creazione struttura locale e Drive..."):
                _run_create_local_structure(slug_effective, workspace_dir, logger)
                drive_map = _run_drive_structure(slug_effective, workspace_dir, logger)
                _run_generate_readmes(slug_effective, logger)

            ensure_db()
            upsert_client(ClientEntry(slug=slug_effective, nome=nome_effective, stato="inizializzato"))
            _update_client_state(logger, slug_effective, "inizializzato")

            st.session_state["ui.new.workspace_created"] = True
            st.success("Workspace creato. Gli editor restano disponibili per ulteriori modifiche.")
            logger.info(
                "ui.new.workspace_created",
                extra={
                    "slug": slug_effective,
                    "drive_raw": (drive_map.get("raw") if isinstance(drive_map, dict) else None),
                },
            )
        except (ConfigError, RuntimeError) as exc:
            st.error("Creazione workspace non riuscita")
            st.caption(f"Dettaglio: {exc}")
            logger.warning(
                "ui.new.workspace_creation_failed",
                extra={"slug": slug_effective, "error": str(exc)},
            )
        except Exception:  # pragma: no cover
            st.error("Errore inatteso durante la creazione del workspace. Consulta i log.")
            logger.exception("ui.new.workspace_creation_failed_unexpected", extra={"slug": slug_effective})
        finally:
            st.session_state["ui.busy.create_workspace"] = False

    if st.session_state.get("ui.new.workspace_created") and slug_effective:
        if st.button(
            "Vai all'arricchimento semantico",
            key=f"ui.new.go_semantic.{slug_effective}",
            width="stretch",
        ):
            st.session_state["ui.mode"] = "manage"
            st.session_state["ui.manage_slug"] = slug_effective
            st.session_state["ui.manage.selected_slug"] = slug_effective
            _safe_streamlit_rerun()


def render_home(*, slug: str | None = None, logger: logging.Logger | None = None) -> None:
    """Landing/Home: usa la landing originale con le azioni Nuovo/Gestisci."""
    del slug
    log = logger or _setup_logging()
    if st is None:
        return
    try:
        _render_landing(log)
    except Exception as exc:  # pragma: no cover
        log.warning("ui.tabs.home_render_failed", extra={"error": str(exc)})


# TEST: ruff check .
# TEST: streamlit run onboarding_ui.py
