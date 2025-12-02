# SPDX-License-Identifier: GPL-3.0-or-later
# src/ui/pages/configurazione.py
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Tuple, cast

import yaml

from pipeline.file_utils import safe_write_text
from pipeline.logging_utils import get_structured_logger
from pipeline.path_utils import ensure_within_and_resolve, read_text_safe
from ui.chrome import header, sidebar
from ui.utils.stubs import get_streamlit

st = get_streamlit()
logger = get_structured_logger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[3]


# ---------------------------------------------------------------------------
# Helpers per metadata delle sezioni
# ---------------------------------------------------------------------------

_SECTION_META: Dict[str, Tuple[str, str]] = {
    "cartelle_raw_yaml": (
        "Cartelle RAW/YAML",
        "Percorsi base per i file PDF originali e per gli output YAML/Markdown generati.",
    ),
    "N_VER": (
        "Versione NeXT",
        "Parametri di versione interni al framework NeXT.",
    ),
    "DATA_VER": (
        "Versione dati",
        "Versioning dello schema e dei dati gestiti da Timmy KB.",
    ),
    "openai": (
        "OpenAI e LLM",
        "Configurazione dei modelli OpenAI e parametri LLM (le credenziali restano nei segreti).",
    ),
    "vision": (
        "Vision e OCR",
        "Provider e parametri per l’estrazione del testo dai PDF (Vision/OCR).",
    ),
    "ui": (
        "Interfaccia utente",
        "Impostazioni della UI di onboarding (preflight, comportamento schermate, ecc.).",
    ),
    "retriever": (
        "Retriever semantico",
        "Budget di latenza, parallelismo e limiti del retriever semantico.",
    ),
    "raw_cache": (
        "Cache RAW",
        "Strategia di cache per i contenuti RAW e per i risultati intermedi.",
    ),
    "security": (
        "Sicurezza e OIDC",
        "Abilitazione OIDC, provider, ruoli e policy di accesso.",
    ),
    "ops": (
        "Operatività e logging",
        "Log level e opzioni operative per l’istanza di Timmy KB.",
    ),
    "finance": (
        "Costi e budget",
        "Parametri per il controllo dei costi e la gestione del budget.",
    ),
}


def _section_meta(key: str) -> Tuple[str, str]:
    """
    Restituisce (titolo, descrizione) per la sezione.

    Se la chiave non è mappata, usa il nome raw come titolo
    e una descrizione generica.
    """
    title, desc = _SECTION_META.get(
        key,
        (
            key,
            f"Sezione di configurazione per `{key}`.",
        ),
    )
    return title, desc


# ---------------------------------------------------------------------------
# I/O config
# ---------------------------------------------------------------------------


def _get_config_path() -> Path:
    """
    Restituisce il path safe di config/config.yaml usando le utilità
    path-safe della pipeline.
    """
    return cast(
        Path,
        ensure_within_and_resolve(
            REPO_ROOT,
            REPO_ROOT / "config" / "config.yaml",
        ),
    )


def _read_config() -> Dict[str, Any] | None:
    """Legge e parsifica config/config.yaml come dict, se possibile."""
    try:
        path = _get_config_path()
    except Exception:  # noqa: BLE001
        logger.exception("ui.config.path_invalid", extra={"action": "read"})
        return None

    if not path.is_file():
        logger.warning("ui.config.missing", extra={"file_path": str(path)})
        return None

    try:
        text = read_text_safe(path.parent, path, encoding="utf-8")
    except OSError:
        logger.exception("ui.config.read_error", extra={"file_path": str(path)})
        return None

    if not text.strip():
        return {}

    try:
        data = yaml.safe_load(text)
    except Exception:  # noqa: BLE001
        logger.exception("ui.config.parse_error", extra={"file_path": str(path)})
        return None

    if data is None:
        return {}
    if not isinstance(data, dict):
        logger.warning(
            "ui.config.invalid_root",
            extra={"file_path": str(path), "type": str(type(data))},
        )
        # Per questa UI lavoriamo solo su root mapping
        return None

    return data


# ---------------------------------------------------------------------------
# Rendering dei campi
# ---------------------------------------------------------------------------


def _render_scalar_input(full_key: str, label: str, value: Any) -> Any:
    """
    Rende un input per valori scalari (bool / int / float / str),
    mettendo etichetta e campo sulla stessa riga.

    Colonne: ~10% label, ~90% input.
    """
    widget_key = f"cfg_{full_key}"

    # 10% / 90% circa
    col_label, col_input = st.columns([1, 9])

    with col_label:
        st.markdown(label)

    with col_input:
        if isinstance(value, bool):
            return st.checkbox(
                "",
                value=value,
                key=widget_key,
                label_visibility="collapsed",
            )
        if isinstance(value, int) and not isinstance(value, bool):
            return st.number_input(
                "",
                value=value,
                step=1,
                key=widget_key,
                label_visibility="collapsed",
            )
        if isinstance(value, float):
            return st.number_input(
                "",
                value=value,
                key=widget_key,
                label_visibility="collapsed",
            )

        # fallback string
        return st.text_input(
            "",
            value=str(value) if value is not None else "",
            key=widget_key,
            label_visibility="collapsed",
        )


