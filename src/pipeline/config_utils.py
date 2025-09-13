# src/pipeline/config_utils.py
"""
Configurazione cliente e utilities (SSoT + path-safety).

Cosa fa questo file
-------------------
Centralizza le utilità di configurazione per la pipeline Timmy-KB:

- `Settings`: modello Pydantic per le variabili ambiente critiche (Drive, GitHub, ecc.),
  con validazione dei campi essenziali e presenza dello `slug`.
- `write_client_config_file(context, config) -> Path`: serializza e salva **atomicamente**
  `config.yaml` nella sandbox del cliente usando `safe_write_text` (backup `.bak` incluso).
- `get_client_config(context) -> dict`: legge e deserializza `config.yaml` dal contesto (errore se assente/malformato).
- `validate_preonboarding_environment(context, base_dir=None)`: verifica minima di ambiente
  (config valido e cartelle chiave come `logs/`).
- `safe_write_file(file_path, content)`: **wrapper legacy** che scrive testo in modo atomico
  passando da `safe_write_text`. Per nuovo codice, usare direttamente `safe_write_text`.
- `update_config_with_drive_ids(context, updates, logger=None)`: merge incrementale su `config.yaml`
  con backup `.bak` e scrittura atomica.

Linee guida implementative
--------------------------
- **SSoT scritture**: tutte le write passano da `pipeline.file_utils.safe_write_text`.
- **Path-safety STRONG**: prima di scrivere nella sandbox, validiamo con `ensure_within(...)`.
- **Niente prompt/exit**: orchestrazione (I/O utente e gestione exit code) demandata ai caller.
"""

from __future__ import annotations

import logging
import shutil
from datetime import date
from pathlib import Path
from typing import Any, Dict, Optional

import yaml
from pydantic import Field, model_validator
from pydantic_settings import BaseSettings as PydanticBaseSettings

from pipeline.constants import BACKUP_SUFFIX, CONFIG_DIR_NAME, CONFIG_FILE_NAME
from pipeline.context import ClientContext
from pipeline.exceptions import ConfigError, PipelineError, PreOnboardingValidationError
from pipeline.file_utils import safe_write_text
from pipeline.logging_utils import get_structured_logger
from pipeline.path_utils import ensure_within

logger = get_structured_logger("pipeline.config_utils")


# ----------------------------------------------------------
#  Modello pydantic per configurazione cliente
# ----------------------------------------------------------
class Settings(PydanticBaseSettings):
    """Modello di configurazione cliente per pipeline Timmy-KB.

    Le variabili sono risolte dall'ambiente (.env/processo) tramite Pydantic.
    I campi critici vengono validati nel validator `check_critical`.

    Attributi (principali):
        DRIVE_ID: ID dello Shared Drive (critico).
        SERVICE_ACCOUNT_FILE: Path al JSON del Service Account (critico).
        BASE_DRIVE: (opz.) Nome base per Drive.
        DRIVE_ROOT_ID: (opz.) ID della cartella radice cliente su Google Drive.
        GITHUB_TOKEN: Token GitHub per operazioni di push (critico).
        GITBOOK_TOKEN: (opz.) Token GitBook.
        slug: Identificativo cliente (necessario a runtime tramite `ClientContext`).
        LOG_LEVEL: Livello di log (default: "INFO").
        DEBUG: Flag di debug (default: False).
    """

    # Parametri Google Drive
    DRIVE_ID: str = Field(..., env="DRIVE_ID")  # type: ignore[call-arg]
    SERVICE_ACCOUNT_FILE: str = Field(..., env="SERVICE_ACCOUNT_FILE")  # type: ignore[call-arg]
    BASE_DRIVE: Optional[str] = Field(None, env="BASE_DRIVE")  # type: ignore[call-arg]
    DRIVE_ROOT_ID: Optional[str] = Field(
        None,
        env="DRIVE_ROOT_ID",  # type: ignore[call-arg]
        description="ID cartella radice cliente su Google Drive",
    )

    # Parametri GitHub/GitBook
    GITHUB_TOKEN: str = Field(..., env="GITHUB_TOKEN")  # type: ignore[call-arg]
    GITBOOK_TOKEN: Optional[str] = Field(None, env="GITBOOK_TOKEN")  # type: ignore[call-arg]

    # Identificativo cliente e log
    slug: Optional[str] = None
    LOG_LEVEL: str = Field("INFO", env="LOG_LEVEL")  # type: ignore[call-arg]
    DEBUG: bool = Field(False, env="DEBUG")  # type: ignore[call-arg]

    @model_validator(mode="after")
    def check_critical(self) -> "Settings":
        """Valida la presenza dei parametri critici e dello slug.

        Raises:
            ValueError: se una variabile critica è mancante o se `slug` è assente.
        """
        required = ["DRIVE_ID", "SERVICE_ACCOUNT_FILE", "GITHUB_TOKEN"]
        for key in required:
            if not getattr(self, key, None):
                logger.error(f"Parametro critico '{key}' mancante!")
                raise ValueError(f"Parametro critico '{key}' mancante!")

        if not self.slug:
            logger.error("Parametro 'slug' mancante! Usare ClientContext.load(slug).")
            raise ValueError("Parametro 'slug' mancante!")

        return self


