# src/pipeline/config_utils.py

from __future__ import annotations

import os
import shutil
import yaml
import logging
from pathlib import Path
from typing import Optional, Dict, Any

from pydantic_settings import BaseSettings as PydanticBaseSettings
from pydantic import Field, model_validator

from pipeline.logging_utils import get_structured_logger
from pipeline.constants import (
    OUTPUT_DIR_NAME, LOGS_DIR_NAME, CONFIG_FILE_NAME,
    BACKUP_SUFFIX, TMP_SUFFIX,
    RAW_DIR_NAME, BOOK_DIR_NAME, CONFIG_DIR_NAME,
)
from pipeline.exceptions import ConfigError, PipelineError, PreOnboardingValidationError
from pipeline.context import ClientContext

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
    DRIVE_ID: str = Field(..., env="DRIVE_ID")
    SERVICE_ACCOUNT_FILE: str = Field(..., env="SERVICE_ACCOUNT_FILE")
    BASE_DRIVE: Optional[str] = Field(None, env="BASE_DRIVE")
    DRIVE_ROOT_ID: Optional[str] = Field(
        None,
        env="DRIVE_ROOT_ID",
        description="ID cartella radice cliente su Google Drive",
    )

    # Parametri GitHub/GitBook
    GITHUB_TOKEN: str = Field(..., env="GITHUB_TOKEN")
    GITBOOK_TOKEN: Optional[str] = Field(None, env="GITBOOK_TOKEN")

    # Identificativo cliente e log
    slug: Optional[str] = None
    LOG_LEVEL: str = Field("INFO", env="LOG_LEVEL")
    DEBUG: bool = Field(False, env="DEBUG")

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
    """Scrive il file `config.yaml` nella cartella cliente, con backup e scrittura atomica.

    Strategia:
      - Crea la cartella `config/` se assente.
      - Se esiste già un config, ne crea un backup con suffisso `.bak`.
      - Scrive su file temporaneo `.tmp` e poi fa `replace()` atomico sul file finale.

    Args:
        context: Contesto del cliente (fornisce `output_dir` e percorsi canonici).
        config: Dizionario di configurazione da serializzare in YAML.

    Returns:
        Il percorso completo del file `config.yaml` scritto.

    Raises:
        ConfigError: in caso di errore di scrittura su disco.
    """
    config_dir = context.output_dir / CONFIG_DIR_NAME
    config_dir.mkdir(parents=True, exist_ok=True)
    config_path = config_dir / CONFIG_FILE_NAME

    # Backup eventuale file esistente
    if config_path.exists():
        backup_path = config_path.with_suffix(config_path.suffix + BACKUP_SUFFIX)
        shutil.copy(config_path, backup_path)
        logger.info(f"📝 Backup config esistente in {backup_path}")

    tmp_path = config_path.with_suffix(config_path.suffix + TMP_SUFFIX)
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(config, f, allow_unicode=True, sort_keys=False)
        tmp_path.replace(config_path)
    except Exception as e:
        raise ConfigError(f"Errore scrittura config {config_path}: {e}")

    logger.info(f"📄 Config cliente salvato in {config_path}")
    return config_path


