# src/ui/app.py
from __future__ import annotations

import logging
import os
import signal
from pathlib import Path
from typing import Any, Dict, Optional, cast

# Import standard/third‑party prima di qualsiasi codice
import yaml

from pipeline.context import ClientContext
from pipeline.exceptions import ConfigError, InvalidSlug
from pipeline.file_utils import safe_write_bytes, safe_write_text
from pipeline.path_utils import ensure_within_and_resolve, read_text_safe, validate_slug
from pipeline.yaml_utils import clear_yaml_cache, yaml_read

# Queste util potrebbero non essere disponibili in ambienti headless → fallback a None
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

from ui.clients_store import ClientEntry, ensure_db, load_clients, set_state, upsert_client
from ui.services.drive_runner import emit_readmes_for_raw
from ui.services.vision_provision import provision_from_vision

# Import Streamlit in modo tollerante (test/CI headless)
try:
    import streamlit as st
except Exception:  # pragma: no cover
    st = None


REPO_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_ROOT = REPO_ROOT / "output"
BASE_CONFIG = REPO_ROOT / "config" / "config.yaml"


def _update_client_state(logger: logging.Logger, slug: str, stato: str) -> bool:
    """Aggiorna lo stato del cliente registrato, senza interrompere la UI."""
    try:
        set_state(slug, stato)
    except Exception as exc:  # pragma: no cover
        logger.warning("ui.client_state_update_failed", extra={"slug": slug, "target_state": stato, "error": str(exc)})
        return False
    logger.info("ui.client_state_updated", extra={"slug": slug, "state": stato})
    return True


def _setup_logging() -> logging.Logger:
    logger = logging.getLogger("ui.new_client")
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(asctime)s %(name)s [%(levelname)s] %(message)s"))
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    return logger


def _render_debug_expander(workspace_dir: Path) -> None:
    """Mostra un expander 'Debug' con eventuali file di diagnostica Vision.

    Cerca in `semantic/` i file `.vision_last_response.json` e `.vision_last_error.txt`.
    Se non trovati, mostra un messaggio informativo.
    """
    if st is None:
        return
    try:
        sem_dir = cast(Path, ensure_within_and_resolve(workspace_dir, _semantic_dir(workspace_dir)))
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


def _request_shutdown(logger: logging.Logger) -> None:
    try:
        slug_extra: Dict[str, Any] = {}
        try:
            if st is not None:
                s = cast(Optional[str], st.session_state.get("slug"))
                if s:
                    slug_extra["slug"] = s
        except Exception:
            pass
        logger.info("ui.shutdown_request", extra=slug_extra or None)
        os.kill(os.getpid(), signal.SIGTERM)
    except Exception:
        os._exit(0)


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


def _pdf_path(workspace_dir: Path) -> Path:
    return workspace_dir / "config" / "VisionStatement.pdf"


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


def _load_config_data(workspace_dir: Path) -> Dict[str, Any]:
    cfg_path = _config_path(workspace_dir)
    data = yaml_read(workspace_dir, cfg_path)
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ConfigError("config.yaml non valido: atteso un dizionario")
    return data


def _persist_config_value(
    workspace_dir: Path,
    slug: str,
    key: str,
    value: Any,
    logger: logging.Logger,
) -> None:
    data = _load_config_data(workspace_dir)
    data[key] = value
    serialized = yaml.safe_dump(data, sort_keys=False, allow_unicode=True)
    target = cast(Path, ensure_within_and_resolve(workspace_dir, _config_path(workspace_dir)))
    safe_write_text(target, serialized, encoding="utf-8", atomic=True)
    clear_yaml_cache()
    logger.info("ui.config.updated", extra={"slug": slug, "key": key, "path": str(target)})


def _render_config_widget(slug: str, key: str, value: Any) -> Any:
    label = f"{key} [{slug}]"
    if isinstance(value, bool):
        return st.checkbox(label, value=value)
    if isinstance(value, int) and not isinstance(value, bool):
        return int(st.number_input(label, value=int(value), step=1))
    if isinstance(value, float):
        return float(st.number_input(label, value=float(value)))
    default = "" if value is None else str(value)
    text = st.text_input(label, value=default)
    if value is None and text == "":
        return None
    return text


