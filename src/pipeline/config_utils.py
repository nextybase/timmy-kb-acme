"""
Configurazione centralizzata della pipeline Timmy-KB.
Integra caricamento da .env, config.yaml cliente e validazione minima.

Modifiche Fase 1:
- Uso di costanti centralizzate da constants.py
- Parametrizzazione BASE_DIR
- Caching Settings
- Scrittura atomica config
"""

from dotenv import load_dotenv
load_dotenv()

from pathlib import Path
from typing import Optional, Dict
import os
import shutil
import yaml
from pydantic_settings import BaseSettings
from pydantic import Field, model_validator, constr
from pipeline.logging_utils import get_structured_logger
from pipeline.constants import (
    OUTPUT_DIR_NAME, LOGS_DIR_NAME, CONFIG_FILE_NAME,
    BACKUP_SUFFIX, TMP_SUFFIX
)
from pipeline.exceptions import ConfigError

logger = get_structured_logger("pipeline.config_utils")

# Cache interna per Settings
_settings_cache: Dict[str, "Settings"] = {}

class Settings(BaseSettings):
    """
    Modello di configurazione centrale per la pipeline Timmy-KB.
    Caricata da env, .env, config cliente.
    """

    # Parametri Google Drive
    DRIVE_ID: str = Field(..., env="DRIVE_ID")
    SERVICE_ACCOUNT_FILE: str = Field(..., env="SERVICE_ACCOUNT_FILE")
    BASE_DRIVE: Optional[str] = Field(None, env="BASE_DRIVE")

    # Parametri GitHub
    GITHUB_TOKEN: str = Field(..., env="GITHUB_TOKEN")
    GITBOOK_TOKEN: Optional[str] = Field(None, env="GITBOOK_TOKEN")

    # Identificativo progetto
    SLUG: Optional[str] = Field(None, env="SLUG", description="Identificativo progetto (obbligatorio in get_settings_for_slug)")
    LOG_LEVEL: str = Field("INFO", env="LOG_LEVEL")
    DEBUG: bool = Field(False, env="DEBUG")

    @model_validator(mode="after")
    def check_critico(self, data):
        """Controlla parametri fondamentali per la pipeline."""
        critici = ["DRIVE_ID", "SERVICE_ACCOUNT_FILE", "GITHUB_TOKEN"]
        for key in critici:
            if not getattr(self, key, None):
                logger.error(f"Parametro critico '{key}' mancante!")
                raise ValueError(f"Parametro critico '{key}' mancante!")
        if not self.SLUG:
            logger.error("Parametro 'SLUG' mancante! Usare get_settings_for_slug(slug).")
            raise ValueError("Parametro 'SLUG' mancante!")
        return self

    # --- Proprietà di path ---

    @property
    def base_dir(self) -> Path:
        """Directory base della pipeline (default: cwd)."""
        return Path(os.getenv("BASE_DIR", Path.cwd()))

    @property
    def output_dir(self) -> Path:
        return self.base_dir / OUTPUT_DIR_NAME / self.SLUG

    @property
    def raw_dir(self) -> Path:
        return self.output_dir / "raw"

    @property
    def md_output_path(self) -> Path:
        return self.output_dir / "book"

    @property
    def book_dir(self) -> Path:
        return self.md_output_path

    @property
    def output_dir_path(self) -> Path:
        return self.output_dir

    @property
    def logs_path(self) -> Path:
        return self.base_dir / LOGS_DIR_NAME / f"timmy-kb-{self.SLUG}.log"

    @property
    def drive_folder_id(self) -> Optional[str]:
        """Recupera drive_folder_id dal config cliente, se presente."""
        config_path = self.output_dir / "config" / CONFIG_FILE_NAME
        if config_path.exists():
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    conf = yaml.safe_load(f) or {}
                    folder_id = conf.get("drive_folder_id")
                    if not folder_id:
                        logger.warning(f"drive_folder_id mancante in {config_path}.")
                    return folder_id
            except Exception as e:
                logger.error(f"Errore lettura drive_folder_id da {config_path}: {e}", exc_info=True)
                return None
        else:
            logger.warning(f"File config cliente non trovato per drive_folder_id: {config_path}")
        return None

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True


# --- Funzioni di gestione config cliente ---

def write_client_config_file(config: dict, slug: str) -> Path:
    """
    Scrive la configurazione cliente in modo sicuro:
    - Crea cartella /output/<slug>/config se non esiste
    - Crea backup .bak
    - Scrive in modo atomico tramite .tmp
    """
    config_dir = Path(OUTPUT_DIR_NAME) / f"timmy-kb-{slug}" / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    config_path = config_dir / CONFIG_FILE_NAME

    # Backup esistente
    if config_path.exists():
        shutil.copy(config_path, config_path.with_suffix(BACKUP_SUFFIX))
        logger.info(f"Backup configurazione cliente in {config_path.with_suffix(BACKUP_SUFFIX)}")

    # Scrittura atomica
    tmp_path = config_path.with_suffix(TMP_SUFFIX)
    with open(tmp_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(config, f, allow_unicode=True)
    tmp_path.replace(config_path)

    logger.info(f"Config file cliente scritto in {config_path}")
    return config_path


def get_client_config(slug: str) -> dict:
    """Legge config cliente YAML per uno slug."""
    config_path = Path(OUTPUT_DIR_NAME) / f"timmy-kb-{slug}" / "config" / CONFIG_FILE_NAME
    if not config_path.exists():
        raise FileNotFoundError(f"Config file non trovato: {config_path}")
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


# --- Gestione Settings con caching ---

def get_settings_for_slug(slug: str, base_dir: Optional[Path] = None, force_reload: bool = False) -> Settings:
    """
    Crea o recupera un'istanza Settings per uno slug.
    Usa cache interna, salvo force_reload=True.
    """
    if not force_reload and slug in _settings_cache:
        return _settings_cache[slug]

    if base_dir:
        os.environ["BASE_DIR"] = str(base_dir)

    settings = Settings(SLUG=slug)
    _settings_cache[slug] = settings
    return settings


# Patch compatibilità per import legacy
try:
    settings = Settings()
except Exception as e:
    logger.warning(f"[Compat] Impossibile istanziare settings al volo: {e}. "
                   f"Usare get_settings_for_slug(slug) per ottenere un'istanza valida.")
    settings = None
