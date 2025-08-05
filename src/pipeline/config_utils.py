"""
pipeline/config_utils.py
Utility e modello di configurazione per la pipeline Timmy-KB.
Gestione centralizzata dei path e dei parametri, con mappatura chiavi YAML → property Python.
"""

from dotenv import load_dotenv
load_dotenv()

import os
import yaml
from pathlib import Path
from pydantic import BaseModel, Field
from typing import Optional
from pipeline.logging_utils import get_structured_logger

logger = get_structured_logger("pipeline.config_utils")

# =======================
# MODELLI CONFIGURAZIONE
# =======================

class TimmySecrets(BaseModel):
    DRIVE_ID: Optional[str] = None
    SERVICE_ACCOUNT_FILE: Optional[str] = None
    GITHUB_TOKEN: Optional[str] = None
    # ... aggiungi altri secrets se necessari

class TimmyConfig(BaseModel):
    slug: str
    output_dir: str                  # Radice output cliente, es: output/timmy-kb-{slug}
    raw_dir: str                     # Cartella raw PDF, es: output/timmy-kb-{slug}/raw
    md_output_path: str              # Cartella markdown output, es: output/timmy-kb-{slug}/book
    config_path: Optional[str] = None# Path file config usato
    github_org: Optional[str] = None
    repo_visibility: Optional[str] = None
    gitbook_image: Optional[str] = None
    gitbook_workspace: Optional[str] = None
    log_file_path: Optional[str] = None
    log_max_bytes: Optional[int] = 1048576
    log_backup_count: Optional[int] = 3
    debug: Optional[bool] = False
    drive_folder_id: Optional[str] = None
    # ... altri parametri pipeline

    secrets: Optional[TimmySecrets] = None

    @property
    def output_dir_path(self) -> Path:
        """Path radice output cliente (output_dir)"""
        return Path(self.output_dir)

    @property
    def raw_dir_path(self) -> Path:
        """Path cartella raw PDF"""
        return Path(self.raw_dir)

    @property
    def md_output_path_path(self) -> Path:
        """Path cartella markdown finali"""
        return Path(self.md_output_path)

    @property
    def book_dir(self) -> Path:
        """Alias retrocompatibile per md_output_path"""
        return self.md_output_path_path

    @property
    def config_path_path(self) -> Optional[Path]:
        """Path oggetto file config, se valorizzato"""
        return Path(self.config_path) if self.config_path else None

    # Utility: path helper per altre sottocartelle future
    def subfolder(self, name: str) -> Path:
        """Restituisce il path di una sottocartella della radice output"""
        return self.output_dir_path / name

# =======================
# FUNZIONI DI UTILITY
# =======================

def get_config(slug: str) -> TimmyConfig:
    """
    Carica la config YAML del cliente dalla directory di output.
    Sostituisce i template path (con {slug}) e popola il modello TimmyConfig.
    Logga warning se il file config non esiste.
    """
    config_path = Path(f"output/timmy-kb-{slug}/config/config.yaml")
    if not config_path.exists():
        logger.warning(f"Config file non trovato: {config_path}")
        raise FileNotFoundError(f"Config file non trovato: {config_path}")

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config_dict = yaml.safe_load(f)
    except Exception as e:
        logger.error(f"Errore nel caricamento della config YAML: {e}")
        raise

    # Applica slug a tutti i template path della YAML
    config_dict["slug"] = slug
    config_dict["output_dir"] = config_dict.get("output_dir_template", f"output/timmy-kb-{slug}").format(slug=slug)
    config_dict["raw_dir"] = config_dict.get("raw_dir_template", f"output/timmy-kb-{slug}/raw").format(slug=slug)
    config_dict["md_output_path"] = str(Path(config_dict["output_dir"]) / "book")
    config_dict["config_path"] = str(config_path)

    # Carica eventuali secrets da env se presenti
    secrets_dict = {}
    for secret_key in ["DRIVE_ID", "SERVICE_ACCOUNT_FILE", "GITHUB_TOKEN"]:
        env_val = os.environ.get(secret_key)
        if env_val:
            secrets_dict[secret_key] = env_val
    secrets = TimmySecrets(**secrets_dict) if secrets_dict else None
    config_dict["secrets"] = secrets

    return TimmyConfig(**config_dict)

def write_client_config_file(config: dict, slug: str) -> Path:
    """
    Scrive la configurazione YAML nella cartella di output del cliente
    in output/timmy-kb-<slug>/config/config.yaml.
    Restituisce il path del file creato.
    Logga warning/error se la scrittura fallisce.
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

# Puoi aggiungere qui altre utility per gestione path/config
