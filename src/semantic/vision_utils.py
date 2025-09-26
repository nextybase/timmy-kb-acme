from __future__ import annotations

from typing import Any, Dict, List

import yaml

from pipeline.exceptions import ConfigError


def json_to_cartelle_raw_yaml(data: Dict[str, Any], slug: str) -> str:
    """Converte il payload Vision in YAML per cartelle_raw.yaml."""
    if not isinstance(data, dict):
        raise ConfigError("Vision data: atteso un oggetto JSON.")

    areas = data.get("areas")
    if not isinstance(areas, list):
        raise ConfigError("Vision data: 'areas' deve essere una lista.")

    folders: List[Dict[str, Any]] = []
    for idx, area in enumerate(areas):
        if not isinstance(area, dict):
            raise ConfigError(f"Vision data: area #{idx} non e un oggetto JSON.")
        key = area.get("key")
        if not isinstance(key, str) or not key:
            raise ConfigError(f"Vision data: area #{idx} priva di chiave valida.")
        ambito = area.get("ambito")
        descrizione = area.get("descrizione")
        esempi = area.get("esempio")
        folders.append(
            {
                "key": key,
                "title": ambito if isinstance(ambito, str) and ambito else key,
                "description": descrizione if isinstance(descrizione, str) else "",
                "examples": list(esempi) if isinstance(esempi, list) else [],
            }
        )

    payload = {
        "version": 1,
        "source": "vision",
        "context": {"slug": slug},
        "folders": folders,
    }

    return yaml.safe_dump(payload, allow_unicode=True, sort_keys=False, width=100)
