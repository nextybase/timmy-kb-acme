"""
Modulo di gestione unificata della configurazione Timmy-KB (YAML + .env).
- Compatibile con la pipeline attuale (nessuna funzione pubblica cambia nome)
- Priorità: .env > YAML > default
"""

import yaml
import os
from pathlib import Path
from functools import lru_cache
from typing import Optional, Dict, Any

from pydantic import BaseModel, validator, Field
from pydantic_settings import BaseSettings
from pipeline.logging_utils import get_structured_logger

logger = get_structured_logger("pipeline.config_utils")

REPO_ROOT = Path(__file__).resolve().parents[2]  # Adatta se serve!

# ======= Modelli di configurazione =======

class TimmyConfig(BaseModel):
    slug: str
    raw_dir: str
    md_output_path: str
    default_language: Optional[str] = "it"
    # Qui puoi aggiungere altri parametri strutturali dal config YAML

    @validator("raw_dir", "md_output_path")
    def validate_paths(cls, v):
        if not v or not isinstance(v, str):
            raise ValueError("Il path deve essere una stringa valida.")
        return v

class TimmySecrets(BaseSettings):
    # === Google Drive ===
    DRIVE_ID: Optional[str] = Field(default=None)
    SERVICE_ACCOUNT_FILE: Optional[str] = Field(default=None)
    # === GitHub ===
    GITHUB_TOKEN: Optional[str] = Field(default=None)
    REPO_CLONE_BASE: Optional[str] = Field(default=None)
    # === GitBook ===
    GITBOOK_TOKEN: Optional[str] = Field(default=None)
    GITBOOK_WORKSPACE: str = "default-workspace"
    # === Path locali
    BASE_DRIVE: Optional[str] = Field(default=None)
    # === Logging
    LOG_PATH: str = "logs/onboarding.log"
    LOG_LEVEL: str = "INFO"

    class Config:
        env_file = ".env"
        case_sensitive = True

class UnifiedConfig(BaseModel):
    # Mantiene la compatibilità col modello attuale
    config: TimmyConfig
    secrets: TimmySecrets

    # Facoltativo: API di shortcut per accedere ai parametri comuni
    @property
    def drive_id(self):
        return self.secrets.DRIVE_ID

    @property
    def service_account_file(self):
        return self.secrets.SERVICE_ACCOUNT_FILE

    @property
    def raw_dir(self):
        return self.config.raw_dir

    @property
    def md_output_path(self):
        return self.config.md_output_path

    @property
    def base_drive(self):
        return self.secrets.BASE_DRIVE

    # Aggiungi qui altre proprietà-ponte se vuoi accesso "piatto"

# ======= Loader unificato =======

@lru_cache()
def get_config(slug: str) -> UnifiedConfig:
    """
    Carica config.yaml (parametri strutturali) e .env (segreti/runtime),
    applica override automatico (priorità: .env > yaml > default).
    """
    # 1. Carica YAML config
    config_path = REPO_ROOT / "output" / f"timmy-kb-{slug}" / "config" / "config.yaml"
    if not config_path.exists():
        logger.error(f"❌ Config file non trovato: {config_path}")
        raise FileNotFoundError(f"Config file non trovato: {config_path}")

    with open(config_path, "r", encoding="utf-8") as f:
        raw_config: Dict[str, Any] = yaml.safe_load(f)

    # Slug sempre presente
    raw_config["slug"] = slug

    # 2. Carica ENV (usa Pydantic Settings)
    secrets = TimmySecrets()

    # 3. Override: .env > yaml
    # Costruisce TimmyConfig usando tutti i valori da yaml, ma per i campi che sono anche in secrets, usa quelli di secrets se valorizzati
    override_config = {**raw_config}
    for key in raw_config:
        env_val = getattr(secrets, key, None)
        if env_val not in (None, "", [], {}):
            # Logging override
            logger.warning(f"⚠️ Override config '{key}' da .env: '{raw_config[key]}' -> '{env_val}'")
            override_config[key] = env_val

    config = TimmyConfig(**override_config)

    return UnifiedConfig(config=config, secrets=secrets)

# ======= Funzioni legacy, ancora compatibili =======

def load_client_config(slug: str) -> dict:
    """
    [DEPRECATO in favore di get_config()] – Carica configurazione YAML come dict semplice.
    """
    config_path = REPO_ROOT / "output" / f"timmy-kb-{slug}" / "config" / "config.yaml"
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
    config_dir = REPO_ROOT / "output" / f"timmy-kb-{slug}" / "config"
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

