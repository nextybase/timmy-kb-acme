# SPDX-License-Identifier: GPL-3.0-only
# src/pipeline/config_utils.py
"""Configurazione cliente e utilities (SSoT + path-safety).

Cosa fa questo file
-------------------
Centralizza le utilità di configurazione per la pipeline Timmy-KB:

- `ClientEnvSettings`: modello Pydantic per le variabili ambiente critiche (Drive, GitHub,
  ecc.), con validazione dei campi essenziali e presenza dello `slug`.
- `write_client_config_file(context, config) -> Path`: serializza e salva
  **atomicamente** `config.yaml` nella sandbox del cliente usando `safe_write_text`
  (backup `.bak` incluso).
- `get_client_config(context) -> dict`: legge e deserializza `config.yaml` dal
  contesto (errore se assente/malformato).
- `validate_preonboarding_environment(context, repo_root_dir=None)`: verifica minima di
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
from typing import TYPE_CHECKING, Any, Mapping, Optional, TypedDict, cast

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

from pipeline.beta_flags import is_beta_strict
from pipeline.constants import BACKUP_SUFFIX
from pipeline.context import ClientContext
from pipeline.exceptions import ConfigError, PipelineError, PreOnboardingValidationError
from pipeline.file_utils import safe_write_text
from pipeline.logging_utils import get_structured_logger
from pipeline.path_utils import ensure_within, read_text_safe
from pipeline.settings import Settings as ContextSettings
from pipeline.workspace_layout import WorkspaceLayout

logger = get_structured_logger("pipeline.config_utils")


class ClientConfigPayload(TypedDict, total=False):
    semantic_defaults: dict[str, Any]
    semantic_mapping_path: str
    client_name: str
    slug: str


_LEGACY_DRIVE_KEY_MAP: dict[str, str] = {
    "drive_folder_id": "folder_id",
    "drive_raw_folder_id": "raw_folder_id",
    "drive_contrattualistica_folder_id": "contrattualistica_folder_id",
    "drive_config_folder_id": "config_folder_id",
}


def _coerce_nonempty_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        candidate = value.strip()
        return candidate or None
    return str(value).strip() or None


def _ensure_mapping(parent: dict[str, Any], key: str) -> dict[str, Any]:
    current = parent.get(key)
    if isinstance(current, Mapping):
        if isinstance(current, dict):
            return current
        current = dict(current)
        parent[key] = current
        return current
    new_map: dict[str, Any] = {}
    parent[key] = new_map
    return new_map


def _ensure_nested_mapping(parent: dict[str, Any], keys: tuple[str, ...]) -> dict[str, Any]:
    current = parent
    for key in keys:
        current = _ensure_mapping(current, key)
    return current


def _deep_merge_dict(base: dict[str, Any], updates: Mapping[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = dict(base)
    for key, value in updates.items():
        if isinstance(value, Mapping) and isinstance(result.get(key), Mapping):
            merged = _deep_merge_dict(dict(cast(Mapping[str, Any], result[key])), cast(Mapping[str, Any], value))
            result[key] = merged
        else:
            result[key] = value
    return result


def _extract_legacy_vision_value(payload: dict[str, Any]) -> tuple[Optional[str], list[str]]:
    removed: list[str] = []
    legacy_value: Optional[str] = None

    if "vision_statement_pdf" in payload:
        legacy_value = _coerce_nonempty_str(payload.get("vision_statement_pdf")) or legacy_value
        payload.pop("vision_statement_pdf", None)
        removed.append("vision_statement_pdf")

    meta = payload.get("meta")
    if isinstance(meta, Mapping):
        meta_dict = dict(meta)
        if "vision_statement_pdf" in meta_dict:
            legacy_value = _coerce_nonempty_str(meta_dict.get("vision_statement_pdf")) or legacy_value
            meta_dict.pop("vision_statement_pdf", None)
            payload["meta"] = meta_dict
            removed.append("meta.vision_statement_pdf")

    return legacy_value, removed


def _migrate_legacy_keys(payload: dict[str, Any]) -> tuple[dict[str, Any], list[str], bool]:
    migrated_keys: list[str] = []
    data = dict(payload)
    drive_section: dict[str, Any] | None = None

    for legacy_key, drive_key in _LEGACY_DRIVE_KEY_MAP.items():
        if legacy_key not in data:
            continue
        if drive_section is None:
            drive_section = _ensure_nested_mapping(data, ("integrations", "drive"))
        legacy_value = _coerce_nonempty_str(data.get(legacy_key))
        data.pop(legacy_key, None)
        migrated_keys.append(legacy_key)
        if drive_section is not None and legacy_value and not _coerce_nonempty_str(drive_section.get(drive_key)):
            drive_section[drive_key] = legacy_value

    legacy_vision, removed_vision_keys = _extract_legacy_vision_value(data)
    moved_vision = False
    if legacy_vision:
        vision_section = _ensure_nested_mapping(data, ("ai", "vision"))
        if not _coerce_nonempty_str(vision_section.get("vision_statement_pdf")):
            vision_section["vision_statement_pdf"] = legacy_vision
            moved_vision = True

    migrated_keys.extend(removed_vision_keys)

    return data, migrated_keys, moved_vision


def _has_legacy_config_keys(payload: Mapping[str, Any]) -> bool:
    if any(key in payload for key in _LEGACY_DRIVE_KEY_MAP):
        return True
    if "vision_statement_pdf" in payload:
        return True
    meta = payload.get("meta")
    return isinstance(meta, Mapping) and "vision_statement_pdf" in meta


def get_drive_config(config: Mapping[str, Any]) -> dict[str, Any]:
    integrations = config.get("integrations")
    if not isinstance(integrations, Mapping):
        return {}
    drive = integrations.get("drive")
    if not isinstance(drive, Mapping):
        return {}
    return dict(drive)


def get_drive_id(config: Mapping[str, Any], key: str) -> Optional[str]:
    drive = get_drive_config(config)
    return _coerce_nonempty_str(drive.get(key))


def _extract_context_settings(context: ClientContext) -> tuple[Optional[ContextSettings], dict[str, Any], bool]:
    """Ritorna (wrapper Settings, payload dict, available)."""
    settings_obj = getattr(context, "settings", None)
    if isinstance(settings_obj, ContextSettings):
        return settings_obj, settings_obj.as_dict(), True
    if isinstance(settings_obj, Mapping):
        return None, dict(settings_obj), True
    return None, {}, False


def _refresh_context_settings(context: ClientContext) -> None:
    """Ricarica il Settings wrapper dopo una write, se possibile."""
    if context.repo_root_dir is None or context.config_path is None:
        return
    try:
        context.settings = ContextSettings.load(
            cast(Path, context.repo_root_dir),
            config_path=cast(Path, context.config_path),
            slug=context.slug,
        )
    except Exception as exc:  # noqa: BLE001
        if is_beta_strict():
            raise ConfigError(
                "Impossibile ricaricare Settings dopo write (strict mode).",
                slug=context.slug,
                file_path=str(context.config_path),
            ) from exc
        logger.warning(
            "pipeline.config_utils.context_settings_refresh_failed",
            extra={
                "slug": context.slug,
                "repo_root_dir": str(context.repo_root_dir),
                "config_path": str(context.config_path),
                "error": str(exc)[:200],
            },
        )


def load_client_settings(
    context: ClientContext,
    *,
    reload: bool = False,
    logger: Optional[logging.Logger] = None,
) -> ContextSettings:
    """API unica per ottenere il `Settings` del cliente a runtime (SSoT).

    - Riusa `context.settings` se già presente e typed, a meno di `reload=True`.
    - Carica tramite `Settings.load(...)` usando i path del contesto.
    - Aggiorna `context.settings` per mantenere l'invariante SSoT nel chiamante.
    """
    if not reload:
        current = getattr(context, "settings", None)
        if isinstance(current, ContextSettings):
            return current

    cfg_path = context.config_path
    root_dir = context.repo_root_dir
    if root_dir is None or cfg_path is None:
        raise PipelineError("Contesto incompleto: workspace root/config_path mancanti", slug=context.slug)

    settings_raw = ContextSettings.load(
        cast(Path, root_dir),
        config_path=cast(Path, cfg_path),
        logger=logger,
        slug=context.slug,
    )
    if hasattr(settings_raw, "as_dict"):
        settings = settings_raw
    else:
        payload: dict[str, Any] = {}
        if isinstance(settings_raw, Mapping):
            payload = dict(settings_raw)
        else:
            try:
                payload = dict(vars(settings_raw))
            except Exception as exc:  # noqa: BLE001
                # Beta 1.0 STRICT: vietato degradare a payload vuoto.
                # Se Settings.load(...) restituisce un oggetto non convertibile,
                # è un errore di provisioning/versione non supportata.
                if logger:
                    logger.error(
                        "pipeline.config_utils.settings_payload_coerce_failed",
                        extra={
                            "slug": context.slug,
                            "repo_root_dir": str(root_dir),
                            "config_path": str(cfg_path),
                            "error": str(exc)[:200],
                            "settings_type": type(settings_raw).__name__,
                        },
                    )
                raise ConfigError(
                    "Impossibile convertire Settings in payload dict (mapping/vars falliti). Runtime strict.",
                    slug=context.slug,
                    file_path=str(cfg_path),
                ) from exc
        settings = ContextSettings(config_path=cast(Path, cfg_path), data=payload)
    context.settings = settings
    return settings


# ----------------------------------------------------------
#  Modello pydantic per configurazione cliente
# ----------------------------------------------------------
class ClientEnvSettings(_BaseSettings):
    """Modello Pydantic per i parametri ambiente specifici del cliente.

    Le variabili sono risolte dall'ambiente (.env/processo) tramite Pydantic.
    I campi critici vengono validati al termine dell'inizializzazione del modello.
    Nota: config.yaml resta non-segreto; qui si validano solo variabili d'ambiente.

    Attributi (principali):
        DRIVE_ID: ID dello Shared Drive (critico).
        SERVICE_ACCOUNT_FILE: Path al JSON del Service Account (critico).
        BASE_DRIVE: (opz.) Nome base per Drive.
        DRIVE_ROOT_ID: (opz.) ID della cartella radice cliente su Google Drive.
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
            # Nessuna azione se la super non definisce model_post_init.
            pass

        for key in ("DRIVE_ID", "SERVICE_ACCOUNT_FILE"):
            if not getattr(self, key, None):
                logger.error(
                    "pipeline.config_utils.missing_required_env",
                    extra={"missing_key": key},
                )
                raise ConfigError(f"Parametro critico '{key}' mancante!", key=key)
        if not self.slug:
            logger.error("pipeline.config_utils.missing_slug", extra={"param": "slug"})
            raise ConfigError("Parametro 'slug' mancante!", param="slug")


