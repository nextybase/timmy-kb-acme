# SPDX-License-Identifier: GPL-3.0-or-later
"""
Utility per testare i valori delle variabili d'ambiente (secrets).

Obiettivi:
- Non toccare mai .env né os.environ: i test sono stateless.
- Validare almeno il FORMATO del valore fornito dall'utente.
- Dove sensato, dare indicazioni sul livello di confidenza del test.
- Nessun side-effect a import-time, nessuna chiamata di rete automatica.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from pipeline.logging_utils import get_structured_logger
from pipeline.path_utils import read_text_safe

logger = get_structured_logger(__name__)


@dataclass(frozen=True)
class SecretTestResult:
    ok: bool
    level: str  # "success" | "warning" | "error"
    message: str
    details: Optional[str] = None


def _success(msg: str, details: str | None = None) -> SecretTestResult:
    return SecretTestResult(ok=True, level="success", message=msg, details=details)


def _warning(msg: str, details: str | None = None) -> SecretTestResult:
    return SecretTestResult(ok=False, level="warning", message=msg, details=details)


def _error(msg: str, details: str | None = None) -> SecretTestResult:
    return SecretTestResult(ok=False, level="error", message=msg, details=details)


def test_secret(name: str, value: str, context: Dict[str, Any] | None = None) -> SecretTestResult:
    """
    Entry point unico per la UI.

    - name: nome della variabile d'ambiente (es. "OPENAI_API_KEY").
    - value: valore fornito dall'utente per il test (non viene mai salvato altrove).
    - context: spazio per future estensioni (es. flag ambiente, opzioni di debug).

    Il test è volutamente conservativo: se non c'è un check specifico,
    restituiamo un warning informativo.
    """
    context = context or {}
    name = name.strip().upper()
    value = value.strip()

    if not value:
        return _error("Il valore è vuoto. Inserisci un valore prima di eseguire il test.")

    try:
        if name == "SERVICE_ACCOUNT_FILE":
            return _test_service_account_file(value)
        if name == "DRIVE_ID":
            return _test_drive_id(value)
        if name == "DRIVE_PARENT_FOLDER_ID":
            return _test_drive_parent_folder_id(value)
        if name == "OPENAI_API_KEY":
            return _test_openai_api_key(value)
        if name in {"OBNEXT_ASSISTANT_ID", "ASSISTANT_ID"}:
            return _test_openai_assistant_id(value)
        if name == "GOOGLE_CLIENT_ID":
            return _test_google_client_id(value)
        if name == "GOOGLE_CLIENT_SECRET":
            return _test_google_client_secret(value)
        if name == "GOOGLE_REDIRECT_URI":
            return _test_google_redirect_uri(value)
        if name == "ALLOWED_GOOGLE_DOMAIN":
            return _test_allowed_google_domain(value)

    except Exception:  # noqa: BLE001
        logger.exception("secret_checks.unexpected_error", extra={"secret_name": name})
        return _error(
            "Errore imprevisto durante il test.",
            details="Controlla i log dell'applicazione per maggiori dettagli.",
        )

    return _warning(
        "Nessun test specifico implementato per questa variabile.",
        details="Puoi comunque usarla nel tuo .env; questa pagina al momento non offre un controllo dedicato.",
    )


# ---------------------------------------------------------------------------
# Test specifici
# ---------------------------------------------------------------------------


def _test_service_account_file(path_str: str) -> SecretTestResult:
    """
    Controlli per SERVICE_ACCOUNT_FILE:
    - path non vuoto
    - file esistente e leggibile
    - JSON valido
    - struttura compatibile con un Service Account Google
    """
    path = Path(path_str).expanduser()

    if not path.exists():
        return _error("File non trovato.", details=f"Percorso specificato: {path}")
    if not path.is_file():
        return _error("Il percorso indicato non è un file.", details=str(path))

    try:
        raw = read_text_safe(path.parent, path, encoding="utf-8")
    except OSError as exc:
        return _error("Impossibile leggere il file.", details=str(exc))

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return _error("Il file non è un JSON valido.")

    if not isinstance(data, dict):
        return _warning("JSON valido, ma non è un oggetto.", details="Struttura inattesa (non è un dict).")

    keys = set(data.keys())
    expected = {"type", "client_email", "private_key", "project_id"}

    if not expected.issubset(keys):
        return _warning(
            "JSON valido, ma non sembra un Service Account standard.",
            details="Chiavi mancanti rispetto a un SA tipico: " + ", ".join(sorted(expected - keys)),
        )

    return _success(
        "File JSON valido e compatibile con un Service Account Google.",
        details=str(path),
    )


def _test_drive_id(value: str) -> SecretTestResult:
    """
    DRIVE_ID: controlla solo che il formato sia plausibile.
    Un ID Drive tipico è una stringa alfanumerica (più _ e -), senza spazi.
    """
    if " " in value:
        return _error("L'ID non deve contenere spazi.")

    if not re.fullmatch(r"[A-Za-z0-9_\-]{10,200}", value):
        return _warning(
            "Formato atipico per un ID Drive.",
            details="Atteso: stringa alfanumerica (con _ e -), almeno 10 caratteri.",
        )

    return _success(
        "Formato plausibile per un ID Drive.",
        details="La verifica API reale non viene eseguita da qui.",
    )


def _test_drive_parent_folder_id(value: str) -> SecretTestResult:
    """
    DRIVE_PARENT_FOLDER_ID: stessi controlli base di DRIVE_ID.
    """
    base = _test_drive_id(value)
    if base.level == "success":
        return _success(
            "Formato plausibile per un ID cartella Drive.",
            details=base.details,
        )
    return base


def _test_openai_api_key(value: str) -> SecretTestResult:
    """
    OPENAI_API_KEY:
    - deve iniziare con 'sk-'
    - lunghezza minima.
    (Nessuna chiamata di rete automatica, per evitare side-effect in test/CI.)
    """
    if not value.startswith("sk-"):
        return _error(
            "Una chiave OpenAI tipica inizia con 'sk-'.",
            details="Verifica di non aver incollato il valore sbagliato (es. ID modello o assistant).",
        )

    if len(value) < 40:
        return _warning(
            "Chiave molto corta per essere una chiave OpenAI.",
            details="Verifica di aver copiato l'intera stringa, senza troncamenti.",
        )

    return _success(
        "Formato plausibile per una chiave OpenAI.",
        details="Per un test funzionale completo usa gli strumenti di diagnostica LLM.",
    )


def _test_openai_assistant_id(value: str) -> SecretTestResult:
    """
    OBNEXT_ASSISTANT_ID / ASSISTANT_ID:
    - deve iniziare con 'asst_'.
    """
    if not value.startswith("asst_"):
        return _error(
            "Un Assistant ID OpenAI tipico inizia con 'asst_'.",
            details="Verifica di aver copiato l'ID dell'assistant, non altro.",
        )

    if len(value) < 10:
        return _warning(
            "Assistant ID insolitamente corto.",
            details="Controlla di aver copiato la stringa completa.",
        )

    return _success("Formato plausibile per un Assistant ID OpenAI.")


def _test_google_client_id(value: str) -> SecretTestResult:
    """
    GOOGLE_CLIENT_ID:
    - tipicamente termina con '.apps.googleusercontent.com'
    """
    if not value.endswith(".apps.googleusercontent.com"):
        return _warning(
            "Un Client ID Google tipico termina con '.apps.googleusercontent.com'.",
            details="Verifica di aver copiato il Client ID corretto dalla console Google Cloud.",
        )

    if " " in value:
        return _error("Il Client ID non deve contenere spazi.")

    return _success("Formato plausibile per un Google OAuth Client ID.")


def _test_google_client_secret(value: str) -> SecretTestResult:
    """
    GOOGLE_CLIENT_SECRET:
    - non possiamo verificare molto, ci limitiamo a controllare che sia non vuoto
      e senza spazi iniziali/finali.
    """
    if " " in value.strip():
        # alcuni secret contengono caratteri speciali, inclusi '/'
        # ci limitiamo a sconsigliare spazi "gratuiti"
        return _warning(
            "Il Client Secret contiene spazi.",
            details="Verifica di non aver incollato spazi all'inizio o alla fine.",
        )

    if len(value) < 10:
        return _warning(
            "Secret insolitamente corto.",
            details="Controlla che non sia troncato.",
        )

    return _success("Valore plausibile per un Google Client Secret.")


def _test_google_redirect_uri(value: str) -> SecretTestResult:
    """
    GOOGLE_REDIRECT_URI:
    - deve iniziare con http:// o https://
    - non deve contenere spazi.
    """
    if not (value.startswith("http://") or value.startswith("https://")):
        return _error(
            "La redirect URI deve iniziare con 'http://' o 'https://'.",
            details="Verifica che corrisponda alla URI registrata nella Google Cloud Console.",
        )

    if " " in value:
        return _error("La redirect URI non deve contenere spazi.")

    return _success(
        "Formato plausibile per una redirect URI OAuth.",
        details="Accertati che sia esattamente uguale a quella registrata nel Client ID.",
    )


def _test_allowed_google_domain(value: str) -> SecretTestResult:
    """
    ALLOWED_GOOGLE_DOMAIN:
    - deve essere un dominio tipo 'example.com'
    - niente schema, niente slash.
    """
    if "://" in value:
        return _error(
            "Non includere lo schema (http/https) nel dominio.",
            details="Usa solo il dominio, ad esempio 'example.com'.",
        )

    if "/" in value:
        return _error("Il dominio non deve contenere path ('/').")

    if " " in value:
        return _error("Il dominio non deve contenere spazi.")

    if "." not in value:
        return _warning(
            "Dominio senza punto.",
            details="Di solito un dominio aziendale è del tipo 'example.com'.",
        )

    return _success("Formato plausibile per un dominio Google ammesso.")
