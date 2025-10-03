# src/ui/app.py
from __future__ import annotations

import logging
import os
import signal
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable, Dict, Optional, cast

SRC_ROOT = Path(__file__).resolve().parents[1]
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

# Import standard/third party prima di qualsiasi codice
import yaml  # noqa: E402

from pipeline.context import ClientContext  # noqa: E402
from pipeline.exceptions import ConfigError, InvalidSlug  # noqa: E402
from pipeline.file_utils import safe_write_text  # noqa: E402
from pipeline.path_utils import ensure_within, ensure_within_and_resolve, read_text_safe, validate_slug  # noqa: E402
from pipeline.yaml_utils import clear_yaml_cache, yaml_read  # noqa: E402
from pre_onboarding import ensure_local_workspace_for_ui  # noqa: E402

# Queste util potrebbero non essere disponibili in ambienti headless: fallback a None
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

from ui.clients_store import ClientEntry, ensure_db, get_state, load_clients, set_state, upsert_client  # noqa: E402
from ui.services.drive_runner import download_raw_from_drive_with_progress, emit_readmes_for_raw  # noqa: E402
from ui.services.vision_provision import provision_from_vision  # noqa: E402

try:
    from ui.components.drive_tree import render_drive_tree
except Exception:  # pragma: no cover
    render_drive_tree = None

try:
    from ui.components.diff_view import render_drive_local_diff
except Exception:  # pragma: no cover
    render_drive_local_diff = None

try:
    from ui.components.yaml_editors import edit_cartelle_raw, edit_semantic_mapping, edit_tags_reviewed
except Exception:  # pragma: no cover
    edit_semantic_mapping = None
    edit_cartelle_raw = None
    edit_tags_reviewed = None

try:
    from ui.services.tags_adapter import run_tags_update
except Exception:  # pragma: no cover
    run_tags_update = None

# Import Streamlit in modo tollerante (test/CI headless)
try:
    import streamlit as st
except Exception:  # pragma: no cover
    st = None


REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = REPO_ROOT / "config"
OUTPUT_ROOT = REPO_ROOT / "output"
BASE_CONFIG = CONFIG_DIR / "config.yaml"


# --- UI adapters (solo presentazione, no business logic) ----------------------
DialogDecorator = Callable[[Callable[[], None]], Callable[[], None]]
DialogFactory = Callable[[str], DialogDecorator]


def _ui_dialog(title: str, body_fn: Callable[[], None]) -> None:
    """
    Version-safe dialog:
    - prefer st.dialog (>=1.30) / st.experimental_dialog (decorator)
    - fallback finale: expander "pseudo-modal"
    body_fn: funzione senza argomenti che renderizza il contenuto del dialog.
    """
    if st is None:
        return
    dlg_raw = getattr(st, "dialog", None) or getattr(st, "experimental_dialog", None)
    dlg = cast(Optional[DialogFactory], dlg_raw)
    if dlg is not None:
        decorator: DialogDecorator = dlg(title)

        @decorator
        def _show() -> None:
            body_fn()

        _show()
    else:
        with st.expander(title, expanded=True):
            body_fn()


def _update_client_state(logger: logging.Logger, slug: str, stato: str) -> bool:
    """Aggiorna lo stato del cliente registrato, senza interrompere la UI."""
    try:
        set_state(slug, stato)
    except Exception as exc:  # pragma: no cover
        logger.warning("ui.client_state_update_failed", extra={"slug": slug, "target_state": stato, "error": str(exc)})
        return False
    logger.info("ui.client_state_updated", extra={"slug": slug, "state": stato})
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
    # Landmark principale per skip-link
    st.markdown("<main id='main'></main>", unsafe_allow_html=True)
    st.title("Onboarding NeXT - Clienti")
    if not slug:
        st.caption("Nessun cliente attivo. Crea o seleziona un cliente per iniziare.")
        return
    state = _current_client_state(slug)
    if state:
        st.markdown(f"Cliente attivo: **{slug}** — Stato: `{state.upper()}`")
    try:
        with st.sidebar:
            st.markdown("### Cliente")
            st.write(f"**Slug**: `{slug}`")
            st.write(f"**Stato**: `{(state or 'n/d').upper()}`")
            st.divider()
            st.markdown("[Vai a Configurazione](#section-yaml)")
            st.markdown("[Vai a Google Drive](#section-drive)")
            st.markdown("[Vai a Semantica](#section-semantic)")
    except Exception:
        pass