# ----------------------------------------------------------
#  Scrittura configurazione cliente su file YAML
# ----------------------------------------------------------
def write_client_config_file(context: ClientContext, config: Dict[str, Any]) -> Path:
    """Scrive il file `config.yaml` nella cartella cliente in modo atomico (backup + SSoT).

    Strategia:
      - Crea `config/` se assente.
      - Se esiste già un config, crea backup `<config.yaml>.bak`.
      - Serializza YAML e scrive con `safe_write_text(..., atomic=True)`.

    Args:
        context: Contesto del cliente (fornisce perimetro sandbox).
        config: Dizionario di configurazione.

    Restituisce:
        Path al file `config.yaml` scritto.

    Raises:
        ConfigError: in caso di errore I/O.
    """
    # Fail-fast esplicito su campi richiesti del contesto
    if context.output_dir is None or context.base_dir is None:
        raise PipelineError(
            "Contesto incompleto: output_dir/base_dir mancanti",
            slug=context.slug,
        )
    config_dir = context.output_dir / CONFIG_DIR_NAME
    config_path = config_dir / CONFIG_FILE_NAME

    # path-safety
    config_dir.mkdir(parents=True, exist_ok=True)
    ensure_within(context.base_dir, config_dir)
    ensure_within(context.base_dir, config_path)

    # Backup eventuale file esistente
    if config_path.exists():
        backup_path = config_path.with_suffix(config_path.suffix + BACKUP_SUFFIX)
        shutil.copy(config_path, backup_path)
        logger.info(
            "📝 Backup config esistente",
            extra={"slug": context.slug, "file_path": str(backup_path)},
        )

    try:
        payload = yaml.safe_dump(config or {}, allow_unicode=True, sort_keys=False)
        safe_write_text(config_path, payload, encoding="utf-8", atomic=True)
    except Exception as e:
        raise ConfigError(f"Errore scrittura config {config_path}: {e}") from e

    logger.info(
        "📄 Config cliente salvato",
        extra={"slug": context.slug, "file_path": str(config_path)},
    )
    return config_path


# ----------------------------------------------------------
#  Lettura configurazione cliente
# ----------------------------------------------------------
def get_client_config(context: ClientContext) -> Dict[str, Any]:
    """Restituisce il contenuto del `config.yaml` dal contesto."""
    if context.config_path is None:
        raise PipelineError("Contesto incompleto: config_path mancante", slug=context.slug)
    if not context.config_path.exists():
        raise ConfigError(f"Config file non trovato: {context.config_path}")
    try:
        from pipeline.path_utils import ensure_within_and_resolve
        from pipeline.yaml_utils import yaml_read

        # Path-safety anche in LETTURA
        safe_cfg_path = ensure_within_and_resolve(context.config_path.parent, context.config_path)
        return yaml_read(safe_cfg_path.parent, safe_cfg_path) or {}
    except Exception as e:
        raise ConfigError(f"Errore lettura config {context.config_path}: {e}") from e


