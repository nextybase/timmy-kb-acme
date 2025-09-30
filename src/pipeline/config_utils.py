# src/pipeline/config_utils.py
"""Configurazione cliente e utilities (SSoT + path-safety).

Cosa fa questo file
-------------------
Centralizza le utilità di configurazione per la pipeline Timmy-KB:

- `Settings`: modello Pydantic per le variabili ambiente critiche (Drive, GitHub,
  ecc.), con validazione dei campi essenziali e presenza dello `slug`.
- `write_client_config_file(context, config) -> Path`: serializza e salva
  **atomicamente** `config.yaml` nella sandbox del cliente usando `safe_write_text`
  (backup `.bak` incluso).
- `get_client_config(context) -> dict`: legge e deserializza `config.yaml` dal
  contesto (errore se assente/malformato).
- `validate_preonboarding_environment(context, base_dir=None)`: verifica minima di
  ambiente (config valido e cartelle chiave come `logs/`).
- `update_config_with_drive_ids(context, updates, logger=None)`: merge incrementale
  su `config.yaml` con backup `.bak` e scrittura atomica.

Linee guida implementative
--------------------------
- **SSoT scritture**: tutte le write passano da `pipeline.file_utils.safe_write_text`.
- **Path-safety STRONG**: prima di scrivere nella sandbox, validiamo con
  `ensure_within(...)`.
- **Niente prompt/exit**: orchestrazione (I/O utente e gestione exit code) demandata
  ai caller.
"""

from __future__ import annotations

import logging
import shutil
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional, cast

import yaml
from pydantic import AliasChoices, Field

if TYPE_CHECKING:

    class _BaseSettings:
        def model_post_init(self, __context: Any) -> None: ...

    class _SettingsConfigDict:  # shim per type checking
        pass

else:
    from pydantic_settings import (  # type: ignore
        BaseSettings as _BaseSettings,
        SettingsConfigDict as _SettingsConfigDict,
    )

from pipeline.constants import BACKUP_SUFFIX, CONFIG_DIR_NAME, CONFIG_FILE_NAME
from pipeline.context import ClientContext
from pipeline.exceptions import ConfigError, PipelineError, PreOnboardingValidationError
from pipeline.file_utils import safe_write_text
from pipeline.logging_utils import get_structured_logger
from pipeline.path_utils import ensure_within

logger = get_structured_logger("pipeline.config_utils")


# ----------------------------------------------------------
#  Modello pydantic per configurazione cliente
# ----------------------------------------------------------
class Settings(_BaseSettings):
    """Modello di configurazione cliente per pipeline Timmy-KB.

    Le variabili sono risolte dall'ambiente (.env/processo) tramite Pydantic.
    I campi critici vengono validati al termine dell'inizializzazione del modello.

    Attributi (principali):
        DRIVE_ID: ID dello Shared Drive (critico).
        SERVICE_ACCOUNT_FILE: Path al JSON del Service Account (critico).
        BASE_DRIVE: (opz.) Nome base per Drive.
        DRIVE_ROOT_ID: (opz.) ID della cartella radice cliente su Google Drive.
        GITHUB_TOKEN: Token GitHub per operazioni di push (critico).
        GITBOOK_TOKEN: (opz.) Token GitBook.
        slug: Identificativo cliente (necessario a runtime tramite `ClientContext`).
        LOG_LEVEL: Livello di log (default: "INFO").
        DEBUG: Flag di debug (default: False).
    """

    # pydantic-settings v2: usare validation_alias per mappare env name
    DRIVE_ID: str = Field(validation_alias=AliasChoices("DRIVE_ID"))
    SERVICE_ACCOUNT_FILE: str = Field(validation_alias=AliasChoices("SERVICE_ACCOUNT_FILE"))
    BASE_DRIVE: Optional[str] = Field(default=None, validation_alias=AliasChoices("BASE_DRIVE"))
    DRIVE_ROOT_ID: Optional[str] = Field(
        default=None,
        description="ID cartella radice cliente su Google Drive",
        validation_alias=AliasChoices("DRIVE_ROOT_ID"),
    )
    GITHUB_TOKEN: str = Field(validation_alias=AliasChoices("GITHUB_TOKEN"))
    GITBOOK_TOKEN: Optional[str] = Field(default=None, validation_alias=AliasChoices("GITBOOK_TOKEN"))
    LOG_LEVEL: str = Field(default="INFO", validation_alias=AliasChoices("LOG_LEVEL"))
    DEBUG: bool = Field(default=False, validation_alias=AliasChoices("DEBUG"))
    slug: Optional[str] = None

    # Config per pydantic-settings v2
    if not TYPE_CHECKING:
        model_config: _SettingsConfigDict = _SettingsConfigDict(
            env_prefix="",
        )

    def model_post_init(self, __context: Any) -> None:
        # pyright/pylance: ok, chiamiamo super se esiste
        try:
            super().model_post_init(__context)
        except Exception:
            # compat, nessuna azione se la super non definisce model_post_init
            pass

        for key in ("DRIVE_ID", "SERVICE_ACCOUNT_FILE", "GITHUB_TOKEN"):
            if not getattr(self, key, None):
                logger.error(f"Parametro critico '{key}' mancante!")
                raise ValueError(f"Parametro critico '{key}' mancante!")
        if not self.slug:
            logger.error("Parametro 'slug' mancante! Usare ClientContext.load(slug).")
            raise ValueError("Parametro 'slug' mancante!")