def _setup_logging() -> logging.Logger:
    logger = logging.getLogger("ui.new_client")
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(asctime)s %(name)s [%(levelname)s] %(message)s"))
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    return logger


def _ui_delete_client_via_tool(slug: str) -> tuple[bool, str]:
    """UI adapter che invoca il tool CLI per eliminare il cliente.

    Restituisce (ok, messaggio).
    """
    cmd = [sys.executable, "-m", "src.tools.clean_client_workspace", "--slug", slug, "-y"]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    except FileNotFoundError as exc:
        return False, f"Tool di cleanup non trovato: {exc}"
    except subprocess.CalledProcessError as exc:
        message = (exc.stderr or exc.stdout or str(exc)).strip()
        return False, message or "Errore durante l'eliminazione del cliente."
    except Exception as exc:  # pragma: no cover
        return False, str(exc)
    output = (result.stdout or result.stderr or "").strip()
    return True, output or "Pulizia completata."


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


def _tags_reviewed_path(workspace_dir: Path) -> Path:
    return _semantic_dir(workspace_dir) / "tags_reviewed.yaml"


def _pdf_path(workspace_dir: Path) -> Path:
    return workspace_dir / "config" / "VisionStatement.pdf"


def _normalize_cartelle_yaml(cartelle_text: str, slug: str) -> str:
    """Garantisce che il file cartelle_raw.yaml contenga un nodo 'raw'."""
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
        st.error("YAML non disponibile")
        st.caption(f"Dettaglio: {exc}")
        return

    if not data:
        st.info("Config vuoto: nessun campo da mostrare.")
        return

    for key, value in data.items():
        with st.form(f"cfg_field_{key}"):
            new_value = _render_config_widget(slug, key, value)
            saved = st.form_submit_button("Salva", width="stretch")
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
            st.warning("Il file caricato e' vuoto. Riprova.")
        elif exists and not overwrite_allowed:
            st.warning("File gia' presente. Abilita la sostituzione per sovrascrivere.")
        else:
            try:
                config_data = _load_config_data(workspace_dir)
            except ConfigError:
                config_data = {}
            client_name = cast(str, (config_data.get("client_name") or slug))
            ensure_local_workspace_for_ui(slug=slug, client_name=client_name, vision_statement_pdf=data)
            pdf_target = cast(Path, ensure_within_and_resolve(config_dir, config_dir / "VisionStatement.pdf"))
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
        st.info("Gli artefatti Vision sono gia presenti: nessuna rigenerazione.")
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
        raise RuntimeError("Funzionalita locali non disponibili: installa i moduli 'pipeline.drive_utils'.")
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
            "Funzionalita Drive non disponibili: installa gli extra o configura i servizi (pipeline.drive_utils)."
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
    logger.info("ui.workspace.readmes", extra={"slug": slug, "count": len(result)})
    return result


def _open_workspace(slug: str, workspace_dir: Path, logger: logging.Logger) -> None:
    # NOTE: normalizza cartelle_raw.yaml al formato con nodo 'raw' prima di proseguire
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
        # i runner segnaleranno successivamente file mancanti
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