# ----------------------------------------------------------
#  Scrittura configurazione cliente su file YAML
# ----------------------------------------------------------
def write_client_config_file(context: ClientContext, config: ClientConfigPayload) -> Path:
    """Scrive il file `config.yaml` nella cartella cliente in modo atomico (backup + SSoT)."""
    layout = WorkspaceLayout.from_context(context)
    repo_root_dir = layout.repo_root_dir
    config_path = layout.config_path
    config_dir = config_path.parent

    config_dir.mkdir(parents=True, exist_ok=True)
    ensure_within(repo_root_dir, config_dir)
    ensure_within(repo_root_dir, config_path)

    if config_path.exists():
        backup_path = config_path.with_suffix(config_path.suffix + BACKUP_SUFFIX)
        shutil.copy(config_path, backup_path)
        logger.info(
            "pipeline.config_utils.backup_created",
            extra={"slug": context.slug, "backup_path": str(backup_path)},
        )

    config_to_dump: ClientConfigPayload = cast(ClientConfigPayload, dict(config))
    try:
        yaml_dump = yaml.safe_dump(config_to_dump, sort_keys=False, allow_unicode=True)
        safe_write_text(config_path, yaml_dump, encoding="utf-8", atomic=True)
    except Exception as exc:
        raise ConfigError(f"Errore scrittura config {config_path}.") from exc

    logger.info(
        "pipeline.config_utils.config_written",
        extra={"slug": context.slug, "file_path": str(config_path)},
    )
    _refresh_context_settings(context)
    return cast(Path, config_path)