# ----------------------------------------------------------
#  Scrittura configurazione cliente su file YAML
# ----------------------------------------------------------
def write_client_config_file(context: ClientContext, config: dict[str, Any]) -> Path:
    """Scrive il file `config.yaml` nella cartella cliente in modo atomico (backup + SSoT)."""
    output_dir = context.output_dir
    base_dir = context.base_dir
    if output_dir is None or base_dir is None:
        raise PipelineError(
            "Contesto incompleto: output_dir/base_dir mancanti",
            slug=context.slug,
        )
    output_dir = cast(Path, output_dir)
    base_dir = cast(Path, base_dir)

    config_dir = output_dir / CONFIG_DIR_NAME
    config_path = config_dir / CONFIG_FILE_NAME

    config_dir.mkdir(parents=True, exist_ok=True)
    ensure_within(base_dir, config_dir)
    ensure_within(base_dir, config_path)

    if config_path.exists():
        backup_path = config_path.with_suffix(config_path.suffix + BACKUP_SUFFIX)
        shutil.copy(config_path, backup_path)
        logger.info(
            "Backup config creato",
            extra={"slug": context.slug, "file_path": str(backup_path)},
        )

    config_to_dump: dict[str, Any] = dict(config)
    try:
        yaml_dump = yaml.safe_dump(config_to_dump, sort_keys=False, allow_unicode=True)
        safe_write_text(config_path, yaml_dump, encoding="utf-8", atomic=True)
    except Exception as exc:
        raise ConfigError(f"Errore scrittura config {config_path}: {exc}") from exc

    logger.info(
        "Config cliente salvato",
        extra={"slug": context.slug, "file_path": str(config_path)},
    )
    return cast(Path, config_path)


# ----------------------------------------------------------
#  Lettura configurazione cliente
# ----------------------------------------------------------
def get_client_config(context: ClientContext) -> dict[str, Any]:
    """Restituisce il contenuto del `config.yaml` dal contesto."""
    if context.config_path is None:
        raise PipelineError("Contesto incompleto: config_path mancante", slug=context.slug)
    if not context.config_path.exists():
        raise ConfigError(f"Config file non trovato: {context.config_path}")
    try:
        from pipeline.path_utils import ensure_within_and_resolve
        from pipeline.yaml_utils import yaml_read

        # Path-safety anche in LETTURA
        safe_cfg_path = ensure_within_and_resolve(context.config_path.parent, context.config_path)
        data = yaml_read(safe_cfg_path.parent, safe_cfg_path) or {}
        if not isinstance(data, dict):
            raise ConfigError("Config YAML non valido.")
        return cast(dict[str, Any], data)
    except Exception as e:
        raise ConfigError(f"Errore lettura config {context.config_path}: {e}") from e


# ----------------------------------------------------------
#  Validazione pre-onboarding (coerenza minima ambiente)
# ----------------------------------------------------------
def validate_preonboarding_environment(context: ClientContext, base_dir: Optional[Path] = None) -> None:
    """Verifica la coerenza minima dell'ambiente prima del pre-onboarding."""
    base_dir = base_dir or context.base_dir
    if base_dir is None or context.config_path is None:
        raise PipelineError(
            "Contesto incompleto: base_dir/config_path mancanti",
            slug=context.slug,
        )

    if not context.config_path.exists():
        logger.error(f"❗ Config cliente non trovato: {context.config_path}")
        raise PreOnboardingValidationError(f"Config cliente non trovato: {context.config_path}")

    try:
        from pipeline.path_utils import ensure_within_and_resolve
        from pipeline.yaml_utils import yaml_read

        # Path-safety in LETTURA
        safe_cfg_path = ensure_within_and_resolve(context.config_path.parent, context.config_path)
        cfg = yaml_read(safe_cfg_path.parent, safe_cfg_path)
    except Exception as e:
        logger.error(f"❗ Errore lettura/parsing YAML in {context.config_path}: {e}")
        raise PreOnboardingValidationError(f"Errore lettura config {context.config_path}: {e}") from e

    if not isinstance(cfg, dict):
        logger.error("Config YAML non valido o vuoto.")
        raise PreOnboardingValidationError("Config YAML non valido o vuoto.")

    # Chiavi obbligatorie minime
    required_keys = ["cartelle_raw_yaml"]
    missing = [k for k in required_keys if k not in cfg]
    if missing:
        logger.error(f"❗ Chiavi obbligatorie mancanti in config: {missing}")
        raise PreOnboardingValidationError(f"Chiavi obbligatorie mancanti in config: {missing}")

    # Verifica/creazione directory richieste (logs)
    logs_dir = (base_dir / "logs").resolve()
    if not logs_dir.exists():
        logger.warning(f"⚠️ Directory mancante: {logs_dir}, creazione automatica...")
        logs_dir.mkdir(parents=True, exist_ok=True)

    logger.info(f"✅ Ambiente pre-onboarding valido per cliente {context.slug}")