def _render_workspace_view(slug: str, workspace_dir: Path, logger: logging.Logger) -> None:
    st.subheader(f"Workspace attivo: {slug}")
    mapping_rel = _mapping_path(workspace_dir)
    cartelle_rel = _cartelle_path(workspace_dir)

    mapping_key = f"{slug}_mapping_text"
    cartelle_key = f"{slug}_cartelle_text"

    try:
        mapping_text = _load_yaml_text(workspace_dir, mapping_rel)
        cartelle_text_raw = _load_yaml_text(workspace_dir, cartelle_rel)
        cartelle_text = _normalize_cartelle_yaml(cartelle_text_raw, slug)
        if cartelle_text != cartelle_text_raw:
            _save_yaml_text(workspace_dir, cartelle_rel, cartelle_text)
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
        if st.form_submit_button("Valida & Salva", type="primary", width="stretch"):
            try:
                # Parsing/validazione base
                _validate_yaml_dict(st.session_state[mapping_key], "semantic_mapping.yaml")
                _validate_yaml_dict(st.session_state[cartelle_key], "cartelle_raw.yaml")

                # Validazione schema minima (piu stretta)
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
                st.error("Salvataggio YAML non riuscito")
                st.caption(f"Dettaglio: {exc}")

    actions = st.columns(3)
    with actions[0]:
        if st.button("Crea locale", width="stretch"):
            try:
                _run_create_local_structure(slug, workspace_dir, logger)
                st.success("Struttura locale aggiornata.")
            except ConfigError as exc:
                st.error("Salvataggio YAML non riuscito")
                st.caption(f"Dettaglio: {exc}")
            except RuntimeError as exc:
                st.error(str(exc))
    with actions[1]:
        if st.button("Crea su Drive", width="stretch"):
            try:
                created = _run_drive_structure(slug, workspace_dir, logger)
                st.success(f"Struttura Drive aggiornata (raw={created.get('raw')}).")
            except ConfigError as exc:
                st.error("Salvataggio YAML non riuscito")
                st.caption(f"Dettaglio: {exc}")
            except RuntimeError as exc:
                st.error(str(exc))
    with actions[2]:
        if st.button("Genera README", width="stretch"):
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


def _handle_sidebar_navigation(slug: str, target: str) -> None:
    if st is None:
        return
    st.session_state["ui.mode"] = "manage"
    st.session_state["ui.show_manage_select"] = True
    st.session_state["ui.manage_slug"] = slug
    st.session_state["ui.manage.selected_slug"] = slug
    if target == "semantica":
        st.session_state["ui.manage.target"] = target
    else:
        st.session_state.pop("ui.manage.target", None)
    try:
        st.rerun()
    except Exception:
        pass


def _render_sidebar_client_panel(slug: Optional[str], logger: logging.Logger) -> None:
    if st is None or not slug:
        return
    _ = logger
    state_value = _current_client_state(slug) or "N/D"
    st.caption("Cliente attivo")
    st.text_input("Slug", value=slug, key=f"sidebar.slug.{slug}", disabled=True)
    st.text_input(
        "Stato",
        value=state_value.upper() if isinstance(state_value, str) else str(state_value),
        key=f"sidebar.state.{slug}",
        disabled=True,
    )
    go_drive = st.button("Vai a Drive", key=f"sidebar.drive.{slug}", width="stretch")
    go_semantic = st.button("Vai a Semantica", key=f"sidebar.semantic.{slug}", width="stretch")
    if go_drive:
        _handle_sidebar_navigation(slug, "drive")
    if go_semantic:
        _handle_sidebar_navigation(slug, "semantica")