def _render_config_editor(workspace_dir: Path, slug: str, logger: logging.Logger) -> None:
    st.subheader("Config workspace")
    try:
        data = _load_config_data(workspace_dir)
    except ConfigError as exc:
        st.error(str(exc))
        return

    if not data:
        st.info("Config vuoto: nessun campo da mostrare.")
        return

    for key, value in data.items():
        with st.form(f"cfg_field_{key}"):
            new_value = _render_config_widget(slug, key, value)
            saved = st.form_submit_button("Salva", use_container_width=True)
            if saved:
                try:
                    _persist_config_value(workspace_dir, slug, key, new_value, logger)
                    st.success("Valore aggiornato.")
                except ConfigError as exc:
                    st.error(str(exc))


def _handle_pdf_upload(workspace_dir: Path, slug: str, logger: logging.Logger) -> bool:
    st.subheader("Vision Statement")
    config_dir = cast(Path, ensure_within_and_resolve(workspace_dir, workspace_dir / "config"))
    config_dir.mkdir(parents=True, exist_ok=True)
    pdf_target = cast(Path, ensure_within_and_resolve(config_dir, config_dir / "VisionStatement.pdf"))

    exists = pdf_target.exists()
    overwrite_allowed = False
    if exists:
        overwrite_allowed = st.checkbox(
            "Sostituisci VisionStatement.pdf esistente",
            value=False,
            key=f"overwrite_pdf_{slug}",
        )

    uploader = st.file_uploader("Carica Vision Statement (PDF)", type=["pdf"])
    if uploader is not None:
        data = uploader.read()
        if not data:
            st.warning("Il file caricato è vuoto. Riprova.")
        elif exists and not overwrite_allowed:
            st.warning("File già presente. Abilita la sostituzione per sovrascrivere.")
        else:
            safe_write_bytes(pdf_target, data, atomic=True)
            st.success("VisionStatement.pdf salvato.")
            logger.info(
                "ui.vision.pdf_uploaded",
                extra={
                    "slug": slug,
                    "path": str(pdf_target),
                    "bytes": len(data),
                    "overwrite": bool(exists),
                },
            )
            exists = True

    if exists:
        st.caption(f"PDF presente: `{pdf_target}`")
    else:
        st.info("Carica il VisionStatement.pdf per abilitare l'inizializzazione.")
    return exists


def _vision_outputs_exist(workspace_dir: Path) -> bool:
    try:
        mapping = cast(Path, ensure_within_and_resolve(workspace_dir, _mapping_path(workspace_dir)))
        cartelle = cast(Path, ensure_within_and_resolve(workspace_dir, _cartelle_path(workspace_dir)))
    except ConfigError:
        return False
    return mapping.exists() and cartelle.exists()


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


def _initialize_workspace(slug: str, workspace_dir: Path, logger: logging.Logger) -> Optional[Dict[str, Any]]:
    if _vision_outputs_exist(workspace_dir):
        st.info("Gli artefatti Vision sono già presenti: nessuna rigenerazione.")
        return None

    pdf_path = cast(Path, ensure_within_and_resolve(workspace_dir, _pdf_path(workspace_dir)))
    if not pdf_path.exists():
        raise ConfigError("VisionStatement.pdf non trovato nel workspace.")

    semantic_dir = cast(Path, ensure_within_and_resolve(workspace_dir, _semantic_dir(workspace_dir)))
    semantic_dir.mkdir(parents=True, exist_ok=True)

    ctx = ClientContext.load(slug=slug, interactive=False, require_env=False, run_id=None)
    result: Dict[str, Any] = provision_from_vision(ctx, logger, slug=slug, pdf_path=pdf_path)
    logger.info(
        "ui.vision.generated",
        extra={
            "slug": slug,
            "mapping": result.get("yaml_paths", {}).get("mapping"),
            "cartelle_raw": result.get("yaml_paths", {}).get("cartelle_raw"),
        },
    )
    return result