# ----------------------------------------------------------
#  Lettura configurazione cliente
# ----------------------------------------------------------
def get_client_config(context: ClientContext) -> ClientConfigPayload:
    """Restituisce il contenuto del `config.yaml` dal contesto."""
    _, settings_payload, available = _extract_context_settings(context)
    if available:
        return cast(ClientConfigPayload, dict(settings_payload))
    settings = load_client_settings(context)
    return cast(ClientConfigPayload, settings.as_dict())


def ensure_config_migrated(
    context: ClientContext,
    *,
    logger: logging.Logger | None = None,
) -> bool:
    """Esegue la migrazione delle chiavi legacy solo su chiamata esplicita."""
    _, settings_payload, available = _extract_context_settings(context)
    if available:
        payload = dict(settings_payload)
    else:
        settings = load_client_settings(context)
        payload = settings.as_dict()

    if not _has_legacy_config_keys(payload):
        return False

    update_config_with_drive_ids(context, updates={}, logger=logger)
    return True


# ----------------------------------------------------------
#  Validazione pre-onboarding (coerenza minima ambiente)
# ----------------------------------------------------------
def validate_preonboarding_environment(context: ClientContext, repo_root_dir: Optional[Path] = None) -> None:
    """Verifica la coerenza minima dell'ambiente prima del pre-onboarding."""
    layout = WorkspaceLayout.from_context(context)
    resolved_repo_root_dir = repo_root_dir or layout.repo_root_dir
    config_path = layout.config_path
    if config_path is None:
        raise PipelineError(
            "Contesto incompleto: repo_root_dir/config_path mancanti",
            slug=context.slug,
        )

    if not config_path.exists():
        logger.error(
            "pipeline.config_utils.config_missing",
            extra={"config_path": str(config_path)},
        )
        raise PreOnboardingValidationError(f"Config cliente non trovato: {config_path}")

    _, _, available = _extract_context_settings(context)
    if not available:
        try:
            from pipeline.path_utils import ensure_within_and_resolve
            from pipeline.yaml_utils import yaml_read

            # Path-safety in LETTURA
            safe_cfg_path = ensure_within_and_resolve(config_path.parent, config_path)
            raw_cfg = yaml_read(safe_cfg_path.parent, safe_cfg_path)
        except Exception as e:
            logger.error(
                "pipeline.config_utils.config_read_error",
                extra={"config_path": str(config_path), "error": str(e)[:200]},
            )
            raise PreOnboardingValidationError(f"Errore lettura config {config_path}: {e}") from e

        if not isinstance(raw_cfg, dict):
            logger.error(
                "pipeline.config_utils.config_invalid",
                extra={"config_path": str(context.config_path)},
            )
            raise PreOnboardingValidationError("Config YAML non valido o vuoto.")

    # Verifica/creazione directory richieste (logs)
    logs_dir = ensure_within_and_resolve(resolved_repo_root_dir, resolved_repo_root_dir / "logs")
    if not logs_dir.exists():
        logger.warning(
            "pipeline.config_utils.logs_dir_missing",
            extra={"path": str(logs_dir)},
        )
        logs_dir.mkdir(parents=True, exist_ok=True)

    logger.info(
        "pipeline.config_utils.preonboarding_ok",
        extra={"slug": context.slug},
    )


