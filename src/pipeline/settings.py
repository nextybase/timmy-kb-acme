"""
Modulo Settings – Configurazione centralizzata pipeline Timmy-KB.
Gestisce alias/fallback per le variabili più usate (.env legacy e nuovi nomi).
"""
from pathlib import Path
import os
from dotenv import load_dotenv

# === Universal .env loader: trova sempre la vera root del repo ===
REPO_ROOT = Path(__file__).resolve().parents[2]  # Due livelli sopra "src/pipeline/settings.py"
DOTENV_PATH = REPO_ROOT / ".env"

if DOTENV_PATH.exists():
    load_dotenv(dotenv_path=DOTENV_PATH, override=True)
    # print(f"[DEBUG] .env caricato da: {DOTENV_PATH}")
else:
    print(f"[DEBUG] .env NON TROVATO in {DOTENV_PATH}")

# print("[DEBUG] DRIVE_ID after dotenv:", os.environ.get("DRIVE_ID"))

from pydantic import Field, ValidationError
from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    # === Google Drive ===
    drive_id: str = Field(..., alias="DRIVE_ID", description="ID root cartella Google Drive")
    google_service_account_json: Optional[str] = Field(default=None, alias="GOOGLE_SERVICE_ACCOUNT_JSON", description="Path file service account JSON Google (preferito)")
    service_account_file: Optional[str] = Field(default=None, alias="SERVICE_ACCOUNT_FILE", description="File credenziali Google API (legacy/compatibilità)")

    # === GitHub ===
    github_org: str = Field(default="nextybase", alias="GITHUB_ORG", description="Nome dell'organizzazione o utente GitHub")
    github_token: Optional[str] = Field(default=None, alias="GITHUB_TOKEN")
    repo_clone_base: Optional[str] = Field(default=None, alias="REPO_CLONE_BASE")
    repo_visibility: Optional[str] = Field(default=None, alias="REPO_VISIBILITY")

    # === Cartelle Pipeline / Template ===
    cartelle_raw_yaml: Optional[str] = Field(default=None, alias="CARTELLE_RAW_YAML")
    local_temp_config_path: Optional[str] = Field(default=None, alias="LOCAL_TEMP_CONFIG_PATH")

    # === Path dinamici per ingest pipeline ===
    raw_dir_template: Optional[str] = Field(default="output/timmy-kb-{slug}/raw", alias="RAW_DIR_TEMPLATE")
    output_dir_template: Optional[str] = Field(default="output/timmy-kb-{slug}/book", alias="OUTPUT_DIR_TEMPLATE")
    base_drive: Optional[str] = Field(default=None, alias="BASE_DRIVE")

    # === Docker Preview ===
    gitbook_image: Optional[str] = Field(default=None, alias="GITBOOK_IMAGE")

    # === GitBook API ===
    gitbook_token: Optional[str] = Field(default=None, alias="GITBOOK_TOKEN")
    gitbook_workspace: Optional[str] = Field(default=None, alias="GITBOOK_WORKSPACE")

    # === Logging ===
    log_file_path: Optional[str] = Field(default=None, alias="LOG_PATH")
    log_max_bytes: Optional[str] = Field(default=None, alias="LOG_MAX_BYTES")
    log_backup_count: Optional[str] = Field(default=None, alias="LOG_BACKUP_COUNT")
    debug: Optional[str] = Field(default=None, alias="DEBUG")

    class Config:
        env_file = ".env"  # Qui è ridondante, dotenv carica già tutto.
        env_file_encoding = "utf-8"
        extra = "ignore"
        populate_by_name = True

    @property
    def drive_service_account_file(self) -> Optional[str]:
        return self.google_service_account_json or self.service_account_file

# Singleton pattern: usa sempre get_settings() per recuperare la config valida
_settings = None

def get_settings():
    global _settings
    if _settings is None:
        try:
            _settings = Settings()
        except ValidationError as e:
            print("\n❌ ERRORE DI CONFIGURAZIONE GLOBAL SETTINGS ❌\n")
            print(e)
            exit(1)
    return _settings