def _render_sidebar_shortcuts(slug: Optional[str], workspace_dir: Optional[Path], logger: logging.Logger) -> None:
    """Shortcut e azioni rapide nel menu laterale."""
    if st is None:
        return

    with st.sidebar:
        try:
            logo_path = REPO_ROOT / "assets" / "next-logo.png"
            if logo_path.exists():
                st.image(str(logo_path), width="stretch")  # immagini: lasciamo compat (nessun warning)
        except Exception as exc:  # pragma: no cover
            logger.warning("ui.sidebar.logo_error", extra={"error": str(exc)})

        st.divider()
        _render_sidebar_client_panel(slug, logger)
        col_exit, col_dummy = st.columns(2)
        if col_exit.button(
            "Esci",
            key="sidebar_exit_btn",
            width="stretch",
            help="Chiudi l'app",
        ):
            _request_shutdown(logger)

        if col_dummy.button(
            "Genera dummy",
            key="sidebar_dummy_btn",
            width="stretch",
            help="Crea il workspace di esempio per testare il flusso",
        ):
            active_slug = slug or "dummy"
            try:
                from tools.gen_dummy_kb import main as gen_dummy_main

                with st.spinner(f"Genero dataset dummy per '{active_slug}'..."):
                    exit_code = gen_dummy_main(["--slug", active_slug, "--non-interactive"])
                if int(exit_code) == 0:
                    st.success(f"Dummy generato per '{active_slug}'.")
                    logger.info("ui.sidebar.dummy_generated", extra={"slug": active_slug})
                else:  # pragma: no cover
                    st.error("Generazione dummy terminata con errore.")
                    logger.error(
                        "ui.sidebar.dummy_failed",
                        extra={"slug": active_slug, "code": int(exit_code)},
                    )
            except Exception as exc:  # pragma: no cover
                st.error(f"Errore durante la generazione del dummy: {exc}")
                logger.exception("ui.sidebar.dummy_exception", extra={"slug": active_slug})

        if slug is None:
            return
        if workspace_dir is None:
            return

        try:
            mapping_rel = _mapping_path(workspace_dir)
            cartelle_rel = _cartelle_path(workspace_dir)
            if mapping_rel.exists() and cartelle_rel.exists():
                st.caption(f"Mapping: `{mapping_rel}`")
                st.caption(f"Cartelle raw: `{cartelle_rel}`")
                if st.session_state.get("phase") == "ready_to_open":
                    if st.button("Apri workspace", type="primary", width="stretch"):
                        try:
                            _open_workspace(slug, workspace_dir, logger)
                            st.session_state["phase"] = "workspace"
                            st.rerun()
                        except (ConfigError, RuntimeError) as exc:
                            st.error(str(exc))
            else:
                st.info("Inizializza workspace prima di aprirlo")
        except Exception:  # pragma: no cover
            # La sidebar non deve interrompere il rendering principale
            pass


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
            st.caption("Lo slug non puo contenere solo spazi.")

        name_valid = bool(name_trimmed)
        if name_value and not name_valid:
            st.error("Nome cliente non valido")
            st.caption("Il nome non puo contenere solo spazi.")

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
            st.error("Inizializzazione Vision non riuscita")
            st.caption(f"Dettaglio: {exc}")
            logger.warning("ui.new.vision_failed", extra={"slug": slug_trimmed, "error": str(exc)})
        except Exception:  # pragma: no cover
            st.error("Errore inaspettato durante l'inizializzazione del workspace.")
            logger.exception("ui.new.vision_failed_unexpected", extra={"slug": slug_trimmed})
        finally:
            st.session_state["ui.busy.init"] = False

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
                st.success("YAML aggiornati.")
            except ConfigError as exc:
                st.error("Salvataggio YAML non riuscito")
                st.caption(f"Dettaglio: {exc}")

    slug_effective = st.session_state.get("ui.new.slug_effective", "")
    nome_effective = st.session_state.get("ui.new.nome_effective", slug_effective)
    busy_create = bool(st.session_state.get("ui.busy.create_workspace"))

    # 🔁 Bottone UNICO per la creazione
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

    # ➡️ CTA per passare subito alla gestione/semantica
    if st.session_state.get("ui.new.workspace_created") and slug_effective:
        if st.button(
            "Vai all'arricchimento semantico",
            key=f"ui.new.go_semantic.{slug_effective}",
            width="stretch",
        ):
            st.session_state["ui.mode"] = "manage"
            st.session_state["ui.manage_slug"] = slug_effective
            st.session_state["ui.manage.selected_slug"] = slug_effective
            st.rerun()


