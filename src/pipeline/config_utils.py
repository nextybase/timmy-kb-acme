"""
src/pipeline/config_utils.py

Configurazione centralizzata pipeline Timmy-KB.
Tutti i nomi 1:1 con .env e config.yaml, con proprietà dinamiche per path e compatibilità moduli.
"""

from dotenv import load_dotenv
load_dotenv()

from pathlib import Path
from typing import Optional
import yaml
from pydantic_settings import BaseSettings
from pydantic import Field, model_validator
from pipeline.logging_utils import get_structured_logger

logger = get_structured_logger("pipeline.config_utils")


class Settings(BaseSettings):
    """
    Modello di configurazione centralizzato per la pipeline Timmy-KB.

    - Cerca parametri in env > .env > default.
    - Lo slug DEVE essere sempre settato tramite factory get_settings_for_slug().
    """

    # === GOOGLE DRIVE ===
    DRIVE_ID: str = Field(..., env="DRIVE_ID")
    SERVICE_ACCOUNT_FILE: str = Field(..., env="SERVICE_ACCOUNT_FILE")
    BASE_DRIVE: Optional[str] = Field(None, env="BASE_DRIVE")

    # === GITHUB ===
    GITHUB_TOKEN: str = Field(..., env="GITHUB_TOKEN")

    # === GITBOOK API (futuro) ===
    GITBOOK_TOKEN: Optional[str] = Field(None, env="GITBOOK_TOKEN")

    # === SLUG e altri ===
    SLUG: Optional[str] = Field(None, env="SLUG", description="Slug identificativo progetto (obbligatorio per pipeline per-client!)")
    LOG_LEVEL: str = Field("INFO", env="LOG_LEVEL")
    DEBUG: bool = Field(False, env="DEBUG")

    @model_validator(mode="after")
    def check_critici(cls, data):
        critici = ["DRIVE_ID", "SERVICE_ACCOUNT_FILE", "GITHUB_TOKEN"]
        for key in critici:
            if not getattr(data, key, None):
                logger.error(f"Parametro critico '{key}' mancante! (.env variabile MAIUSCOLA)")
                raise ValueError(f"Parametro critico '{key}' mancante!")
        if not getattr(data, "SLUG", None):
            logger.error("Parametro obbligatorio 'SLUG' mancante! Usare sempre get_settings_for_slug(slug) negli orchestratori.")
            raise ValueError("Parametro obbligatorio 'SLUG' mancante! Usare sempre get_settings_for_slug(slug) negli orchestratori.")
        return data

    @property
    def slug(self) -> str:
        if self.SLUG:
            return self.SLUG
        raise RuntimeError("SLUG mancante nei settings e nelle variabili d'ambiente.")

    @property
    def output_dir(self) -> Path:
        return Path(f"output/timmy-kb-{self.slug}")

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
        log_name = f"timmy-kb-{self.slug}.log"
        return Path("logs") / log_name

    @property
    def drive_folder_id(self) -> Optional[str]:
        """
        Restituisce il drive_folder_id dal config cliente (minuscolo, config.yaml),
        con logging diagnostico se mancante o non leggibile.
        """
        config_path = self.output_dir / "config" / "config.yaml"
        if config_path.exists():
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    conf = yaml.safe_load(f) or {}
                folder_id = conf.get("drive_folder_id")
                if not folder_id:
                    logger.warning(
                        f"drive_folder_id mancante in {config_path}. "
                        "Verificare il file di configurazione cliente."
                    )
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


if __name__ == "__main__":
    try:
        settings = Settings()
        print(f"SERVICE_ACCOUNT_FILE from settings: {settings.SERVICE_ACCOUNT_FILE}")
        print(f"SLUG: {settings.SLUG}")
    except Exception as e:
        print(f"Errore: {e}")


def write_client_config_file(config: dict, slug: str) -> Path:
    config_dir = Path(f"output/timmy-kb-{slug}") / "config"
    try:
        config_dir.mkdir(parents=True, exist_ok=True)
        config_path = config_dir / "config.yaml"
        with open(config_path, "w", encoding="utf-8") as f:
            yaml.dump(config, f, allow_unicode=True)
        logger.info(f"Config file scritto correttamente: {config_path}")
        return config_path
    except Exception as e:
        logger.error(f"Errore nella scrittura del file di configurazione: {e}")
        raise


def get_client_config(slug: str) -> dict:
    config_path = Path(f"output/timmy-kb-{slug}/config/config.yaml")
    if not config_path.exists():
        raise FileNotFoundError(f"Config file non trovato: {config_path}")
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_settings_for_slug(slug: str = None):
    """
    Factory per generare una nuova istanza Settings agganciata sullo slug fornito.
    Usare SEMPRE questa factory negli orchestratori per-client.
    """
    import os
    if slug:
        os.environ["SLUG"] = slug
    return Settings()

# Patch di compatibilità per moduli legacy che importano `settings` direttamente
try:
    settings = Settings()
except Exception as e:
    logger.warning(
        f"[Compat] Impossibile istanziare settings al volo: {e}. "
        "Usare get_settings_for_slug(slug) per ottenere un'istanza valida."
    )
    settings = None
