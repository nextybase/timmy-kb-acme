#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
# src/pipeline/observability_config.py
"""
Gestione delle impostazioni globali di osservabilità / logging.

Le impostazioni sono salvate in uno YAML globale (default: ~/.timmykb/observability.yaml)
per non legarle a uno specifico workspace cliente.

Campi gestiti:
- stack_enabled: preferenza uso stack Grafana/Loki
- tracing_enabled: preferenza uso OpenTelemetry (OTLP)
- redact_logs: se abilitare i filtri di redazione nei logger strutturati
- log_level: livello di verbosity (DEBUG, INFO, WARNING, ERROR)

Queste impostazioni NON modificano da sole il comportamento:
devono essere lette dagli orchestratori / logging_utils in fase di init.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import urlencode, urljoin

import yaml

from pipeline.file_utils import safe_write_text
from pipeline.path_utils import ensure_within_and_resolve, read_text_safe

_OBS_CONFIG_ENV = "TIMMY_OBSERVABILITY_CONFIG"
_DEFAULT_RELATIVE_CONFIG = ".timmykb/observability.yaml"
_GRAFANA_URL_ENV = "TIMMY_GRAFANA_URL"
_GRAFANA_LOGS_UID_ENV = "TIMMY_GRAFANA_LOGS_UID"
_GRAFANA_ERRORS_UID_ENV = "TIMMY_GRAFANA_ERRORS_UID"


@dataclass(frozen=True)
class ObservabilitySettings:
    stack_enabled: bool = False
    tracing_enabled: bool = False
    redact_logs: bool = True
    log_level: str = "INFO"


def get_observability_config_path() -> Path:
    """
    Percorso del file di configurazione osservabilità.

    - Se TIMMY_OBSERVABILITY_CONFIG è impostata, usa quel path.
    - Altrimenti usa ~/.timmykb/observability.yaml
    """
    custom = os.getenv(_OBS_CONFIG_ENV)
    if custom:
        return Path(custom).expanduser()

    home = Path.home()
    return home / _DEFAULT_RELATIVE_CONFIG


def _normalize_level(level: str | None) -> str:
    if not isinstance(level, str):
        level = "" if level is None else str(level)
    level_upper = (level or "").upper()
    if level_upper not in {"DEBUG", "INFO", "WARNING", "ERROR"}:
        return "INFO"
    return level_upper


def load_observability_settings() -> ObservabilitySettings:
    """
    Carica le impostazioni globali di osservabilità dal file YAML.

    In caso di assenza o errore di parsing, ritorna i default safe.
    """
    path = get_observability_config_path()
    path_safe = ensure_within_and_resolve(path.parent, path)
    if not path_safe.exists():
        return ObservabilitySettings()

    try:
        raw: Dict[str, Any] = yaml.safe_load(read_text_safe(path_safe)) or {}
    except Exception:
        # In caso di file corrotto, fallback ai default
        return ObservabilitySettings()

    return ObservabilitySettings(
        stack_enabled=bool(raw.get("stack_enabled", False)),
        tracing_enabled=bool(raw.get("tracing_enabled", False)),
        redact_logs=bool(raw.get("redact_logs", True)),
        log_level=_normalize_level(str(raw.get("log_level", "INFO"))),
    )


def update_observability_settings(
    *,
    stack_enabled: bool | None = None,
    tracing_enabled: bool | None = None,
    redact_logs: bool | None = None,
    log_level: str | None = None,
) -> ObservabilitySettings:
    """
    Aggiorna le impostazioni esistenti con i valori forniti e le persiste su disco.

    Ritorna l'oggetto ObservabilitySettings aggiornato.
    """
    current = load_observability_settings()

    new_settings = ObservabilitySettings(
        stack_enabled=current.stack_enabled if stack_enabled is None else bool(stack_enabled),
        tracing_enabled=current.tracing_enabled if tracing_enabled is None else bool(tracing_enabled),
        redact_logs=current.redact_logs if redact_logs is None else bool(redact_logs),
        log_level=_normalize_level(log_level or current.log_level),
    )

    path = get_observability_config_path()
    path_safe = ensure_within_and_resolve(path.parent, path)
    path_safe.parent.mkdir(parents=True, exist_ok=True)

    data: Dict[str, Any] = {
        "stack_enabled": new_settings.stack_enabled,
        "tracing_enabled": new_settings.tracing_enabled,
        "redact_logs": new_settings.redact_logs,
        "log_level": new_settings.log_level,
    }

    text = yaml.safe_dump(data, sort_keys=True, allow_unicode=True)
    safe_write_text(path_safe, text, encoding="utf-8", atomic=True)

    return new_settings


def get_grafana_url(default: str = "http://localhost:3000/") -> str:
    """
    Ritorna l'URL base di Grafana da usare nei link UI.

    - Se TIMMY_GRAFANA_URL è impostata, usa quel valore.
    - Altrimenti usa il default passato (di solito http://localhost:3000/).
    """
    base = os.getenv(_GRAFANA_URL_ENV, default).strip()
    if not base:
        base = default
    # assicuriamoci di avere la trailing slash
    if not base.endswith("/"):
        base = base + "/"
    return base


def _build_grafana_dashboard_url(uid_env: str, *, slug: Optional[str] = None) -> Optional[str]:
    uid = os.getenv(uid_env)
    if not uid:
        return None
    base = get_grafana_url()
    dashboard = urljoin(base, f"d/{uid}")
    if slug:
        query = urlencode({"var-slug": slug})
        separator = "&" if "?" in dashboard else "?"
        dashboard = f"{dashboard}{separator}{query}"
    return dashboard


def get_grafana_logs_dashboard_url(slug: Optional[str] = None) -> Optional[str]:
    """Restituisce l'URL della dashboard log Grafana (se configurata)."""
    return _build_grafana_dashboard_url(_GRAFANA_LOGS_UID_ENV, slug=slug)


def get_grafana_errors_dashboard_url(slug: Optional[str] = None) -> Optional[str]:
    """Restituisce l'URL della dashboard alert/errori Grafana (se configurata)."""
    return _build_grafana_dashboard_url(_GRAFANA_ERRORS_UID_ENV, slug=slug)