def _run_create_local_structure(slug: str, workspace_dir: Path, logger: logging.Logger) -> None:
    if create_local_base_structure is None:
        raise RuntimeError("Funzionalità locali non disponibili: installa i moduli 'pipeline.drive_utils'.")
    ctx = ClientContext.load(slug=slug, interactive=False, require_env=False, run_id=None)
    cartelle = cast(Path, ensure_within_and_resolve(workspace_dir, _cartelle_path(workspace_dir)))
    create_local_base_structure(ctx, cartelle)
    logger.info("ui.workspace.local_structure", extra={"slug": slug, "yaml": str(cartelle)})


def _run_drive_structure(slug: str, workspace_dir: Path, logger: logging.Logger) -> Dict[str, str]:
    # Guardie per ambienti senza dipendenze Drive
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
            ensure_structure=False,
        ),
    )
    logger.info("ui.workspace.readmes", extra={"slug": slug, "count": len(result)})
    return result


def _open_workspace(slug: str, workspace_dir: Path, logger: logging.Logger) -> None:
    with st.spinner("Creazione workspace..."):
        _run_create_local_structure(slug, workspace_dir, logger)
        _run_drive_structure(slug, workspace_dir, logger)
        _run_generate_readmes(slug, logger)
    _update_client_state(logger, slug, "inizializzato")
    st.success("Workspace inizializzato. Hai accesso agli editor YAML qui sotto.")
    try:
        logger.info("ui.workspace.opened", extra={"slug": slug})
    except Exception:
        pass


def _render_workspace_view(slug: str, workspace_dir: Path, logger: logging.Logger) -> None:
    st.subheader(f"Workspace attivo: {slug}")
    mapping_rel = _mapping_path(workspace_dir)
    cartelle_rel = _cartelle_path(workspace_dir)

    mapping_key = f"{slug}_mapping_text"
    cartelle_key = f"{slug}_cartelle_text"

    try:
        mapping_text = _load_yaml_text(workspace_dir, mapping_rel)
        cartelle_text = _load_yaml_text(workspace_dir, cartelle_rel)
    except ConfigError as exc:
        st.error(str(exc))
        return

    if mapping_key not in st.session_state:
        st.session_state[mapping_key] = mapping_text
    if cartelle_key not in st.session_state:
        st.session_state[cartelle_key] = cartelle_text

    with st.form("yaml_editor_form"):
        st.text_area("semantic/semantic_mapping.yaml", key=mapping_key, height=320)
        st.text_area("semantic/cartelle_raw.yaml", key=cartelle_key, height=320)
        if st.form_submit_button("Valida & Salva", type="primary"):
            try:
                # Parsing/validazione base
                _validate_yaml_dict(st.session_state[mapping_key], "semantic_mapping.yaml")
                _validate_yaml_dict(st.session_state[cartelle_key], "cartelle_raw.yaml")

                # Validazione schema minima (più stretta)
                mapping_data = yaml.safe_load(st.session_state[mapping_key]) or {}
                cartelle_data = yaml.safe_load(st.session_state[cartelle_key]) or {}

                if (
                    "context" not in mapping_data
                    or "areas" not in mapping_data
                    or not isinstance(mapping_data["areas"], list)
                    or not mapping_data["areas"]
                ):
                    raise ConfigError("semantic_mapping.yaml: mancano 'context' o 'areas' (lista non vuota).")
                ctx_map = mapping_data["context"]
                if not isinstance(ctx_map, dict) or "slug" not in ctx_map or "client_name" not in ctx_map:
                    raise ConfigError("semantic_mapping.yaml: 'context.slug' e 'context.client_name' sono obbligatori.")

                if cartelle_data.get("version") != 1 or not isinstance(cartelle_data.get("folders"), list):
                    raise ConfigError("cartelle_raw.yaml: attesi 'version: 1' e 'folders' come lista.")

                _save_yaml_text(workspace_dir, mapping_rel, st.session_state[mapping_key])
                _save_yaml_text(workspace_dir, cartelle_rel, st.session_state[cartelle_key])
                st.success("YAML aggiornati.")
            except ConfigError as exc:
                st.error(str(exc))

    actions = st.columns(3)
    with actions[0]:
        if st.button("Crea locale", use_container_width=True):
            try:
                _run_create_local_structure(slug, workspace_dir, logger)
                st.success("Struttura locale aggiornata.")
            except ConfigError as exc:
                st.error(str(exc))
            except RuntimeError as exc:
                st.error(str(exc))
    with actions[1]:
        if st.button("Crea su Drive", use_container_width=True):
            try:
                created = _run_drive_structure(slug, workspace_dir, logger)
                st.success(f"Struttura Drive aggiornata (raw={created.get('raw')}).")
            except ConfigError as exc:
                st.error(str(exc))
            except RuntimeError as exc:
                st.error(str(exc))
    with actions[2]:
        if st.button("Genera README", use_container_width=True):
            try:
                uploaded = _run_generate_readmes(slug, logger)
                st.success(f"README caricati: {len(uploaded)}")
            except (ConfigError, RuntimeError) as exc:
                st.error(str(exc))

    st.caption(f"Mapping: `{mapping_rel}`")
    st.caption(f"Cartelle raw: `{cartelle_rel}`")


