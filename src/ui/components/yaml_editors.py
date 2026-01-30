# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

from pipeline.logging_utils import get_structured_logger

"""
Editor YAML per i file semantici.

"""

from pathlib import Path
from typing import cast

import yaml

from pipeline.exceptions import ConfigError
from pipeline.path_utils import ensure_within_and_resolve, read_text_safe
from pipeline.workspace_layout import WorkspaceLayout
from pipeline.yaml_utils import clear_yaml_cache
from ui.utils.workspace import get_ui_workspace_layout

try:
    import streamlit as st
except Exception:  # pragma: no cover
    st = None

from pipeline.file_utils import safe_write_text
from storage.tags_store import import_tags_yaml_to_db

from ..const import DEFAULT_ENCODING
from ..utils.streamlit_fragments import run_fragment

LOGGER = get_structured_logger("ui.components.yaml_editors")


def _show_error(message: str, exc: Exception) -> None:
    if st is None:
        return
    st.error(message)
    with st.expander("Dettagli tecnici", expanded=False):
        st.exception(exc)


SEMANTIC_DIR = "semantic"
MAPPING_FILE = "semantic_mapping.yaml"
TAGS_FILE = "tags_reviewed.yaml"


def _require_layout(slug: str) -> WorkspaceLayout:
    slug_value = (slug or "").strip()
    if not slug_value:
        raise ConfigError("Slug mancante per gli editor YAML.")
    try:
        return get_ui_workspace_layout(slug_value, require_drive_env=False)
    except Exception as exc:
        raise ConfigError(
            "Impossibile risolvere il layout workspace: "
            "usa pipeline.workspace_bootstrap per creare o riparare il workspace.",
            slug=slug_value,
        ) from exc


def _semantic_path(slug: str, filename: str) -> Path:
    layout = _require_layout(slug)
    semantic_dir = layout.semantic_dir
    return cast(
        Path,
        ensure_within_and_resolve(semantic_dir, semantic_dir / filename),
    )


def _read_yaml_text(slug: str, filename: str) -> str:
    path = _semantic_path(slug, filename)
    if not path.exists():
        raise ConfigError(f"File `{path}` non trovato. Genera gli artefatti Vision e riprova.")
    layout = _require_layout(slug)
    return cast(str, read_text_safe(layout.repo_root_dir, path, encoding=DEFAULT_ENCODING))


def _write_yaml_text(slug: str, filename: str, content: str) -> None:
    path = _semantic_path(slug, filename)
    safe_write_text(path, content, encoding=DEFAULT_ENCODING, atomic=True)
    clear_yaml_cache()
    if filename == TAGS_FILE:
        try:
            import_tags_yaml_to_db(path)
        except Exception as exc:  # pragma: no cover - feedback in UI
            LOGGER.warning(
                "ui.yaml_editor.tags.sync_failed",
                extra={"slug": slug, "file": str(path), "error": str(exc)},
            )
            raise
    LOGGER.info("ui.yaml_editor.saved", extra={"slug": slug, "file": str(path)})


def _require_streamlit() -> None:
    if st is None:
        raise ConfigError("Streamlit non disponibile per gli editor YAML.")


def edit_semantic_mapping(slug: str) -> None:
    def _body() -> None:
        _require_streamlit()
        try:
            original = _read_yaml_text(slug, MAPPING_FILE)
        except ConfigError as exc:
            st.error("File non disponibile")
            st.caption(f"Dettaglio: {exc}")
            return

        state_key = f"yaml_mapping::{slug}"
        if state_key not in st.session_state:
            st.session_state[state_key] = original

        st.subheader("semantic_mapping.yaml")
        st.caption(f"Percorso: output/timmy-kb-{slug}/semantic/{MAPPING_FILE}")
        # UI: descrizione più esplicita per screen reader
        st.caption(
            "Schema minimo: context.slug, context.client_name, areas[]. "
            "Usa YAML valido. Il salvataggio è atomico con guardie di path-safety."
        )

        text_value = st.text_area(
            "Contenuto mapping (YAML)",
            key=state_key,
            height=360,
            help=(
                "Inserisci YAML valido con i campi obbligatori: context.slug, "
                "context.client_name e 'areas' (lista non vuota)."
            ),
        )
        line_count = text_value.count("\n") + 1
        st.caption(f"Totale righe: {line_count}")

        if st.button("Salva mapping", key=f"save_mapping.{slug}", type="primary", width="stretch"):
            try:
                data = yaml.safe_load(text_value) or {}
                if not isinstance(data, dict):
                    raise ConfigError("Mapping non valido: atteso oggetto YAML (dict).")
                context = data.get("context")
                if not isinstance(context, dict):
                    raise ConfigError("Mapping non valido: blocco 'context' mancante.")
                for required in ("slug", "client_name"):
                    if required not in context:
                        raise ConfigError(f"Campo obbligatorio mancante in context: '{required}'.")
                areas = data.get("areas")
                if not isinstance(areas, list) or not areas:
                    raise ConfigError("Mapping non valido: lista 'areas' assente o vuota.")
                _write_yaml_text(slug, MAPPING_FILE, text_value)
                st.success("semantic_mapping.yaml salvato correttamente.")
            except ConfigError as exc:
                _show_error("Salvataggio non riuscito", exc)
            except yaml.YAMLError as exc:  # pragma: no cover
                _show_error("YAML non valido", exc)

    run_fragment(f"yaml_editor.mapping.{slug}", _body)


def edit_tags_reviewed(slug: str) -> None:
    def _body() -> None:
        _require_streamlit()
        try:
            original = _read_yaml_text(slug, TAGS_FILE)
        except ConfigError as exc:
            st.error("File non disponibile")
            st.caption(f"Dettaglio: {exc}")
            return

        state_key = f"yaml_tags::{slug}"
        if state_key not in st.session_state:
            st.session_state[state_key] = original

        st.subheader("Tag revisionati")
        st.caption(f"Percorso: output/timmy-kb-{slug}/semantic/{TAGS_FILE}")
        st.caption("Accetta dict (chiave→metadati) o lista (elenco tag).")

        text_value = st.text_area(
            "Contenuto tags_reviewed.yaml (YAML)",
            key=state_key,
            height=360,
            help="Il contenuto puo essere un dict non vuoto o una lista non vuota.",
        )
        line_count = text_value.count("\n") + 1
        st.caption(f"Totale righe: {line_count}")

        if st.button("Salva tags", key=f"save_tags.{slug}", type="primary", width="stretch"):
            try:
                data = yaml.safe_load(text_value) or {}
                if isinstance(data, dict):
                    if not data:
                        raise ConfigError("tags_reviewed non puo essere vuoto.")
                elif isinstance(data, list):
                    if not data:
                        raise ConfigError("tags_reviewed non puo essere una lista vuota.")
                else:
                    raise ConfigError("tags_reviewed deve essere un dict o una lista.")
                _write_yaml_text(slug, TAGS_FILE, text_value)
                st.success("tags_reviewed.yaml salvato correttamente.")
            except ConfigError as exc:
                _show_error("Salvataggio non riuscito", exc)
            except yaml.YAMLError as exc:  # pragma: no cover
                _show_error("YAML non valido", exc)

    run_fragment(f"yaml_editor.tags.{slug}", _body)
