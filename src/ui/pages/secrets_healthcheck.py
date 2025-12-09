# SPDX-License-Identifier: GPL-3.0-or-later
"""
Secrets Healthcheck: panoramica delle variabili d'ambiente sensibili.
- Mostra stato ✅/❌ senza rivelare i valori.
- Permette di leggere la guida contestuale per ogni secret (modal).
- Permette di testare il FORMATO (e in futuro il funzionamento) dei valori,
  prima di inserirli in .env.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, List, cast

import yaml

from ui.utils.route_state import clear_tab, get_slug_from_qp, get_tab, set_tab  # noqa: F401
from ui.utils.stubs import get_streamlit

st = get_streamlit()

from pipeline.env_utils import ensure_dotenv_loaded, get_env_var
from pipeline.logging_utils import get_structured_logger
from pipeline.path_utils import read_text_safe
from pipeline.secret_checks import SecretTestResult, test_secret
from pipeline.settings import Settings
from ui.chrome import render_chrome_then_require

logger = get_structured_logger(__name__)

GUIDE_PATH = Path(__file__).resolve().with_name("secrets_guide.yaml")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _status_emoji(present: bool, required: bool) -> str:
    if present:
        return "✅ Presente"
    if required:
        return "❌ Mancante"
    return "⚠️ Assente (opzionale)"


def _safe_lookup(name: str) -> bool:
    try:
        value = get_env_var(name, default=None)
    except KeyError:
        return False
    except Exception:
        return False
    return bool(value and str(value).strip())


def _load_guide() -> Dict[str, Dict[str, Any]]:
    """
    Carica la guida dei secrets da secrets_guide.yaml.

    Formato atteso:
    secrets:
      NAME:
        description: ...
        howto: |
          ...
    """
    try:
        if not GUIDE_PATH.is_file():
            logger.info("ui.secrets_guide.missing", extra={"file_path": str(GUIDE_PATH)})
            return {}

        text = read_text_safe(GUIDE_PATH.parent, GUIDE_PATH, encoding="utf-8")
        data = yaml.safe_load(text) or {}
        if not isinstance(data, dict):
            return {}
        secrets = data.get("secrets", data)
        if not isinstance(secrets, dict):
            return {}
        # normalizziamo le chiavi a stringa
        return {str(k): (v or {}) for k, v in secrets.items() if isinstance(v, dict)}
    except Exception:  # noqa: BLE001
        logger.exception("ui.secrets_guide.load_failed", extra={"file_path": str(GUIDE_PATH)})
        return {}


def _render_test_result(result: SecretTestResult) -> None:
    if result.level == "success":
        st.success(result.message)
    elif result.level == "warning":
        st.warning(result.message)
    else:
        st.error(result.message)
    if result.details:
        st.caption(result.details)


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------


def main() -> None:
    render_chrome_then_require(
        allow_without_slug=True,
        title="Secrets Healthcheck",
        subtitle=(
            "Controlla lo stato delle variabili d'ambiente richieste. "
            "I valori non vengono mai mostrati; puoi leggere la guida e testare il formato "
            "prima di aggiornare il tuo `.env`."
        ),
    )

    env_path = Path(".env")
    try:
        ensure_dotenv_loaded()
    except Exception:  # noqa: BLE001
        # In caso di problemi con dotenv mostriamo comunque gli stati
        logger.exception("ui.secrets_health.env_load_failed", extra={"env_path": str(env_path)})

    catalog: List[Dict[str, Any]] = Settings.env_catalog()
    guide = _load_guide()

    # Modal (se disponibile) per mostrare l'howto dettagliato
    dialog_factory = getattr(st, "dialog", None)
    if callable(dialog_factory):
        DialogFactory = Callable[[str], Callable[[Callable[[], None]], Callable[[], None]]]
        dialog = cast(DialogFactory, dialog_factory)

        @dialog("Guida variabile d'ambiente")
        def _show_secret_dialog() -> None:
            name = st.session_state.get("secret_info_name")
            if not name:
                return
            entry = guide.get(name, {})
            title = entry.get("title") or name
            description = entry.get("description") or ""
            howto = entry.get("howto") or "Guida non disponibile per questa variabile."

            st.markdown(f"### {title}")
            if description:
                st.caption(description)
            st.markdown(howto)

    missing_required = False

    for item in catalog:
        name = str(item.get("name"))
        required = bool(item.get("required", False))
        description = str(item.get("description", ""))

        present = _safe_lookup(name)
        if required and not present:
            missing_required = True

        guide_entry = guide.get(name, {})
        has_guide = bool(guide_entry.get("howto"))

        col_name, col_status, col_actions = st.columns([2, 2, 3])

        with col_name:
            # Solo descrizione + nome variabile in corsivo, più grande e in grassetto
            if description:
                st.markdown(f"**{description} (*{name}*)**")
            else:
                st.markdown(f"**(*{name}*)**")

        with col_status:
            # Info + stato sulla stessa riga
            if has_guide:
                info_col, state_col = st.columns([1, 3])
                with info_col:
                    if st.button(
                        "ℹ️",
                        key=f"info_{name}",
                        help="Apri la guida per questa variabile.",
                    ):
                        st.session_state["secret_info_name"] = name
                with state_col:
                    st.markdown(_status_emoji(present, required))
            else:
                st.markdown(_status_emoji(present, required))

        with col_actions:
            # Input di test + pulsante Test sulla stessa linea (8/2)
            input_col, btn_col = st.columns([8, 2])

            with input_col:
                test_value = st.text_input(
                    label="",
                    value=st.session_state.get(f"secret_test_value_{name}", ""),
                    key=f"secret_test_value_{name}",
                    placeholder="Incolla qui il valore da provare",
                    label_visibility="collapsed",
                )

            with btn_col:
                if st.button("Test", key=f"test_btn_{name}"):
                    if not test_value.strip():
                        st.session_state[f"secret_test_result_{name}"] = SecretTestResult(
                            ok=False,
                            level="error",
                            message="Inserisci un valore prima di eseguire il test.",
                            details=None,
                        )
                    else:
                        result = test_secret(name, test_value, context={"required": required})
                        st.session_state[f"secret_test_result_{name}"] = result

            result_obj = st.session_state.get(f"secret_test_result_{name}")
            if isinstance(result_obj, SecretTestResult):
                _render_test_result(result_obj)

        st.markdown("---")

    # Messaggio di stato globale
    if missing_required:
        st.error(
            "Alcune variabili obbligatorie risultano mancanti. " "Aggiorna il tuo `.env` prima di proseguire.",
            icon="🚫",
        )
    else:
        st.success("Tutte le variabili obbligatorie risultano impostate.", icon="✅")

    # Apertura del modal (se supportato), altrimenti fallback inline
    info_name = st.session_state.get("secret_info_name")
    if info_name and guide.get(info_name):
        if dialog_factory is not None:
            _show_secret_dialog()
        else:
            # Fallback per ambienti senza st.dialog (es. alcuni test)
            entry = guide[info_name]
            title = entry.get("title") or info_name
            howto = entry.get("howto") or "Guida non disponibile per questa variabile."
            st.markdown(f"### {title}")
            st.info(howto)


if __name__ == "__main__":  # pragma: no cover
    main()