# ----------------------------------------------------------
#  Validazione pre-onboarding (coerenza minima ambiente)
# ----------------------------------------------------------
def validate_preonboarding_environment(
    context: ClientContext, base_dir: Optional[Path] = None
) -> None:
    """Verifica la coerenza minima dell'ambiente prima del pre-onboarding."""
    base_dir = base_dir or context.base_dir
    if base_dir is None or context.config_path is None:
        raise PipelineError(
            "Contesto incompleto: base_dir/config_path mancanti",
            slug=context.slug,
        )

    if not context.config_path.exists():
        logger.error(f"❗ Config cliente non trovato: {context.config_path}")
        raise PreOnboardingValidationError(f"Config cliente non trovato: {context.config_path}")

    try:
        from pipeline.path_utils import ensure_within_and_resolve
        from pipeline.yaml_utils import yaml_read

        # Path-safety in LETTURA
        safe_cfg_path = ensure_within_and_resolve(context.config_path.parent, context.config_path)
        cfg = yaml_read(safe_cfg_path.parent, safe_cfg_path)
    except Exception as e:
        logger.error(f"❗ Errore lettura/parsing YAML in {context.config_path}: {e}")
        raise PreOnboardingValidationError(
            f"Errore lettura config {context.config_path}: {e}"
        ) from e

    if not isinstance(cfg, dict):
        logger.error("Config YAML non valido o vuoto.")
        raise PreOnboardingValidationError("Config YAML non valido o vuoto.")

    # Chiavi obbligatorie minime
    required_keys = ["cartelle_raw_yaml"]
    missing = [k for k in required_keys if k not in cfg]
    if missing:
        logger.error(f"❗ Chiavi obbligatorie mancanti in config: {missing}")
        raise PreOnboardingValidationError(f"Chiavi obbligatorie mancanti in config: {missing}")

    # Verifica/creazione directory richieste (logs)
    logs_dir = (base_dir / "logs").resolve()
    if not logs_dir.exists():
        logger.warning(f"⚠️ Directory mancante: {logs_dir}, creazione automatica...")
        logs_dir.mkdir(parents=True, exist_ok=True)

    logger.info(f"✅ Ambiente pre-onboarding valido per cliente {context.slug}")


# ----------------------------------------------------------
#  Scrittura sicura di file generici (wrapper legacy) – ATOMICA
# ----------------------------------------------------------
def safe_write_file(file_path: Path, content: str) -> None:
    """Scrive testo in modo sicuro e atomico usando `safe_write_text`.

    - Crea le cartelle necessarie.
    - Se esiste già un file, crea backup `<nome>.bak`.
    - Usa `safe_write_text(..., atomic=True)` per la sostituzione.

    Nota: funzione mantenuta per retrocompatibilità; preferire `safe_write_text`.
    """
    file_path.parent.mkdir(parents=True, exist_ok=True)

    # Path-safety minimale (perimetro = directory padre)
    ensure_within(file_path.parent, file_path)

    # Backup se già esiste
    if file_path.exists():
        backup_path = file_path.with_suffix(file_path.suffix + BACKUP_SUFFIX)
        shutil.copy(file_path, backup_path)
        logger.info(f"Backup creato: {backup_path}")

    try:
        safe_write_text(file_path, content, encoding="utf-8", atomic=True)
    except Exception as e:
        logger.error(f"Errore scrittura file {file_path}: {e}")
        raise PipelineError(f"Errore scrittura file {file_path}: {e}") from e


