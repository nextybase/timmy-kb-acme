"""
src/pipeline/config_utils.py

Configurazione centralizzata pipeline Timmy-KB.
Tutti i nomi 1:1 con .env e config.yaml, con property dinamiche per path e compatibilità moduli.
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

    Flow di configurazione:
      1. Cerca parametri prima nelle variabili d’ambiente (es. export DRIVE_ID=...)
      2. Se assenti, cerca in .env (root progetto)
      3. Usa default dichiarati nella classe SOLO per i non critici
      4. Sostituisce automaticamente {slug} nei path template (se usi path template)
      5. Parametri critici: errore se mancanti, pipeline non parte
      6. Tutti i moduli consumano la config solo via 'from pipeline.config_utils import settings'
    """

    # === GOOGLE DRIVE ===
    DRIVE_ID: str = Field(..., env="DRIVE_ID", description="ID Drive condiviso clienti (obbligatorio)")
    SERVICE_ACCOUNT_FILE: str = Field(..., env="SERVICE_ACCOUNT_FILE", description="Credenziali Google API (obbligatorio)")
    BASE_DRIVE: Optional[str] = Field(None, env="BASE_DRIVE", description="Path base reale su filesystem locale (opzionale)")

    # === GITHUB ===
    GITHUB_TOKEN: str = Field(..., env="GITHUB_TOKEN", description="Token OAuth GitHub (obbligatorio)")

    # === GITBOOK API (solo se usata in futuro) ===
    GITBOOK_TOKEN: Optional[str] = Field(None, env="GITBOOK_TOKEN", description="Token API GitBook (opzionale)")

    # === ALTRI (aggiungili qui se presenti in config.yaml/.env) ===
    SLUG: Optional[str] = Field(None, env="SLUG", description="Slug identificativo progetto (opzionale, preferito se presente)")
    # Altri parametri custom (aggiungi se necessario) ...

    LOG_LEVEL: str = Field("INFO", env="LOG_LEVEL", description="Livello logging")
    DEBUG: bool = Field(False, env="DEBUG", description="Debug mode")

    @model_validator(mode="after")
    def check_critici(cls, data):
        critici = ["DRIVE_ID", "SERVICE_ACCOUNT_FILE", "GITHUB_TOKEN"]
        for key in critici:
            if not getattr(data, key, None):
                logger.error(f"Parametro critico '{key}' mancante!")
                raise ValueError(f"Parametro critico '{key}' mancante!")
        return data

    # === PROPERTY DINAMICHE (compatibili legacy) ===

    @property
    def slug(self) -> str:
        """
        Restituisce lo slug prioritariamente dalla variabile SLUG,
        oppure deriva da DRIVE_ID (fallback) o da output_dir.
        """
        if self.SLUG:
            return self.SLUG
        return self.DRIVE_ID.lower().replace("_", "-")

    @property
    def output_dir(self) -> Path:
        """
        Path radice output cliente (es: output/timmy-kb-{slug})
        """
        return Path(f"output/timmy-kb-{self.slug}")

    @property
    def raw_dir(self) -> Path:
        """
        Path cartella raw PDF (es: output/timmy-kb-{slug}/raw)
        """
        return self.output_dir / "raw"

    @property
    def md_output_path(self) -> Path:
        """
        Path cartella markdown finali (es: output/timmy-kb-{slug}/book)
        """
        return self.output_dir / "book"

    @property
    def book_dir(self) -> Path:
        """Alias retrocompatibile."""
        return self.md_output_path

    @property
    def output_dir_path(self) -> Path:
        """Alias retrocompatibile."""
        return self.output_dir

    @property
    def logs_path(self) -> Path:
        """
        Restituisce il path file di log principale.
        Usa logs/timmy-kb-<slug>.log.
        """
        log_name = f"timmy-kb-{self.slug}.log"
        return Path("logs") / log_name
    
    @property
    def drive_folder_id(self) -> Optional[str]:
        """
        Restituisce l'ID della cartella cliente su Drive (drive_folder_id)
        leggendo dinamicamente dal config YAML del cliente.
        """
        config_path = self.output_dir / "config" / "config.yaml"
        if config_path.exists():
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    conf = yaml.safe_load(f)
                return conf.get("drive_folder_id")
            except Exception as e:
                logger.warning(f"Impossibile leggere drive_folder_id da {config_path}: {e}")
        return None

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True

settings = Settings()

if __name__ == "__main__":
    print(f"SERVICE_ACCOUNT_FILE from settings: {settings.SERVICE_ACCOUNT_FILE}")


def write_client_config_file(config: dict, slug: str) -> Path:
    """
    Scrive la configurazione YAML nella cartella di output del cliente
    in output/timmy-kb-<slug>/config/config.yaml.
    Restituisce il path del file creato.
    Logga warning/error se la scrittura fallisce.

    Args:
        config (dict): Dizionario di configurazione da salvare.
        slug (str): Identificativo cliente/progetto.

    Returns:
        Path: Percorso file YAML creato.
    """
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

# Utility per leggere config cliente dal YAML (per drive_folder_id e altri parametri dinamici)
def get_client_config(slug: str) -> dict:
    """
    Carica la config YAML di un cliente dal path standard.
    Utile per recuperare drive_folder_id e altri parametri non-globali.
    """
    config_path = Path(f"output/timmy-kb-{slug}/config/config.yaml")
    if not config_path.exists():
        raise FileNotFoundError(f"Config file non trovato: {config_path}")
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)