def _render_manage_client_block(logger: logging.Logger) -> None:
    try:
        clients = load_clients()
    except Exception as exc:  # pragma: no cover
        st.error("Impossibile caricare l'elenco clienti")
        st.caption(f"Dettaglio: {exc}")
        logger.warning("ui.manage.load_clients_failed", extra={"error": str(exc)})
        return

    if not clients:
        st.info("Nessun cliente registrato. Crea un nuovo cliente per iniziare.")
        st.session_state["ui.manage_slug"] = None
        st.session_state.pop("ui.manage.selected_slug", None)
        return

    feedback = st.session_state.pop("ui.manage.feedback", None)
    if feedback:
        status, message = feedback
        if status == "success":
            st.success(message)
        elif status == "error":
            st.error(message)
        elif status == "warning":
            st.warning(message)
        else:
            st.info(message)

    st.subheader("Gestisci cliente")
    slugs = [entry.slug for entry in clients]

    selected_slug = st.session_state.get("ui.manage.selected_slug")
    if not selected_slug or selected_slug not in slugs:
        selected_slug = slugs[0] if slugs else None

    if slugs:
        try:
            selected = st.selectbox(
                "Cliente",
                options=slugs,
                index=slugs.index(selected_slug) if selected_slug else 0,
                key="ui.manage.selectbox",
                help="Seleziona un cliente dall'elenco.",
            )
        except Exception:  # pragma: no cover - compatibilita placeholder
            selected = st.selectbox("Cliente", options=slugs, key="ui.manage.selectbox")
    else:
        selected = None
    st.session_state["ui.manage.selected_slug"] = selected if selected else None

    # stato UI per conferma eliminazione (init PRIMA dei widget)
    st.session_state.setdefault("ui.manage.confirm_open", False)
    st.session_state.setdefault("ui.manage.confirm_target", None)

    col_manage, col_delete = st.columns([1, 1])

    with col_manage:
        if st.button(
            "Gestisci",
            key="ui.manage.button",
            type="primary",
            width="stretch",
            disabled=not selected,
        ):
            st.session_state["ui.manage_slug"] = selected
            logger.info("ui.manage.slug_selected", extra={"slug": selected})
            st.rerun()

    with col_delete:
        # Chiave univoca per evitare duplicate key
        if st.button(
            "Elimina",
            key=f"ui.manage.delete_button.{selected or 'none'}",
            width="stretch",
            disabled=not selected,
        ):
            # Apri modale di conferma in un nuovo rerun
            if selected:
                st.session_state["ui.manage.confirm_open"] = True
                st.session_state["ui.manage.confirm_target"] = selected
                # reset dello stato digitato (prima di renderizzare la text_input)
                typed_key = f"ui.manage.confirm_typed.{selected}"
                if typed_key in st.session_state:
                    st.session_state.pop(typed_key)
                st.rerun()

    # Modale di conferma eliminazione (gestita fuori dalle colonne)
    if st.session_state.get("ui.manage.confirm_open"):
        target = st.session_state.get("ui.manage.confirm_target")
        if target:
            confirm_key = f"ui.manage.confirm_typed.{target}"

            def _delete_dialog_body() -> None:
                st.error("Azione irreversibile. Digita lo slug per confermare e poi premi elimina.")
                st.text_input("Scrivi lo slug esatto per confermare", key=confirm_key, placeholder=target)
                c1, c2 = st.columns(2)
                with c1:
                    if st.button("Annulla", key=f"ui.manage.cancel_delete.{target}", width="stretch"):
                        st.session_state["ui.manage.confirm_open"] = False
                        st.session_state["ui.manage.confirm_target"] = None
                        st.session_state.pop(confirm_key, None)
                        st.rerun()
                with c2:
                    confirmed = st.session_state.get(confirm_key, "") == target
                    if st.button(
                        "Elimina definitivamente",
                        key=f"ui.manage.confirm_delete.{target}",
                        type="primary",
                        width="stretch",
                        disabled=not confirmed,
                    ):
                        with st.spinner(f"Elimino '{target}' da locale, DB e Drive..."):
                            ok, message = _ui_delete_client_via_tool(target)
                        if ok:
                            # feedback sintetico, niente log dump in UI
                            st.session_state["ui.manage.feedback"] = ("success", f"Cliente '{target}' eliminato.")
                            # chiudi modale e ripulisci stato
                            st.session_state["ui.manage.confirm_open"] = False
                            st.session_state["ui.manage.confirm_target"] = None
                            st.session_state.pop(confirm_key, None)
                            # reset selezione se serviva
                            if target == st.session_state.get("ui.manage_slug"):
                                st.session_state.pop("ui.manage_slug", None)
                            st.session_state["ui.manage.selected_slug"] = None
                            st.rerun()
                        else:
                            st.error(f"Errore eliminazione: {message}")

            # mostra dialog compatibile
            _ui_dialog(f"Conferma eliminazione '{target}'", _delete_dialog_body)

    slug = st.session_state.get("ui.manage_slug")
    if not slug:
        st.info("Seleziona un cliente e premi 'Gestisci' per accedere agli strumenti dedicati.")
        return

    _render_manage_client_view(slug, logger)