# ----------------------------------------------------------
#  Scrittura sicura di file generici (wrapper legacy) – ATOMICA
# ----------------------------------------------------------


# ----------------------------------------------------------
#  Merge incrementale su config.yaml con backup
# ----------------------------------------------------------
def update_config_with_drive_ids(
    context: ClientContext,
    updates: dict[str, Any],
    logger: logging.Logger | None = None,
) -> None:
    """Aggiorna il file `config.yaml` del cliente con i valori forniti.

    Comportamento:
      - Esegue backup `.bak` del config esistente.
      - Aggiorna **solo** le chiavi presenti in `updates`.
      - Scrive via `safe_write_text` in modo atomico.

    Raises:
        ConfigError: se la lettura/scrittura del config fallisce o se il file è assente.
    """
    if context.config_path is None or context.base_dir is None:
        raise PipelineError(
            "Contesto incompleto: config_path/base_dir mancanti",
            slug=context.slug,
        )
    config_path = cast(Path, context.config_path)
    base_dir = cast(Path, context.base_dir)

    if not config_path.exists():
        raise ConfigError(f"Config file non trovato: {config_path}")

    # Backup file esistente
    backup_path = config_path.with_suffix(config_path.suffix + BACKUP_SUFFIX)
    shutil.copy(config_path, backup_path)
    if logger:
        logger.info(f"💾 Backup config creato: {backup_path}")

    # Carica config esistente (path-safety in LETTURA)
    try:
        from pipeline.yaml_utils import yaml_read

        config_raw = yaml_read(config_path.parent, config_path) or {}
    except Exception as e:
        raise ConfigError(f"Errore lettura config {config_path}: {e}") from e

    if not isinstance(config_raw, dict):
        raise ConfigError("Config YAML non valido.")
    config_data: dict[str, Any] = dict(config_raw)
    config_data.update(updates or {})

    # Scrittura sicura (atomica) + path-safety
    ensure_within(base_dir, config_path)
    try:
        yaml_dump = yaml.safe_dump(config_data, sort_keys=False, allow_unicode=True)
        safe_write_text(config_path, yaml_dump, encoding="utf-8", atomic=True)
        if logger:
            logger.info(f"✅ Config aggiornato in {config_path}")
    except Exception as e:
        raise ConfigError(f"Errore scrittura config {config_path}: {e}") from e


__all__ = [
    "Settings",
    "write_client_config_file",
    "get_client_config",
    "validate_preonboarding_environment",
    "update_config_with_drive_ids",
    "bump_n_ver_if_needed",
    "set_data_ver_today",
]


# ----------------------------------------------------------
#  Versioning helpers (N_VER / DATA_VER)
# ----------------------------------------------------------
def bump_n_ver_if_needed(context: ClientContext, logger: logging.Logger | None = None) -> None:
    """Incrementa N_VER di 1 nel config del cliente.

    Nota: la logica "if needed" è demandata al chiamante (UI tiene un flag di
    sessione) per garantire un solo incremento per sessione. Questa funzione è
    idempotente a livello di singola invocazione: legge il valore corrente
    (default 0) e scrive +1.
    """
    log = logger or globals().get("logger")
    cfg = get_client_config(context) or {}
    try:
        current = int(cfg.get("N_VER", 0) or 0)
    except Exception:
        current = 0
    new_val = current + 1
    if log:
        log.info(
            {
                "event": "bump_n_ver",
                "old": current,
                "new": new_val,
                "slug": context.slug,
            }
        )
    update_config_with_drive_ids(context, updates={"N_VER": new_val}, logger=log)


def set_data_ver_today(context: ClientContext, logger: logging.Logger | None = None) -> None:
    """Imposta DATA_VER alla data odierna (YYYY-MM-DD) nel config del cliente.

    Viene tipicamente chiamata alla chiusura della UI, solo se nella sessione ci
    sono state modifiche. Rimuove eventuali flag temporanei (nessun flag gestito qui).
    """
    log = logger or globals().get("logger")
    today = date.today().isoformat()
    if log:
        log.info({"event": "set_data_ver_today", "value": today, "slug": context.slug})
    update_config_with_drive_ids(context, updates={"DATA_VER": today}, logger=log)
