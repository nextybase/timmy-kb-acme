from __future__ import annotations

"""
YAML editors for semantic workspace files.

UI-only: improves labels/help/accessibility without changing business logic or
side-effects.
"""

import logging
from pathlib import Path
from typing import cast

import yaml

from pipeline.exceptions import ConfigError
from pipeline.path_utils import ensure_within_and_resolve, read_text_safe
from pipeline.yaml_utils import clear_yaml_cache

try:
    import streamlit as st
except Exception:  # pragma: no cover
    st = None

from ui.const import DEFAULT_ENCODING
from ui.utils.core import safe_write_text

LOGGER = logging.getLogger("ui.components.yaml_editors")


def _show_error(message: str, exc: Exception) -> None:
    if st is None:
        return
    st.error(message)
    with st.expander("Dettagli tecnici", expanded=False):
        st.exception(exc)


SEMANTIC_DIR = "semantic"
MAPPING_FILE = "semantic_mapping.yaml"
CARTELLE_FILE = "cartelle_raw.yaml"
TAGS_FILE = "tags_reviewed.yaml"


def _workspace_root(slug: str) -> Path:
    root = Path("output") / f"timmy-kb-{slug}"
    if not root.exists():
        raise ConfigError(f"Workspace locale non trovato: {root}")
    return root


def _semantic_path(slug: str, filename: str) -> Path:
    workspace = _workspace_root(slug)
    return cast(
        Path,
        ensure_within_and_resolve(workspace, workspace / SEMANTIC_DIR / filename),
    )


def _read_yaml_text(slug: str, filename: str) -> str:
    path = _semantic_path(slug, filename)
    if not path.exists():
        raise ConfigError(f"File `{path}` non trovato. Genera gli artefatti Vision e riprova.")
    return cast(str, read_text_safe(_workspace_root(slug), path, encoding=DEFAULT_ENCODING))


def _write_yaml_text(slug: str, filename: str, content: str) -> None:
    path = _semantic_path(slug, filename)
    safe_write_text(path, content, encoding=DEFAULT_ENCODING, atomic=True)
    clear_yaml_cache()
    LOGGER.info("ui.yaml_editor.saved", extra={"slug": slug, "file": str(path)})


def _require_streamlit() -> None:
    if st is None:
        raise ConfigError("Streamlit non disponibile per gli editor YAML.")


def edit_semantic_mapping(slug: str) -> None:
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

    if st.button("Salva mapping", type="primary"):
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


def edit_cartelle_raw(slug: str) -> None:
    _require_streamlit()
    try:
        original = _read_yaml_text(slug, CARTELLE_FILE)
    except ConfigError as exc:
        st.error("File non disponibile")
        st.caption(f"Dettaglio: {exc}")
        return

    state_key = f"yaml_cartelle::{slug}"
    if state_key not in st.session_state:
        st.session_state[state_key] = original

    st.subheader("cartelle_raw.yaml")
    st.caption(f"Percorso: output/timmy-kb-{slug}/semantic/{CARTELLE_FILE}")
    st.caption("Schema atteso: nodo radice dict con chiave 'raw' → {cartella: {...}}.")

    text_value = st.text_area(
        "Contenuto cartelle_raw (YAML)",
        key=state_key,
        height=360,
        help=("Assicurati che esista il nodo 'raw' e che i nomi cartella non siano " "vuoti o duplicati."),
    )
    line_count = text_value.count("\n") + 1
    st.caption(f"Totale righe: {line_count}")

    if st.button("Salva cartelle", type="primary"):
        try:
            data = yaml.safe_load(text_value) or {}
            if not isinstance(data, dict):
                raise ConfigError("cartelle_raw deve essere un oggetto YAML.")
            context = data.get("context")
            if not isinstance(context, dict):
                raise ConfigError("cartelle_raw richiede il blocco 'context'.")
            for required in ("slug", "client_name"):
                if required not in context:
                    raise ConfigError(f"Campo obbligatorio mancante in context: '{required}'.")
            raw_section = data.get("raw")
            if not isinstance(raw_section, dict):
                raise ConfigError("cartelle_raw deve contenere il blocco 'raw'.")
            seen: set[str] = set()
            for name in raw_section.keys():
                cleaned = str(name).strip()
                if not cleaned:
                    raise ConfigError("cartelle_raw contiene nomi di cartella vuoti.")
                if cleaned in seen:
                    raise ConfigError(f"cartelle_raw contiene duplicati: '{cleaned}'.")
                seen.add(cleaned)
            _write_yaml_text(slug, CARTELLE_FILE, text_value)
            st.success("cartelle_raw.yaml salvato correttamente.")
        except ConfigError as exc:
            _show_error("Salvataggio non riuscito", exc)
        except yaml.YAMLError as exc:  # pragma: no cover
            _show_error("YAML non valido", exc)


def edit_tags_reviewed(slug: str) -> None:
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

    if st.button("Salva tags", type="primary"):
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
