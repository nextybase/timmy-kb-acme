"""
Modulo Settings – Configurazione centralizzata pipeline Timmy-KB.
Gestisce alias/fallback per le variabili più usate (.env legacy e nuovi nomi).
"""
from pydantic_settings import BaseSettings
from pydantic import Field, ValidationError
from typing import Optional

class Settings(BaseSettings):
    # === Google Drive ===
    drive_id: str = Field(..., description="ID root cartella Google Drive")
    google_service_account_json: Optional[str] = Field(default=None, description="Path file service account JSON Google (preferito)")
    service_account_file: Optional[str] = Field(default=None, description="File credenziali Google API (legacy/compatibilità)")

    # === GitHub ===
    github_org: str = Field(..., description="Nome dell'utente GitHub")
    repo_clone_base: Optional[str] = None
    repo_visibility: Optional[str] = None
    github_token: Optional[str] = None

    # === Cartelle Pipeline / Template ===
    cartelle_raw_yaml: Optional[str] = None
    local_temp_config_path: Optional[str] = None

    # === Path dinamici per ingest pipeline ===
    raw_dir_template: Optional[str] = Field(default="output/timmy-kb-{slug}/raw")
    output_dir_template: Optional[str] = Field(default="output/timmy-kb-{slug}/book")
    base_drive: Optional[str] = None

    # === Docker Preview ===
    gitbook_image: Optional[str] = None

    # === GitBook API ===
    gitbook_token: Optional[str] = None
    gitbook_workspace: Optional[str] = None

    # === Logging ===
    log_file_path: Optional[str] = None
    log_max_bytes: Optional[str] = None
    log_backup_count: Optional[str] = None
    debug: Optional[str] = None

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"

    @property
    def drive_service_account_file(self) -> Optional[str]:
        # Ritorna la variabile preferita, altrimenti il fallback legacy
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