def _render_yaml_input(full_key: str, label: str, value: Any) -> Any:
    """
    Per valori non scalari (liste, strutture complesse) usiamo un text_area
    con YAML embedded, che viene ri-parsato se l’utente lo modifica.
    """
    if value is None:
        serialized = ""
    else:
        try:
            serialized = yaml.safe_dump(
                value,
                sort_keys=False,
                allow_unicode=True,
            ).strip()
        except Exception:  # noqa: BLE001
            serialized = str(value)

    edited = st.text_area(
        label,
        value=serialized,
        key=f"cfg_{full_key}",
        height=140,
    )

    if not edited.strip():
        return None

    try:
        return yaml.safe_load(edited)
    except Exception:  # noqa: BLE001
        st.warning(
            f"Valore non valido per '{label}': non riesco a interpretarlo come YAML. " "Mantengo il valore originale."
        )
        return value


def _render_mapping(path_prefix: str, mapping: Dict[str, Any], level: int = 0) -> Dict[str, Any]:
    """
    Rende un dict arbitrariamente annidato come sottoelenco di input.

    - Nessun expander annidato.
    - Ogni chiave interna diventa un campo singolo.
    - I dict più profondi vengono “aperti” come sottoelenco, ricorsivamente.
    - Le etichette in markdown sono usate solo per i blocchi dict,
      non per le foglie (per evitare ripetizioni).
    """
    updated: Dict[str, Any] = {}

    for sub_key, sub_val in mapping.items():
        full_key = f"{path_prefix}.{sub_key}" if path_prefix else sub_key
        label = sub_key

        if isinstance(sub_val, dict):
            # Heading SOLO per blocchi dict
            if level == 0:
                st.markdown(f"**{label}**")
            elif level == 1:
                st.markdown(f"*{label}*")
            else:
                st.markdown(label)

            updated[sub_key] = _render_mapping(full_key, sub_val, level + 1)

            # Separatore tra blocchi top-level interni
            if level == 0:
                st.markdown("---")
        else:
            # Foglie: solo label del widget, niente markdown aggiuntivo
            if isinstance(sub_val, (bool, int, float, str)) or sub_val is None:
                new_value = _render_scalar_input(full_key, label, sub_val)
            else:
                new_value = _render_yaml_input(full_key, label, sub_val)
            updated[sub_key] = new_value

            if level == 0:
                st.markdown("---")

    return updated


def _render_section_inputs(root_key: str, value: Any) -> Any:
    """
    Rende gli input all'interno di un blocco (expander).

    - Se il valore è un dict: ogni sottovoce diventa un campo singolo,
      con sottoelenco ricorsivo per i dict annidati.
    - Altrimenti: il blocco contiene un singolo input (scalare o YAML).
    """
    if isinstance(value, dict):
        return _render_mapping(root_key, value, level=0)

    # Root non-dict: lo trattiamo come singola voce del blocco
    if isinstance(value, (bool, int, float, str)) or value is None:
        return _render_scalar_input(root_key, root_key, value)

    return _render_yaml_input(root_key, root_key, value)


def _render_config_form(config: Dict[str, Any]) -> Dict[str, Any] | None:
    """
    Rende la form di configurazione e restituisce il dict aggiornato
    quando la form viene inviata, altrimenti None.

    Ogni blocco top-level è un expander apri/chiudi con titolo parlante
    e una breve descrizione.
    """
    with st.form("config_form"):
        st.markdown("Modifica i parametri di configurazione e premi " "**Salva configurazione**.")

        updated: Dict[str, Any] = {}

        # Manteniamo l'ordine di definizione (dict Python 3.7+ è ordered)
        for key, value in config.items():
            title, desc = _section_meta(key)

            with st.expander(title, expanded=False):
                if desc:
                    st.caption(desc)

                new_value = _render_section_inputs(key, value)
                updated[key] = new_value

        submitted = st.form_submit_button("💾 Salva configurazione")

    if not submitted:
        return None
    return updated


def _write_config(config: Dict[str, Any]) -> bool:
    """Serializza e scrive la configurazione su config.yaml in modo safe."""
    try:
        path = _get_config_path()
    except Exception:  # noqa: BLE001
        logger.exception("ui.config.path_invalid", extra={"action": "write"})
        return False

    try:
        text = yaml.safe_dump(
            config,
            sort_keys=False,
            allow_unicode=True,
        )
    except Exception:  # noqa: BLE001
        logger.exception("ui.config.dump_error", extra={"file_path": str(path)})
        return False

    try:
        safe_write_text(path, text)
        logger.info("ui.config.updated", extra={"file_path": str(path)})
        return True
    except OSError:
        logger.exception("ui.config.write_error", extra={"file_path": str(path)})
        return False


def main() -> None:
    """
    Pagina Admin -> Configurazione.

    - Usa la stessa struttura delle altre pagine Admin (header + sidebar).
    - Lavora a livello globale, senza dipendere dallo slug del cliente.
    - Mostra i blocchi di config/config.yaml come expander, con titolo
      esplicativo e piccola descrizione, seguiti dal sottoelenco di voci singole.
    """
    header(None)
    sidebar(None)

    st.subheader("Configurazione")
    st.caption(
        "Gestione dei parametri globali caricati da `config/config.yaml`. "
        "Ogni blocco è apri/chiudi, con le singole voci modificabili."
    )

    config = _read_config()
    if config is None:
        st.error(
            "Non riesco a caricare `config/config.yaml`. "
            "Verifica che il file esista, sia leggibile e abbia sintassi YAML valida."
        )
        return

    updated = _render_config_form(config)
    if updated is None:
        # form non inviata
        return

    if _write_config(updated):
        st.success("Configurazione salvata correttamente.")
    else:
        st.error("Errore durante il salvataggio della configurazione. Controlla i log.")


if __name__ == "__main__":
    main()