# ----------------------------------------------------------
#  Merge incrementale su config.yaml con backup
# ----------------------------------------------------------
def update_config_with_drive_ids(
    context: ClientContext,
    updates: dict,
    logger: logging.Logger | None = None,
) -> None:
    """Aggiorna il file `config.yaml` del cliente con i valori forniti.

    Comportamento:
      - Esegue backup `.bak` del config esistente.
      - Aggiorna **solo** le chiavi presenti in `updates`.
      - Scrive via `safe_write_text` in modo atomico.

    Raises:
        ConfigError: se la lettura/scrittura del config fallisce o se il file è assente.
    """
    if context.config_path is None or context.base_dir is None:
        raise PipelineError(
            "Contesto incompleto: config_path/base_dir mancanti",
            slug=context.slug,
        )
    config_path = context.config_path

    if not config_path.exists():
        raise ConfigError(f"Config file non trovato: {config_path}")

    # Backup file esistente
    backup_path = config_path.with_suffix(config_path.suffix + BACKUP_SUFFIX)
    shutil.copy(config_path, backup_path)
    if logger:
        logger.info(f"💾 Backup config creato: {backup_path}")

    # Carica config esistente (path-safety in LETTURA)
    try:
        from pipeline.yaml_utils import yaml_read

        config_data = yaml_read(config_path.parent, config_path) or {}
    except Exception as e:
        raise ConfigError(f"Errore lettura config {config_path}: {e}") from e

    # Aggiorna solo le chiavi passate
    config_data.update(updates or {})

    # Scrittura sicura (atomica) + path-safety
    ensure_within(context.base_dir, config_path)
    try:
        yaml_dump = yaml.safe_dump(config_data, sort_keys=False, allow_unicode=True)
        safe_write_text(config_path, yaml_dump, encoding="utf-8", atomic=True)
        if logger:
            logger.info(f"✅ Config aggiornato in {config_path}")
    except Exception as e:
        raise ConfigError(f"Errore scrittura config {config_path}: {e}") from e


__all__ = [
    "Settings",
    "write_client_config_file",
    "get_client_config",
    "validate_preonboarding_environment",
    "safe_write_file",
    "update_config_with_drive_ids",
    "bump_n_ver_if_needed",
    "set_data_ver_today",
]


# ----------------------------------------------------------
#  Versioning helpers (N_VER / DATA_VER)
# ----------------------------------------------------------
def bump_n_ver_if_needed(context: ClientContext, logger: logging.Logger | None = None) -> None:
    """Incrementa N_VER di 1 nel config del cliente.

    Nota: la logica "if needed" è demandata al chiamante (UI tiene un flag di sessione)
    per garantire un solo incremento per sessione. Questa funzione è idempotente a
    livello di singola invocazione: legge il valore corrente (default 0) e scrive +1.
    """
    log = logger or globals().get("logger")
    cfg = get_client_config(context) or {}
    try:
        current = int(cfg.get("N_VER", 0) or 0)
    except Exception:
        current = 0
    new_val = current + 1
    if log:
        log.info(
            {
                "event": "bump_n_ver",
                "old": current,
                "new": new_val,
                "slug": context.slug,
            }
        )
    update_config_with_drive_ids(context, updates={"N_VER": new_val}, logger=log)


def set_data_ver_today(context: ClientContext, logger: logging.Logger | None = None) -> None:
    """Imposta DATA_VER alla data odierna (YYYY-MM-DD) nel config del cliente.

    Viene tipicamente chiamata alla chiusura della UI, solo se nella sessione ci sono
    state modifiche. Rimuove eventuali flag temporanei (nessun flag gestito qui).
    """
    log = logger or globals().get("logger")
    today = date.today().isoformat()
    if log:
        log.info({"event": "set_data_ver_today", "value": today, "slug": context.slug})
    update_config_with_drive_ids(context, updates={"DATA_VER": today}, logger=log)