def _back_to_landing() -> None:
    for key in list(st.session_state.keys()):
        if key not in {"phase"}:
            st.session_state.pop(key, None)
    st.session_state["phase"] = "landing"


def _render_setup(slug: str, workspace_dir: Path, logger: logging.Logger) -> None:
    st.header("Nuovo cliente: configurazione iniziale")
    st.caption(f"Workspace: `{workspace_dir}`")

    try:
        _copy_base_config(workspace_dir, slug, logger)
    except ConfigError as exc:
        st.error(str(exc))
        return

    _render_config_editor(workspace_dir, slug, logger)
    pdf_ready = _handle_pdf_upload(workspace_dir, slug, logger)

    if st.button("Inizializza workspace", type="primary", disabled=not pdf_ready):
        try:
            logger.info("ui.setup.init_start", extra={"slug": slug})
            result = _initialize_workspace(slug, workspace_dir, logger)
            st.session_state["init_result"] = result or {}
            st.toast("Workspace inizializzato")
            st.session_state["phase"] = "ready_to_open"
            logger.info("ui.setup.init_done", extra={"slug": slug})
        except ConfigError as exc:
            st.error(str(exc))
            _render_debug_expander(workspace_dir)

    st.button("Torna alla landing", on_click=_back_to_landing)


def _render_ready(slug: str, workspace_dir: Path, logger: logging.Logger) -> None:
    st.header("Workspace pronto")
    st.success("Artefatti Vision generati. Puoi creare la struttura completa ora.")
    result = st.session_state.get("init_result") or {}
    yaml_paths = result.get("yaml_paths") or {}
    if yaml_paths:
        st.json(yaml_paths, expanded=False)

    # Percorsi YAML sempre visibili, anche se init_result manca (refresh)
    mapping_rel = _mapping_path(workspace_dir)
    cartelle_rel = _cartelle_path(workspace_dir)
    if hasattr(st, "caption"):
        st.caption(f"Mapping: `{mapping_rel}`")
        st.caption(f"Cartelle raw: `{cartelle_rel}`")

    # Opzione di rigenerazione YAML se gli artefatti sono presenti
    mapping_path = yaml_paths.get("mapping")
    cartelle_path = yaml_paths.get("cartelle_raw")
    if mapping_path and cartelle_path:
        confirm_key = f"regen_confirm_{slug}"
        confirm = st.checkbox("Sovrascrivi i file", key=confirm_key, value=False)
        if st.button("Rigenera YAML"):
            if not confirm:
                st.warning("Conferma la sovrascrittura per procedere.")
            else:
                try:
                    # Rilancia la generazione usando il PDF esistente nel workspace
                    ctx = ClientContext.load(slug=slug, interactive=False, require_env=False, run_id=None)
                    pdf_path = cast(Path, ensure_within_and_resolve(workspace_dir, _pdf_path(workspace_dir)))
                    new_result = provision_from_vision(ctx, logger, slug=slug, pdf_path=pdf_path)
                    yaml_paths_new = new_result.get("yaml_paths") if isinstance(new_result, dict) else {}
                    st.session_state["init_result"] = {"yaml_paths": yaml_paths_new or {}}
                    st.success("YAML rigenerati con successo.")
                except ConfigError as exc:
                    st.error(str(exc))

    if st.button(f"Apri workspace: {slug}", type="primary"):
        try:
            _open_workspace(slug, workspace_dir, logger)
            st.session_state["phase"] = "workspace"
        except (ConfigError, RuntimeError) as exc:
            st.error(str(exc))

    st.button("Torna alla landing", on_click=_back_to_landing)


