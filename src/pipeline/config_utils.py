"""
Modulo di gestione centralizzata della configurazione Timmy (YAML + .env).

- TimmyConfig: parametri strutturali del cliente (es. raw_dir, md_output_path)
- TimmySecrets: parametri runtime/sensibili (.env)
- get_config(): loader unificato con override e validazione
"""

import yaml
from pathlib import Path
from functools import lru_cache
from typing import Optional, Dict

from pydantic import BaseModel, validator
from pydantic_settings import BaseSettings
from pipeline.logging_utils import get_structured_logger

logger = get_structured_logger("pipeline.config_utils")


class TimmyConfig(BaseModel):
    slug: str
    raw_dir: str
    md_output_path: str
    default_language: Optional[str] = "it"

    @validator("raw_dir", "md_output_path")
    def validate_paths(cls, v):
        if not v or not isinstance(v, str):
            raise ValueError("Il path deve essere una stringa valida.")
        return v


class TimmySecrets(BaseSettings):
    # === Google Drive ===
    DRIVE_ID: str
    SERVICE_ACCOUNT_FILE: str

    # === GitHub ===
    GITHUB_TOKEN: str
    REPO_CLONE_BASE: str

    # === GitBook ===
    GITBOOK_TOKEN: str
    GITBOOK_WORKSPACE: str = "default-workspace"

    # === Path locali
    BASE_DRIVE: str

    # === Logging
    LOG_PATH: str = "logs/onboarding.log"
    LOG_LEVEL: str = "INFO"

    class Config:
        env_file = ".env"
        case_sensitive = True


class UnifiedConfig(BaseModel):
    config: TimmyConfig
    secrets: TimmySecrets


@lru_cache()
def get_config(slug: str) -> UnifiedConfig:
    """
    Carica e valida config.yaml e .env per un dato slug cliente.
    Applica override dei valori comuni usando .env come sorgente prioritaria.
    """
    config_path = Path("output") / f"timmy-kb-{slug}" / "config" / "config.yaml"
    if not config_path.exists():
        logger.error(f"❌ Config file non trovato: {config_path}")
        raise FileNotFoundError(f"Config file non trovato: {config_path}")

    with open(config_path, "r", encoding="utf-8") as f:
        raw_config: Dict = yaml.safe_load(f)

    raw_config["slug"] = slug
    config = TimmyConfig(**raw_config)
    secrets = TimmySecrets()

    # Log override eventuali
    override_keys = set(raw_config.keys()) & secrets.dict().keys()
    for key in override_keys:
        logger.warning(f"⚠️ Override config '{key}' da .env: '{raw_config[key]}' -> '{getattr(secrets, key)}'")

    return UnifiedConfig(config=config, secrets=secrets)


def load_client_config(slug: str) -> dict:
    """
    [DEPRECATO in favore di get_config()] – Carica configurazione YAML come dict semplice.
    """
    config_path = Path("output") / f"timmy-kb-{slug}" / "config" / "config.yaml"
    if not config_path.exists():
        logger.error(f"❌ Config file non trovato: {config_path}")
        raise FileNotFoundError(f"Config file non trovato: {config_path}")
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    config["slug"] = slug
    return config


def write_client_config_file(config: dict, slug: str) -> Path:
    """
    Scrive il file di configurazione arricchito del cliente nella posizione standard.
    Ritorna il path assoluto del file creato.
    """
    config_dir = Path("output") / f"timmy-kb-{slug}" / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    config_path = config_dir / "config.yaml"
    try:
        with open(config_path, "w", encoding="utf-8") as f:
            yaml.dump(config, f, allow_unicode=True)
        logger.info(f"✅ Config YAML scritto in: {config_path}")
    except Exception as e:
        logger.error(f"❌ Errore scrivendo config YAML in {config_path}: {e}")
        raise
    return config_path
