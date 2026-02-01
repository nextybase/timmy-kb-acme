# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from pipeline.env_utils import get_env_var
from pipeline.exceptions import ConfigError
from pipeline.logging_utils import get_structured_logger
from pipeline.settings import Settings
from ui.utils.repo_root import get_repo_root


@dataclass
class DriveEnvConfig:
    service_account_file: Optional[str]
    drive_id: Optional[str]
    parent_folder_id: Optional[str]
    service_account_ok: bool
    drive_id_ok: bool

    @property
    def download_ready(self) -> bool:
        """True se abbiamo credenziali minime per abilitare il download da Drive."""
        return self.service_account_ok and self.drive_id_ok


def get_drive_env_config() -> DriveEnvConfig:
    """
    Legge le variabili legate a Drive e restituisce un oggetto tipizzato con flag di validazione.
    """
    saf = get_env_var("SERVICE_ACCOUNT_FILE", default=None)
    drive_id = get_env_var("DRIVE_ID", default=None)
    parent = get_env_var("DRIVE_PARENT_FOLDER_ID", default=None)

    service_account_ok = False
    if saf:
        try:
            path = Path(saf).expanduser()
            service_account_ok = path.exists()
        except Exception:
            service_account_ok = False

    drive_id_ok = bool(drive_id and drive_id.strip())

    return DriveEnvConfig(
        service_account_file=saf,
        drive_id=drive_id,
        parent_folder_id=parent,
        service_account_ok=service_account_ok,
        drive_id_ok=drive_id_ok,
    )


@dataclass
class TagsEnvConfig:
    raw_value: str
    normalized: str

    @property
    def is_stub(self) -> bool:
        return self.normalized == "stub"


def get_tags_env_config() -> TagsEnvConfig:
    """
    Legge TAGS_MODE dall'ambiente, normalizzando il valore senza imporre vincoli.
    """
    raw = get_env_var("TAGS_MODE", default="") or ""
    normalized = raw.strip().lower()
    return TagsEnvConfig(raw_value=raw, normalized=normalized)


def resolve_ui_allow_local_only() -> bool:
    """Legge ui.allow_local_only dalla configurazione runtime (repo root)."""
    logger = get_structured_logger("ui.config")
    try:
        settings_obj = Settings.load(get_repo_root())
    except Exception as exc:
        logger.error("ui.config.load_failed", extra={"error": str(exc)})
        raise ConfigError(
            "Impossibile caricare la configurazione: modalita runtime non determinabile.",
        ) from exc
    try:
        return bool(settings_obj.ui_allow_local_only)
    except Exception as exc:
        logger.error("ui.config.allow_local_only_failed", extra={"error": str(exc)})
        raise ConfigError(
            "Impossibile leggere ui_allow_local_only dalla configurazione.",
        ) from exc