def _render_sidebar_shortcuts(slug: Optional[str], workspace_dir: Optional[Path], logger: logging.Logger) -> None:
    """Shortcut in sidebar per aprire rapidamente il workspace."""
    if st is None or slug is None or workspace_dir is None:
        return
    with st.sidebar:
        try:
            mapping_rel = _mapping_path(workspace_dir)
            cartelle_rel = _cartelle_path(workspace_dir)
            if mapping_rel.exists() and cartelle_rel.exists():
                st.caption(f"Mapping: `{mapping_rel}`")
                st.caption(f"Cartelle raw: `{cartelle_rel}`")
                if st.session_state.get("phase") == "ready_to_open":
                    if st.button("Apri workspace", type="primary", use_container_width=True):
                        try:
                            _open_workspace(slug, workspace_dir, logger)
                            st.session_state["phase"] = "workspace"
                            st.rerun()
                        except (ConfigError, RuntimeError) as exc:
                            st.error(str(exc))
            else:
                st.info("Inizializza workspace prima di aprirlo")
        except Exception:
            # La sidebar non deve interrompere il rendering principale
            pass


def _render_landing(logger: logging.Logger) -> None:
    tab_new, tab_edit = st.tabs(["Nuovo cliente", "Modifica cliente"])

    with tab_new:
        slug_input = st.text_input("Slug (kebab-case)", key="landing_new_slug", placeholder="acme-sicilia")
        name_input = st.text_input("Nome cliente", key="landing_new_name", placeholder="Acme S.p.A.")
        uploaded_pdf = st.file_uploader("VisionStatement.pdf", type=["pdf"], key="landing_new_pdf")

        col_submit, col_exit = st.columns([2, 1])
        with col_submit:
            submit = st.button("Crea e continua", type="primary", use_container_width=True, key="landing_new_submit")
        with col_exit:
            if st.button("Esci", use_container_width=True, key="landing_exit_btn"):
                _request_shutdown(logger)

        if submit:
            slug = slug_input.strip()
            nome = name_input.strip()
            if not slug:
                st.error("Inserisci uno slug valido")
                return
            try:
                validate_slug(slug)
            except InvalidSlug as exc:
                st.error(str(exc))
                try:
                    logger.info("ui.landing.invalid_slug", extra={"slug": slug})
                except Exception:
                    pass
                return
            if not nome:
                st.error("Inserisci un nome cliente")
                return
            if uploaded_pdf is None:
                st.error("Carica il Vision Statement (PDF) per procedere")
                return
            pdf_bytes = uploaded_pdf.getvalue() or b""
            if not pdf_bytes:
                st.error("Carica il Vision Statement (PDF) per procedere")
                return
            try:
                workspace_dir = _workspace_dir_for(slug)
                workspace_dir.mkdir(parents=True, exist_ok=True)
                _copy_base_config(workspace_dir, slug, logger)
                semantic_dir = cast(Path, ensure_within_and_resolve(workspace_dir, _semantic_dir(workspace_dir)))
                semantic_dir.mkdir(parents=True, exist_ok=True)
                pdf_path = cast(Path, ensure_within_and_resolve(semantic_dir, semantic_dir / "VisionStatement.pdf"))
                safe_write_bytes(pdf_path, pdf_bytes, atomic=True)

                ctx = ClientContext.load(slug=slug, interactive=False, require_env=False, run_id=None)
                result: Dict[str, Any] | None = provision_from_vision(ctx, logger, slug=slug, pdf_path=pdf_path)

                ensure_db()
                upsert_client(ClientEntry(slug=slug, nome=nome, stato="nuovo"))

                st.session_state["slug"] = slug
                st.session_state["workspace_dir"] = str(workspace_dir)
                st.session_state.pop("init_result", None)
                st.session_state["init_result"] = result if isinstance(result, dict) else {}
                st.session_state["phase"] = "setup"

                st.rerun()
            except (ConfigError, RuntimeError) as exc:
                st.error(str(exc))

    with tab_edit:
        clients = load_clients()
        selected_entry: ClientEntry | None = None
        with st.form("landing_edit_form"):
            if not clients:
                st.selectbox(
                    "Seleziona cliente",
                    options=["Nessun cliente registrato"],
                    index=0,
                    disabled=True,
                    key="landing_edit_select_disabled",
                )
                st.info("Nessun cliente registrato: crea un nuovo cliente per iniziare.")
                open_disabled = True
            else:
                labels = {f"{entry.nome or entry.slug} ({entry.slug})": entry for entry in clients}
                options = list(labels.keys())
                selected_label: str | None = None
                try:
                    selected_label = st.selectbox(
                        "Seleziona cliente",
                        options,
                        index=None,
                        placeholder="Scegli un cliente",
                        key="landing_edit_select",
                    )
                except TypeError:
                    placeholder = "-- Seleziona cliente --"
                    fallback_options = [placeholder, *options]
                    selected_label = st.selectbox(
                        "Seleziona cliente",
                        fallback_options,
                        index=0,
                        key="landing_edit_select_fallback",
                    )
                    if selected_label == placeholder:
                        selected_label = None
                if selected_label:
                    selected_entry = labels.get(selected_label)
                open_disabled = selected_entry is None
            open_client = st.form_submit_button(
                "Apri",
                type="primary",
                use_container_width=True,
                disabled=open_disabled,
                key="landing_edit_open",
            )

        if open_client and selected_entry:
            slug_to_open = selected_entry.slug
            workspace_dir = _workspace_dir_for(slug_to_open)
            st.session_state["slug"] = slug_to_open
            st.session_state["workspace_dir"] = str(workspace_dir)
            st.session_state.pop("init_result", None)
            st.session_state["phase"] = "workspace" if _vision_outputs_exist(workspace_dir) else "setup"
            st.rerun()


def main() -> None:
    logger = _setup_logging()
    if st is not None:
        st.set_page_config(page_title="Onboarding NeXT", layout="wide")

    phase = st.session_state.get("phase", "landing")
    slug = st.session_state.get("slug")
    workspace_dir = Path(st.session_state.get("workspace_dir", "")) if slug else None

    # Sidebar scorciatoie (non bloccante)
    _render_sidebar_shortcuts(slug, workspace_dir, logger)

    if phase == "landing":
        _render_landing(logger)
        return

    if not slug or workspace_dir is None:
        st.session_state["phase"] = "landing"
        _render_landing(logger)
        return

    if phase == "setup":
        _render_setup(slug, workspace_dir, logger)
    elif phase == "ready_to_open":
        _render_ready(slug, workspace_dir, logger)
    elif phase == "workspace":
        _render_workspace_view(slug, workspace_dir, logger)
    else:
        st.session_state["phase"] = "landing"
        _render_landing(logger)


if __name__ == "__main__":
    main()