# ----------------------------------------------------------
#  Scrittura sicura di file generici (wrapper interno) - ATOMICA
# ----------------------------------------------------------


# ----------------------------------------------------------
#  Merge incrementale su config.yaml con backup
# ----------------------------------------------------------
def merge_client_config_from_template(
    context: ClientContext,
    template_path: Path,
    preserve_keys: tuple[str, ...] = ("client_name", "slug"),
    logger: logging.Logger | None = None,
) -> Path:
    """Unisce il config cliente con il template mantenendo chiavi sensibili."""
    layout = WorkspaceLayout.from_context(context)
    config_path = layout.config_path
    repo_root_dir = layout.repo_root_dir
    if config_path is None:
        raise PipelineError("Contesto incompleto: config_path/repo_root_dir mancanti", slug=context.slug)

    log = logger or globals().get("logger")

    if not template_path.exists():
        return config_path

    template_payload: dict[str, Any] = {}
    try:
        template_text = read_text_safe(template_path.parent, template_path, encoding="utf-8")
        template_payload = yaml.safe_load(template_text) if template_text else {}
    except FileNotFoundError:
        return config_path
    except Exception as exc:  # pragma: no cover
        raise ConfigError(f"Errore lettura template config {template_path}.") from exc

    template_data: dict[str, Any] = dict(template_payload or {})

    existing_data: dict[str, Any] = {}
    if config_path.exists():
        backup_path = config_path.with_suffix(config_path.suffix + BACKUP_SUFFIX)
        shutil.copy(config_path, backup_path)
        if log:
            log.info("config.client.backup", extra={"slug": context.slug, "path": str(backup_path)})

        _, settings_payload, available = _extract_context_settings(context)
        if available:
            existing_data = dict(settings_payload)
        else:
            try:
                from pipeline.yaml_utils import yaml_read

                current = yaml_read(config_path.parent, config_path) or {}
                if isinstance(current, dict):
                    existing_data = dict(current)
            except Exception as exc:
                raise ConfigError(f"Errore lettura config esistente {config_path}.") from exc

    preserve_set = set(preserve_keys)

    def _merge_dict(base: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
        result: dict[str, Any] = dict(base)
        for key, value in overrides.items():
            if key in preserve_set:
                result[key] = value
                continue
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = _merge_dict(cast(dict[str, Any], result[key]), value)
            else:
                result[key] = value
        return result

    merged: dict[str, Any] = _merge_dict(template_data, existing_data)

    ensure_within(repo_root_dir, config_path)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        serialized = yaml.safe_dump(merged, sort_keys=False, allow_unicode=True)
        safe_write_text(config_path, serialized, encoding="utf-8", atomic=True)
    except Exception as exc:  # pragma: no cover
        raise ConfigError(f"Errore scrittura config {config_path}.") from exc

    if log:
        log.info(
            "config.client.merged",
            extra={
                "slug": context.slug,
                "dst": str(config_path),
                "preserved": list(preserve_keys),
            },
        )

    _refresh_context_settings(context)

    return config_path


def update_config_with_drive_ids(
    context: ClientContext,
    updates: dict[str, Any],
    logger: logging.Logger | None = None,
) -> None:
    """Aggiorna il file `config.yaml` del cliente con i valori forniti.

    Comportamento:
      - Esegue backup `.bak` del config esistente.
      - Esegue deep merge deterministico (dict ricorsivi, liste sostituiscono).
      - Migra chiavi legacy drive_* e vision_statement_pdf in place.
      - Scrive via `safe_write_text` in modo atomico.

    Raises:
        ConfigError: se la lettura/scrittura del config fallisce o se il file e assente.
    """
    layout = WorkspaceLayout.from_context(context)
    config_path = layout.config_path
    repo_root_dir = layout.repo_root_dir
    if config_path is None:
        raise PipelineError(
            "Contesto incompleto: config_path/repo_root_dir mancanti",
            slug=context.slug,
        )

    if not config_path.exists():
        raise ConfigError(f"Config file non trovato: {config_path}")

    # Backup file esistente
    backup_path = config_path.with_suffix(config_path.suffix + BACKUP_SUFFIX)
    shutil.copy(config_path, backup_path)
    if logger:
        logger.info(
            "pipeline.config_utils.backup_created",
            extra={"backup_path": str(backup_path)},
        )

    # Carica config esistente (preferendo il contesto)
    _, settings_payload, available = _extract_context_settings(context)
    if available:
        config_data: dict[str, Any] = dict(settings_payload)
    else:
        try:
            from pipeline.yaml_utils import yaml_read

            config_raw = yaml_read(config_path.parent, config_path) or {}
        except Exception as e:
            raise ConfigError(f"Errore lettura config {config_path}.") from e

        if not isinstance(config_raw, dict):
            raise ConfigError("Config YAML non valido.")
        config_data = dict(config_raw)

    config_data, migrated_keys, moved_vision = _migrate_legacy_keys(config_data)
    normalized_updates, updates_migrated, updates_moved_vision = _migrate_legacy_keys(dict(updates or {}))
    drive_migrated = [k for k in (migrated_keys + updates_migrated) if k in _LEGACY_DRIVE_KEY_MAP]
    vision_moved = moved_vision or updates_moved_vision

    log = logger or globals().get("logger")
    if drive_migrated and log:
        log.info(
            "config.migrated.legacy_flat_drive_keys",
            extra={"count": len(drive_migrated), "keys": sorted(set(drive_migrated))},
        )
    if vision_moved and log:
        log.info("config.migrated.vision_statement_pdf", extra={"slug": context.slug})

    config_data = _deep_merge_dict(config_data, normalized_updates)

    remaining_drive = [key for key in _LEGACY_DRIVE_KEY_MAP if key in config_data]
    if remaining_drive:
        msg = f"Chiavi legacy Drive non rimosse dal config: {', '.join(remaining_drive)}"
        if is_beta_strict():
            raise ConfigError(msg, slug=context.slug, file_path=str(config_path))
        if log:
            log.warning("config.legacy_drive_keys_remaining", extra={"keys": remaining_drive})

    remaining_vision: list[str] = []
    if "vision_statement_pdf" in config_data:
        remaining_vision.append("vision_statement_pdf")
    meta_section = config_data.get("meta")
    if isinstance(meta_section, Mapping) and "vision_statement_pdf" in meta_section:
        remaining_vision.append("meta.vision_statement_pdf")
    if remaining_vision:
        msg = f"Chiavi legacy VisionStatement non rimosse dal config: {', '.join(remaining_vision)}"
        if is_beta_strict():
            raise ConfigError(msg, slug=context.slug, file_path=str(config_path))
        if log:
            log.warning("config.legacy_vision_statement_remaining", extra={"keys": remaining_vision})

    # Scrittura sicura (atomica) + path-safety
    ensure_within(repo_root_dir, config_path)
    try:
        yaml_dump = yaml.safe_dump(config_data, sort_keys=False, allow_unicode=True)
        safe_write_text(config_path, yaml_dump, encoding="utf-8", atomic=True)
        if log:
            log.info(
                "pipeline.config_utils.config_written",
                extra={"config_path": str(config_path)},
            )
    except Exception as e:
        raise ConfigError(f"Errore scrittura config {config_path}.") from e
    _refresh_context_settings(context)


__all__ = [
    "ClientEnvSettings",
    "write_client_config_file",
    "get_client_config",
    "ensure_config_migrated",
    "load_client_settings",
    "validate_preonboarding_environment",
    "merge_client_config_from_template",
    "update_config_with_drive_ids",
    "get_drive_config",
    "get_drive_id",
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
    current_raw = cfg.get("N_VER", 0)
    if isinstance(current_raw, (int, float, str)):
        try:
            current = int(current_raw) if current_raw not in (None, "") else 0
        except Exception:
            current = 0
    else:
        current = 0
    new_val = current + 1
    if log:
        log.info(
            "config.n_ver.bumped",
            extra={"old": current, "new": new_val, "slug": context.slug},
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
        log.info("config.data_ver.set", extra={"value": today, "slug": context.slug})
    update_config_with_drive_ids(context, updates={"DATA_VER": today}, logger=log)