def _render_manage_semantic_tab(slug: str, workspace_dir: Path, logger: logging.Logger) -> None:
    mapping_rel = _mapping_path(workspace_dir)
    cartelle_rel = _cartelle_path(workspace_dir)
    mapping_key = f"ui.manage.{slug}.mapping_text"
    cartelle_key = f"ui.manage.{slug}.cartelle_text"

    if mapping_key not in st.session_state:
        try:
            st.session_state[mapping_key] = _load_yaml_text(workspace_dir, mapping_rel)
        except ConfigError:
            st.session_state[mapping_key] = ""
    if cartelle_key not in st.session_state:
        try:
            st.session_state[cartelle_key] = _load_yaml_text(workspace_dir, cartelle_rel)
        except ConfigError:
            st.session_state[cartelle_key] = ""

    with st.form(f"manage_semantic_form_{slug}"):
        st.text_area("semantic/semantic_mapping.yaml", key=mapping_key, height=320)
        st.text_area("semantic/cartelle_raw.yaml", key=cartelle_key, height=320)
        saved = st.form_submit_button(
            "Salva YAML",
            type="primary",
            width="stretch",
        )

    if saved:
        try:
            _validate_yaml_dict(st.session_state[mapping_key], "semantic_mapping.yaml")
            _validate_yaml_dict(st.session_state[cartelle_key], "cartelle_raw.yaml")
            mapping_rel.parent.mkdir(parents=True, exist_ok=True)
            cartelle_rel.parent.mkdir(parents=True, exist_ok=True)
            _save_yaml_text(workspace_dir, mapping_rel, st.session_state[mapping_key])
            _save_yaml_text(workspace_dir, cartelle_rel, st.session_state[cartelle_key])
            st.success("YAML aggiornati.")
            logger.info("ui.manage.semantic_saved", extra={"slug": slug})
        except ConfigError as exc:
            st.error(str(exc))


