# SPDX-License-Identifier: GPL-3.0-or-later
# src/ui/pages/configurazione.py
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Tuple, cast

import yaml

from pipeline.file_utils import safe_write_text
from pipeline.logging_utils import get_structured_logger
from pipeline.settings import Settings
from ui.chrome import header, sidebar
from ui.config_store import get_config_path
from ui.utils.stubs import get_streamlit

st = get_streamlit()
logger = get_structured_logger("ui.configurazione")

REPO_ROOT = Path(__file__).resolve().parents[3]


# ---------------------------------------------------------------------------
# Helpers per metadata delle sezioni
# ---------------------------------------------------------------------------

_SECTION_META: Dict[str, Tuple[str, str]] = {
    "meta": (
        "Metadati cliente",
        "Versioning interno, nominativo cliente, riferimenti SSoT (Vision Statement, mapping semantici).",
    ),
    "ui": (
        "Interfaccia utente",
        "Impostazioni della UI di onboarding (preflight, modalità locale, pannello admin).",
    ),
    "ai": (
        "AI / LLM / Vision",
        "Configurazione OpenAI (timeout/retry) e modelli Vision/Assistants (gli ID restano nei segreti).",
    ),
    "pipeline": (
        "Pipeline",
        "Parametri operativi della pipeline: retriever (throttle/auto_by_budget) e cache RAW.",
    ),
    "security": (
        "Sicurezza e OIDC",
        "Abilitazione OIDC, provider, ruoli e policy di accesso.",
    ),
    "integrations": (
        "Integrazioni esterne",
        "Integrazioni con terze parti (es. Google Drive) e relativi identificativi.",
    ),
    "ops": (
        "Operatività e logging",
        "Log level e opzioni operative per l'istanza di Timmy KB.",
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
    """Restituisce il path safe di config/config.yaml (SSoT globale)."""
    return cast(Path, get_config_path())


def _read_config() -> Dict[str, Any] | None:
    """Legge config/config.yaml via Settings (SSoT) e ritorna il payload dict."""
    try:
        settings = Settings.load(REPO_ROOT, config_path=_get_config_path(), logger=logger)
        data = settings.as_dict()
    except Exception:  # noqa: BLE001
        logger.exception(
            "ui.config.read_error",
            extra={"file_path": str(_get_config_path())},
        )
        return None

    if not isinstance(data, dict):
        logger.warning(
            "ui.config.invalid_root",
            extra={"file_path": str(_get_config_path()), "type": str(type(data))},
        )
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

        # stringa di default
        return st.text_input(
            "",
            value=str(value) if value is not None else "",
            key=widget_key,
            label_visibility="collapsed",
        )


def _render_mapping_inputs(prefix: str, mapping: Dict[str, Any]) -> Dict[str, Any]:
    """
    Rende un mapping (dict) come lista di campi chiave/valore.

    Gestisce ricorsivamente i nested dict chiamando `_render_section_inputs`.
    """
    result: Dict[str, Any] = {}
    for key, value in mapping.items():
        full_key = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            st.markdown(f"**{key}**")
            result[key] = _render_section_inputs(full_key, value)
        else:
            result[key] = _render_scalar_input(full_key, key, value)
    return result


def _render_section_inputs(section_key: str, value: Any) -> Any:
    """Rende gli input per una sezione top-level della config."""
    if isinstance(value, dict):
        return _render_mapping_inputs(section_key, value)
    return _render_scalar_input(section_key, section_key, value)


def _render_config_form(config: Dict[str, Any]) -> Dict[str, Any] | None:
    """
    Rende la form di configurazione e restituisce il dict aggiornato
    quando la form viene inviata, altrimenti None.

    Ogni blocco top-level è un expander apri/chiudi con titolo parlante
    e una breve descrizione.
    """
    with st.form("config_form"):
        st.markdown("Modifica i parametri di configurazione e premi **Salva configurazione**.")

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
        safe_write_text(path, text, encoding="utf-8", atomic=True)
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
