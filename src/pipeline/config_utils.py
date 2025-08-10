from dotenv import load_dotenv
load_dotenv()

from pathlib import Path
from typing import Optional, Dict, Any
import os
import shutil
import yaml
import logging
import re

from pydantic_settings import BaseSettings as PydanticBaseSettings
from pydantic import Field, model_validator
from pipeline.constants import (
    OUTPUT_DIR_NAME, LOGS_DIR_NAME, CONFIG_FILE_NAME,
    BACKUP_SUFFIX, TMP_SUFFIX,
    RAW_DIR_NAME, BOOK_DIR_NAME, CONFIG_DIR_NAME
)
from pipeline.exceptions import ConfigError, PipelineError, PreOnboardingValidationError

# Cache interna per Settings
_settings_cache: Dict[str, "Settings"] = {}


class Settings(PydanticBaseSettings):
    """Modello di configurazione centrale per la pipeline Timmy-KB."""

    # Parametri Google Drive
    DRIVE_ID: str = Field(..., env="DRIVE_ID")
    SERVICE_ACCOUNT_FILE: str = Field(..., env="SERVICE_ACCOUNT_FILE")
    BASE_DRIVE: Optional[str] = Field(None, env="BASE_DRIVE")
    DRIVE_ROOT_ID: Optional[str] = Field(
        None,
        env="DRIVE_ROOT_ID",
        description="ID cartella radice cliente su Google Drive"
    )

    # Parametri GitHub / GitBook
    GITHUB_TOKEN: str = Field(..., env="GITHUB_TOKEN")
    GITBOOK_TOKEN: Optional[str] = Field(None, env="GITBOOK_TOKEN")

    # Identificativo cliente e log
    slug: Optional[str] = None  # 🔹 nuovo campo per compatibilità multi-client
    LOG_LEVEL: str = Field("INFO", env="LOG_LEVEL")
    DEBUG: bool = Field(False, env="DEBUG")

    @model_validator(mode="after")
    def check_critico(self, data):
        from pipeline.logging_utils import get_structured_logger
        logger = get_structured_logger("pipeline.config_utils")

        critico = ["DRIVE_ID", "SERVICE_ACCOUNT_FILE", "GITHUB_TOKEN"]
        for key in critico:
            if not getattr(self, key, None):
                logger.error(f"Parametro critico '{key}' mancante!")
                raise ValueError(f"Parametro critico '{key}' mancante!")

        if not self.slug:
            logger.error("Parametro 'slug' mancante! Usare get_settings_for_slug(slug).")
            raise ValueError("Parametro 'slug' mancante!")

        if not self.DRIVE_ROOT_ID:
            logger.warning("Parametro 'DRIVE_ROOT_ID' mancante: alcune funzioni Drive potrebbero non funzionare.")

        return self

    # --- Proprietà di path ---
    @property
    def base_dir(self) -> Path:
        return Path(os.getenv("BASE_DIR", Path.cwd()))

    @property
    def output_dir(self) -> Path:
        return self.base_dir / OUTPUT_DIR_NAME / self.slug

    @property
    def config_dir(self) -> Path:
        return self.output_dir / CONFIG_DIR_NAME

    @property
    def raw_dir(self) -> Path:
        return self.output_dir / RAW_DIR_NAME

    @property
    def md_output_path(self) -> Path:
        return self.output_dir / BOOK_DIR_NAME

    @property
    def book_dir(self) -> Path:
        return self.md_output_path

    @property
    def output_dir_path(self) -> Path:
        return self.output_dir

    @property
    def logs_path(self) -> Path:
        return self.base_dir / LOGS_DIR_NAME / f"timmy-kb-{self.slug}.log"

    @property
    def drive_folder_id(self) -> Optional[str]:
        from pipeline.logging_utils import get_structured_logger
        logger = get_structured_logger("pipeline.config_utils")

        config_path = self.config_dir / CONFIG_FILE_NAME
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


# --- Funzioni di gestione config ---
def write_client_config_file(config: Dict[str, Any], slug: str) -> Path:
    from pipeline.logging_utils import get_structured_logger
    logger = get_structured_logger("pipeline.config_utils")

    config_dir = Path(OUTPUT_DIR_NAME) / f"timmy-kb-{slug}" / CONFIG_DIR_NAME
    _validate_path_in_base_dir(config_dir, config_dir.parent)
    config_dir.mkdir(parents=True, exist_ok=True)

    config_path = config_dir / CONFIG_FILE_NAME
    if config_path.exists():
        shutil.copy(config_path, config_path.with_suffix(BACKUP_SUFFIX))
        logger.info(f"Backup configurazione cliente in {config_path.with_suffix(BACKUP_SUFFIX)}")

    tmp_path = config_path.with_suffix(TMP_SUFFIX)
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(config, f, allow_unicode=True)
        tmp_path.replace(config_path)
    except Exception as e:
        raise ConfigError(f"Errore scrittura config {config_path}: {e}")

    logger.info(f"Config file cliente scritto in {config_path}")
    return config_path


