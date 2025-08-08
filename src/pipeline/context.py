# src/pipeline/context.py

from pathlib import Path
from typing import Optional, Dict, Any, List
from pydantic import BaseModel

class PipelineContext(BaseModel):
    """
    Oggetto unificato per passaggio dati, stato e configurazione
    in tutte le funzioni della pipeline Timmy-KB.
    """
    # Identificativi
    slug: str
    client_name: Optional[str] = None

    # Configurazione centrale e parametri settings
    settings: Dict[str, Any]  # oppure: Settings (Pydantic)
    config_path: Path
    mapping_path: Optional[Path] = None

    # Directory & path operative
    log_path: Path
    output_dir: Path
    raw_dir: Path
    md_dir: Path

    # Drive / Output / Servizi esterni
    drive_folder_id: Optional[str] = None

    # Parametri di controllo flusso pipeline
    no_interactive: bool = False
    auto_push: bool = False
    skip_preview: bool = False

    # Logging e livello
    log_level: str = "INFO"

    # Stato run, errori, warning step-by-step
    error_list: List[str] = []
    warning_list: List[str] = []
    step_status: Dict[str, str] = {}

    # Dry-run flag (per test/pulizia)
    dry_run: bool = False

    # --- Metodi utili ---
    def log_error(self, msg: str):
        self.error_list.append(msg)

    def log_warning(self, msg: str):
        self.warning_list.append(msg)

    def set_step_status(self, step: str, status: str):
        self.step_status[step] = status

    # Shortcut: info di stato finale
    def summary(self):
        return {
            "slug": self.slug,
            "error_count": len(self.error_list),
            "warning_count": len(self.warning_list),
            "steps": self.step_status
        }