# ----------------------------------------------------------
#  Lettura configurazione cliente
# ----------------------------------------------------------
def get_client_config(context: ClientContext) -> Dict[str, Any]:
    """Restituisce il contenuto del `config.yaml` dal contesto.

    Args:
        context: Contesto del cliente, con `config_path` valorizzato.

    Returns:
        Il contenuto del config come `dict` (o `{}` se il file è vuoto).

    Raises:
        ConfigError: se il file non esiste o in caso di errore di lettura/parsing.
    """
    if not context.config_path.exists():
        raise ConfigError(f"Config file non trovato: {context.config_path}")
    try:
        with open(context.config_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception as e:
        raise ConfigError(f"Errore lettura config {context.config_path}: {e}")


# ----------------------------------------------------------
#  Validazione pre-onboarding (coerenza minima ambiente)
# ----------------------------------------------------------
def validate_preonboarding_environment(context: ClientContext, base_dir: Optional[Path] = None) -> None:
    """Verifica la coerenza minima dell'ambiente prima del pre-onboarding.

    STEP 1: verifica la presenza e la validità della config principale (`config.yaml`).
    STEP 2: verifica (e crea se mancante) le directory critiche (es. `logs/`).

    Args:
        context: Contesto cliente.
        base_dir: Radice delle directory del cliente. Se `None`, usa `context.base_dir`.

    Raises:
        PreOnboardingValidationError: per config mancante/non valida o YAML malformato.
    """
    base_dir = base_dir or context.base_dir

    # Verifica config file
    if not context.config_path.exists():
        logger.error(f"❗ Config cliente non trovato: {context.config_path}")
        raise PreOnboardingValidationError(f"Config cliente non trovato: {context.config_path}")

    try:
        with open(context.config_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
    except Exception as e:
        logger.error(f"❗ Errore lettura/parsing YAML in {context.config_path}: {e}")
        raise PreOnboardingValidationError(f"Errore lettura config {context.config_path}: {e}")

    if not isinstance(cfg, dict):
        logger.error("❗ Config YAML non valido o vuoto.")
        raise PreOnboardingValidationError("Config YAML non valido o vuoto.")

    # Chiavi obbligatorie minime
    required_keys = ["cartelle_raw_yaml"]
    missing = [k for k in required_keys if k not in cfg]
    if missing:
        logger.error(f"❗ Chiavi obbligatorie mancanti in config: {missing}")
        raise PreOnboardingValidationError(f"Chiavi obbligatorie mancanti in config: {missing}")

    # Verifica/creazione directory richieste (logs)
    required_dirs = ["logs"]
    for dir_name in required_dirs:
        dir_path = (base_dir / dir_name) if not Path(dir_name).is_absolute() else Path(dir_name)
        dir_path = dir_path.resolve()
        if not dir_path.exists():
            logger.warning(f"⚠️ Directory mancante: {dir_path}, creazione automatica...")
            dir_path.mkdir(parents=True, exist_ok=True)

    logger.info(f"✅ Ambiente pre-onboarding valido per cliente {context.slug}")


# ----------------------------------------------------------
#  Scrittura sicura di file generici (STANDARD v1.0 stable) – ATOMICA
# ----------------------------------------------------------
def safe_write_file(file_path: Path, content: str) -> None:
    """Scrive un file in modalità sicura con backup e replace atomico.

    Procedura:
      - Crea le cartelle necessarie.
      - Se esiste già un file, crea un backup con suffisso `.bak`.
      - Scrive su file temporaneo `.tmp`; poi `replace()` atomico sul target.

    Args:
        file_path: Percorso del file di destinazione.
        content: Contenuto da scrivere (testo UTF-8).

    Raises:
        PipelineError: se la scrittura fallisce.
    """
    file_path.parent.mkdir(parents=True, exist_ok=True)

    # Backup se già esiste
    if file_path.exists():
        backup_path = file_path.with_suffix(file_path.suffix + BACKUP_SUFFIX)
        shutil.copy(file_path, backup_path)
        logger.info(f"Backup creato: {backup_path}")

    # Scrittura atomica: tmp + replace
    tmp_path = file_path.with_suffix(file_path.suffix + TMP_SUFFIX)
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(content)
        tmp_path.replace(file_path)
    except Exception as e:
        logger.error(f"Errore scrittura file {file_path}: {e}")
        raise PipelineError(f"Errore scrittura file {file_path}: {e}")


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
      - Schre via `safe_write_file` in modo atomico.

    Args:
        context: Contesto cliente con `config_path` valido.
        updates: Mappa chiave→valore da fondere nel config.
        logger: Logger opzionale per messaggi di esito.

    Raises:
        ConfigError: se la lettura/scrittura del config fallisce o se il file è assente.
    """
    config_path = context.config_path

    if not config_path.exists():
        raise ConfigError(f"Config file non trovato: {config_path}")

    # Backup file esistente
    backup_path = config_path.with_suffix(config_path.suffix + BACKUP_SUFFIX)
    shutil.copy(config_path, backup_path)
    if logger:
        logger.info(f"💾 Backup config creato: {backup_path}")

    # Carica config esistente
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config_data = yaml.safe_load(f) or {}
    except Exception as e:
        raise ConfigError(f"Errore lettura config {config_path}: {e}")

    # Aggiorna solo le chiavi passate
    config_data.update(updates)

    # Scrittura sicura (atomica)
    try:
        yaml_dump = yaml.safe_dump(config_data, sort_keys=False, allow_unicode=True)
        safe_write_file(config_path, yaml_dump)
        if logger:
            logger.info(f"✅ Config aggiornato in {config_path}")
    except Exception as e:
        raise ConfigError(f"Errore scrittura config {config_path}: {e}")


__all__ = [
    "Settings",
    "write_client_config_file",
    "get_client_config",
    "validate_preonboarding_environment",
    "safe_write_file",
    "update_config_with_drive_ids",
]
