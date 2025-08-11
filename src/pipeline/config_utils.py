# src/pipeline/config_utils.py

import os
import shutil
import yaml
import logging
import re
from pathlib import Path
from typing import Optional, Dict, Any

from pydantic_settings import BaseSettings as PydanticBaseSettings
from pydantic import Field, model_validator

from pipeline.logging_utils import get_structured_logger
from pipeline.constants import (
    OUTPUT_DIR_NAME, LOGS_DIR_NAME, CONFIG_FILE_NAME,
    BACKUP_SUFFIX, TMP_SUFFIX,
    RAW_DIR_NAME, BOOK_DIR_NAME, CONFIG_DIR_NAME
)
from pipeline.exceptions import ConfigError, PipelineError, PreOnboardingValidationError
from pipeline.context import ClientContext

logger = get_structured_logger("pipeline.config_utils")

# ----------------------------------------------------------
#  Modello pydantic per configurazione cliente
# ----------------------------------------------------------
class Settings(PydanticBaseSettings):
    """Modello di configurazione cliente per pipeline Timmy-KB."""

    # Parametri Google Drive
    DRIVE_ID: str = Field(..., env="DRIVE_ID")
    SERVICE_ACCOUNT_FILE: str = Field(..., env="SERVICE_ACCOUNT_FILE")
    BASE_DRIVE: Optional[str] = Field(None, env="BASE_DRIVE")
    DRIVE_ROOT_ID: Optional[str] = Field(
        None,
        env="DRIVE_ROOT_ID",
        description="ID cartella radice cliente su Google Drive"
    )

    # Parametri GitHub
    GITHUB_TOKEN: str = Field(..., env="GITHUB_TOKEN")
    GITBOOK_TOKEN: Optional[str] = Field(None, env="GITBOOK_TOKEN")

    # Identificativo cliente e log
    slug: Optional[str] = None
    LOG_LEVEL: str = Field("INFO", env="LOG_LEVEL")
    DEBUG: bool = Field(False, env="DEBUG")

    @model_validator(mode="after")
    def check_critical(self):
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
    """Scrive il file config.yml nella cartella cliente, con backup."""
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
            yaml.safe_dump(config, f, allow_unicode=True)
        tmp_path.replace(config_path)
    except Exception as e:
        raise ConfigError(f"Errore scrittura config {config_path}: {e}")

    logger.info(f"📄 Config cliente salvato in {config_path}")
    return config_path

# ----------------------------------------------------------
#  Lettura configurazione cliente
# ----------------------------------------------------------
def get_client_config(context: ClientContext) -> Dict[str, Any]:
    """Restituisce il contenuto del config.yml dal contesto."""
    if not context.config_path.exists():
        raise ConfigError(f"Config file non trovato: {context.config_path}")
    try:
        with open(context.config_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception as e:
        raise ConfigError(f"Errore lettura config {context.config_path}: {e}")

# ----------------------------------------------------------
#  Validazione slug cliente
# ----------------------------------------------------------
def is_valid_slug(slug: Optional[str]) -> bool:
    """Verifica che lo slug rispetti il formato consentito."""
    if not slug:
        return False
    normalized_slug = slug.replace("_", "-").lower()
    pattern = r"^[a-z0-9]+(?:-[a-z0-9]+)*$"
    if not re.fullmatch(pattern, normalized_slug):
        logger.debug(f"Slug '{slug}' non valido. Normalizzato: '{normalized_slug}'")
        return False
    return True

# ----------------------------------------------------------
#  Validazione pre-onboarding
# ----------------------------------------------------------
def validate_preonboarding_environment(context: ClientContext, base_dir: Optional[Path] = None):
    """
    STEP 1: verifica config principale.
    STEP 2: verifica directory critiche.
    """
    base_dir = base_dir or context.base_dir

    # Verifica config file
    if not context.config_path.exists():
        logger.error(f"❗ Config cliente non trovato: {context.config_path}")
        raise PreOnboardingValidationError(f"Config cliente non trovato: {context.config_path}")

    try:
        cfg = yaml.safe_load(open(context.config_path, "r", encoding="utf-8"))
    except Exception as e:
        logger.error(f"❗ Errore lettura/parsing YAML in {context.config_path}: {e}")
        raise PreOnboardingValidationError(f"Errore lettura config {context.config_path}: {e}")

    # Chiavi obbligatorie
    required_keys = ["cartelle_raw_yaml"]
    missing = [k for k in required_keys if k not in cfg]
    if missing:
        logger.error(f"❗ Chiavi obbligatorie mancanti in config: {missing}")
        raise PreOnboardingValidationError(f"Chiavi obbligatorie mancanti in config: {missing}")

    # Verifica cartelle richieste
    required_dirs = ["logs"]
    for dir_name in required_dirs:
        dir_path = Path(dir_name).resolve()
        if not dir_path.exists():
            logger.warning(f"⚠️ Directory mancante: {dir_path}, creazione automatica...")
            dir_path.mkdir(parents=True, exist_ok=True)

    logger.info(f"✅ Ambiente pre-onboarding valido per cliente {context.slug}")

# ----------------------------------------------------------
#  Scrittura sicura di file generici (STANDARD v1.0 stable)
# ----------------------------------------------------------
def safe_write_file(file_path: Path, content: str):
    """
    Scrive un file in modalità sicura con backup.

    - Crea cartelle necessarie.
    - Crea backup se esiste un file precedente.
    - Sovrascrive in UTF-8.
    - Log automatico di operazioni ed errori.
    """
    if file_path.exists():
        backup_path = file_path.with_suffix(file_path.suffix + BACKUP_SUFFIX)
        shutil.copy(file_path, backup_path)
        logger.info(f"Backup creato: {backup_path}")

    try:
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)
    except Exception as e:
        logger.error(f"Errore scrittura file {file_path}: {e}")
        raise PipelineError(f"Errore scrittura file {file_path}: {e}")

def update_config_with_drive_ids(context: ClientContext, updates: dict, logger=None):
    """
    Aggiorna il file config.yml del cliente con i valori forniti in 'updates'.
    - Esegue backup .bak del config esistente.
    - Aggiorna solo le chiavi presenti in 'updates'.
    - Usa scrittura sicura tramite safe_write_file.

    Args:
        context (ClientContext): Contesto del cliente.
        updates (dict): Chiavi/valori da aggiornare nel config.
        logger: Logger strutturato opzionale.
    """
    config_path = context.config_path

    if not config_path.exists():
        raise ConfigError(f"Config file non trovato: {config_path}")

    # 📦 Backup file esistente
    backup_path = config_path.with_suffix(config_path.suffix + BACKUP_SUFFIX)
    shutil.copy(config_path, backup_path)
    if logger:
        logger.info(f"💾 Backup config creato: {backup_path}")

    # 📥 Carica config esistente
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config_data = yaml.safe_load(f) or {}
    except Exception as e:
        raise ConfigError(f"Errore lettura config {config_path}: {e}")

    # 🔄 Aggiorna solo le chiavi passate
    config_data.update(updates)

    # ✍️ Scrittura sicura
    try:
        safe_write_file(config_path, yaml.safe_dump(config_data, sort_keys=False, allow_unicode=True))
        if logger:
            logger.info(f"✅ Config aggiornato in {config_path}")
    except Exception as e:
        raise ConfigError(f"Errore scrittura config {config_path}: {e}")