def _render_manage_client_view(slug: str, logger: logging.Logger | None = None) -> None:
    logger = logger or logging.getLogger("ui.manage_client")
    workspace_dir = _workspace_dir_for(slug)

    st.subheader(f"Gestisci cliente - {slug}")
    if workspace_dir.exists():
        st.caption(f"Workspace: {workspace_dir}")
    else:
        st.warning("Workspace locale non trovato. Alcune funzionalita potrebbero non funzionare.")

    st.markdown("#### Navigazione rapida")
    st.markdown("- [Drive](#section-drive)\n- [Editor YAML](#section-yaml)\n- [Semantica](#section-semantic)")

    raw_dir = workspace_dir / "raw"
    raw_exists = raw_dir.exists() and raw_dir.is_dir()

    st.session_state.setdefault("ui.busy.download_raw", False)
    st.session_state.setdefault("ui.busy.extract_tags", False)

    download_busy = bool(st.session_state.get("ui.busy.download_raw"))
    download_available = callable(download_raw_from_drive_with_progress)
    extract_busy = bool(st.session_state.get("ui.busy.extract_tags"))

    st.markdown("<a id='section-drive'></a>", unsafe_allow_html=True)
    col_drive, col_diff, col_tags = st.columns([3, 4, 3])
    drive_index: Dict[str, Dict[str, Any]] = {}

    with col_drive:
        st.subheader(f"Albero Drive (DRIVE_ID/{slug})")
        st.caption("Focus su raw/ e sottocartelle.")
        if callable(render_drive_tree):
            try:
                drive_index = render_drive_tree(slug)
            except Exception as exc:  # pragma: no cover
                st.error("Impossibile caricare l'albero Drive")
                st.caption(f"Dettaglio: {exc}")
                logger.warning("ui.manage.drive_tree_failed", extra={"slug": slug, "error": str(exc)})
        else:
            st.info("Albero Drive non disponibile in questo ambiente.")

    with col_diff:
        st.subheader("Differenze Drive/Locale")
        download_clicked = st.button(
            "Scarica da Drive in raw/",
            type="primary",
            width="stretch",
            disabled=download_busy or not download_available,
            help="Scarica i PDF da DRIVE_ID/<slug>/raw/ nella cartella locale raw/.",
        )
        if download_clicked and download_available and not download_busy:
            st.session_state["ui.busy.download_raw"] = True
            status = None
            try:
                status = st.status("Scaricamento da Drive in corso...", expanded=True)
                with status:
                    status.write("Connessione a Drive...")
                    download_raw_from_drive_with_progress(slug=slug, logger=logger)
                    status.update(label="Scaricamento completato", state="complete", expanded=False)
                try:
                    set_state(slug, "pronto")
                    logger.info("ui.state.updated", extra={"slug": slug, "state": "pronto"})
                    st.toast("Stato cliente aggiornato a 'pronto'.")
                except Exception as state_exc:  # pragma: no cover
                    logger.warning("ui.state.update_failed", extra={"slug": slug, "error": str(state_exc)})
                st.success("Scaricamento completato")
                st.rerun()
            except Exception as exc:  # pragma: no cover
                if status is not None:
                    status.update(label="Scaricamento interrotto", state="error", expanded=False)
                st.error("Scaricamento da Drive non riuscito")
                st.caption(f"Dettaglio: {exc}")
                logger.warning("ui.manage.download_raw_failed", extra={"slug": slug, "error": str(exc)})
            finally:
                st.session_state["ui.busy.download_raw"] = False
        elif download_clicked and not download_available:
            st.warning("Scaricamento da Drive non disponibile in questo ambiente.")

        if callable(render_drive_local_diff):
            try:
                render_drive_local_diff(slug, drive_index)
            except Exception as exc:  # pragma: no cover
                st.error("Diff Drive/Locale non riuscito")
                st.caption(f"Dettaglio: {exc}")
                logger.warning("ui.manage.diff_failed", extra={"slug": slug, "error": str(exc)})
        else:
            st.info("Diff Drive/locale non ancora disponibile.")

    with col_tags:
        st.subheader("Tag revisionati")
        if callable(edit_tags_reviewed):
            try:
                edit_tags_reviewed(slug)
            except Exception as exc:  # pragma: no cover
                st.error("Impossibile mostrare tags_reviewed.yaml")
                st.caption(f"Dettaglio: {exc}")
                logger.warning("ui.manage.tags_editor_failed", extra={"slug": slug, "error": str(exc)})
        else:
            st.info("Editor tags non disponibile in questo ambiente.")

        extract_disabled = not raw_exists or not callable(run_tags_update) or extract_busy
        extract_clicked = st.button(
            "Estrai Tags",
            type="primary",
            width="stretch",
            disabled=extract_disabled,
            help="Aggiorna tags_reviewed.yaml analizzando i contenuti in raw/.",
        )
        if extract_clicked and callable(run_tags_update) and not extract_busy and raw_exists:
            st.session_state["ui.busy.extract_tags"] = True
            status = None
            try:
                status = st.status("Estrazione tag in corso...", expanded=True)
                with status:
                    status.write("Analisi dei PDF in raw/...")
                    run_tags_update(slug)
                    status.update(label="Estrazione completata", state="complete", expanded=False)
                st.success("Estrai Tags completato")
                st.toast("tags_reviewed.yaml aggiornato.")
                st.rerun()
            except Exception as exc:  # pragma: no cover
                if status is not None:
                    status.update(label="Estrazione interrotta", state="error", expanded=False)
                st.error("Estrazione tag non riuscita")
                st.caption(f"Dettaglio: {exc}")
                logger.warning("ui.manage.tags_extract_failed", extra={"slug": slug, "error": str(exc)})
            finally:
                st.session_state["ui.busy.extract_tags"] = False
        elif extract_clicked and not raw_exists:
            st.warning("Cartella raw/ locale non disponibile.")
        elif extract_clicked and not callable(run_tags_update):
            st.warning("Adapter Estrai Tags non disponibile in questo ambiente.")

    st.markdown("<a id='section-yaml'></a><a id='section-semantic'></a>", unsafe_allow_html=True)
    st.subheader("Semantica")
    # 🔄 Aggiorna elenco file su Drive e ricalcola le differenze
    refresh_col, _ = st.columns([1, 3])
    if refresh_col.button(
        "Aggiorna elenco Drive",
        key=f"ui.manage.refresh_drive.{slug}",
        help="Rileggi l'albero su Drive e aggiorna le differenze Drive/Locale.",
        width="stretch",
    ):
        try:
            # forza l’invalidazione di eventuali cache dati usate dai componenti Drive
            if hasattr(st, "cache_data") and hasattr(st.cache_data, "clear"):
                st.cache_data.clear()
        except Exception:
            pass
        st.toast("Elenco Drive aggiornato. Ricalcolo in corso…")
        try:
            st.rerun()
        except Exception:
            pass
    state_val = (get_state(slug) or "").lower()
    eligible_states = {"pronto", "arricchito", "finito"}

    if state_val in eligible_states:
        sem_tabs = st.tabs(["Semantica"])
        with sem_tabs[0]:
            st.caption("Editor YAML semantici.")
            if callable(edit_semantic_mapping):
                edit_semantic_mapping(slug)
            if callable(edit_cartelle_raw):
                edit_cartelle_raw(slug)
    else:
        st.info("La semantica sara' disponibile quando lo stato raggiunge 'pronto' (dopo il download dei PDF in raw/).")


def main() -> None:
    logger = _setup_logging()
    if st is not None:
        st.set_page_config(
            page_title="Onboarding NeXT - Clienti",
            layout="wide",
            page_icon=str(REPO_ROOT / "assets" / "ico-next.png"),
        )

    phase = st.session_state.get("phase", "landing")
    slug = st.session_state.get("slug")
    workspace_dir = Path(st.session_state.get("workspace_dir", "")) if slug else None

    # Sidebar scorciatoie (non bloccante)
    _render_sidebar_shortcuts(slug, workspace_dir, logger)
    _render_header(slug)

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