def get_client_config(slug: str) -> Dict[str, Any]:
    config_path = Path(OUTPUT_DIR_NAME) / f"timmy-kb-{slug}" / CONFIG_DIR_NAME / CONFIG_FILE_NAME
    _validate_path_in_base_dir(config_path, config_path.parent)
    if not config_path.exists():
        raise ConfigError(f"Config file non trovato: {config_path}")
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception as e:
        raise ConfigError(f"Errore lettura config {config_path}: {e}")


# --- Gestione Settings con cache ---
def get_settings_for_slug(slug: str, base_dir: Optional[Path] = None, force_reload: bool = False) -> Settings:
    if not force_reload and slug in _settings_cache:
        return _settings_cache[slug]
    if base_dir:
        os.environ["BASE_DIR"] = str(base_dir)
    settings_obj = Settings(slug=slug)
    _settings_cache[slug] = settings_obj
    return settings_obj


# --- Validazioni ---
def is_valid_slug(slug: Optional[str] = None) -> bool:
    """
    Verifica che lo slug rispetti il formato consentito.
    """
    if not slug:
        return False
    normalized_slug = slug.replace("_", "-").lower()
    # Regex restrittiva: lettere, numeri, trattini, no doppio trattino, no trattini iniziali/finali
    pattern = r"^[a-z0-9]+(?:-[a-z0-9]+)*$"
    if not re.fullmatch(pattern, normalized_slug):
        logging.getLogger("slug.validation").debug(
            f"Slug '{slug}' non valido. Normalizzato: '{normalized_slug}', pattern: {pattern}"
        )
        return False
    return True


def _validate_path_in_base_dir(path: Path, base_dir: Path) -> None:
    """
    Verifica che il path sia figlio di base_dir.
    """
    resolved_path = path.resolve()
    if not str(resolved_path).startswith(str(base_dir.resolve())):
        raise PipelineError(f"Percorso non consentito: {resolved_path} fuori da {base_dir}")


def validate_preonboarding_environment(base_dir: Optional[Path] = None, logger: Optional[logging.Logger] = None) -> None:
    """
    STEP 1: Verifica config principale.
    STEP 2: Verifica directory critiche.
    """
    if logger is None:
        logger = logging.getLogger("preonboarding.validation")

    if base_dir is None:
        base_dir = getattr(settings, "base_dir", Path("."))

    # STEP 1 – Validazione config principale
    config_path = Path("config") / CONFIG_FILE_NAME
    config_path = config_path.resolve()

    if not config_path.exists():
        logger.error(f"❌ File di configurazione non trovato: {config_path}")
        raise PreOnboardingValidationError(f"File di configurazione non trovato: {config_path}")

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
    except Exception as e:
        logger.error(f"❌ Errore di lettura/parsing YAML in {config_path}: {e}")
        raise PreOnboardingValidationError(f"Errore di lettura/parsing YAML in {config_path}: {e}")

    required_base_keys = ["cartelle_raw_yaml"]
    missing_keys = [k for k in required_base_keys if k not in config]
    if missing_keys:
        logger.error(f"❌ Chiavi obbligatorie mancanti in {config_path}: {missing_keys}")
        raise PreOnboardingValidationError(f"Chiavi obbligatorie mancanti: {missing_keys}")

    logger.info(f"✅ Config {config_path} esistente e leggibile.")

    # STEP 2 – Verifica e creazione directory critiche
    required_dirs = ["logs"]
    for dir_name in required_dirs:
        dir_path = Path(dir_name).resolve()
        try:
            _validate_path_in_base_dir(dir_path, base_dir)
        except PipelineError as e:
            logger.error(f"❌ Directory fuori scope: {dir_path}")
            raise PreOnboardingValidationError(str(e))
        if not dir_path.exists():
            logger.warning(f"⚠️ Directory mancante: {dir_path}, creazione automatica...")
            dir_path.mkdir(parents=True, exist_ok=True)

    logger.info("✅ Tutti i file e le directory richieste sono presenti o create.")

def _safe_write_file(file_path: Path, content: str):
    """
    Scrive un file in modo sicuro:
    - Backup del file esistente
    - Sovrascrittura con nuovo contenuto
    """
    _validate_path_in_base_dir(file_path, file_path.parent)

    if file_path.exists():
        backup_path = file_path.with_suffix(BACKUP_SUFFIX)
        shutil.copy(file_path, backup_path)
        logger.info(f"💾 Backup creato: {backup_path}")

    try:
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)
        logger.debug(f"✏️ File scritto: {file_path}")
    except Exception as e:
        logger.error(f"❌ Errore scrittura file {file_path}: {e}")
        raise PipelineError(f"Errore scrittura file {file_path}: {e}")

