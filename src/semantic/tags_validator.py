# SPDX-License-Identifier: GPL-3.0-or-later
# src/semantic/tags_validator.py
# -*- coding: utf-8 -*-
from __future__ import annotations

"""
Validatore per `tags_reviewed.yaml` – Timmy-KB

Cosa fa il modulo
-----------------
- `load_yaml(path) -> dict`
  Carica in modo sicuro un file YAML e restituisce un dict ({} se vuoto). Solleva
  `ConfigError` se PyYAML non è disponibile, il file non esiste o il parsing fallisce.

- `validate_tags_reviewed(data: dict) -> dict`
  Valida la struttura logica di `tags_reviewed.yaml` (campi obbligatori, tipi,
  vincoli su nomi/tag/azioni). Ritorna un dizionario con `errors`, `warnings`
  e `count`.

- `write_validation_report(report_path, result, logger) -> None`
  Scrive in modo **atomico** il report JSON della validazione a `report_path`,
  applicando guard-rail **STRONG** con `ensure_within` e propagando un
  `ConfigError` in caso di I/O o path non sicuro.

Sicurezza & I/O
---------------
- Nessuna interazione utente (niente `print()`/`input()`).
- Path-safety: `ensure_within` prima di scritture su disco.
- Scritture atomiche con `safe_write_text`.
"""

import json
import re
import time
from pathlib import Path
from typing import Dict, Any

from pipeline.exceptions import ConfigError
from pipeline.file_utils import safe_write_text
from pipeline.path_utils import ensure_within

try:
    import yaml  # PyYAML
except Exception:  # pragma: no cover
    yaml = None

__all__ = ["load_yaml", "validate_tags_reviewed", "write_validation_report"]

_INVALID_CHARS_RE = re.compile(r'[\/\\:\*\?"<>\|]')


def load_yaml(path: Path) -> Dict[str, Any]:
    """
    Carica un file YAML e restituisce un dict ({} su file vuoto).

    Solleva:
        ConfigError: se PyYAML non è disponibile, se il file non esiste
                     o se il parsing fallisce.
    """
    if yaml is None:
        raise ConfigError("PyYAML non disponibile: installa 'pyyaml'.", file_path=str(path))
    path = Path(path).resolve()
    if not path.exists():
        raise ConfigError("File YAML non trovato.", file_path=str(path))
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return data if isinstance(data, dict) else {}
    except Exception as e:
        raise ConfigError(f"Impossibile leggere/parsing YAML: {e}", file_path=str(path)) from e


def validate_tags_reviewed(data: dict) -> dict:
    """
    Valida la struttura di `tags_reviewed.yaml`.

    Ritorna:
        dict con chiavi: errors (list[str]), warnings (list[str]), count (int, opzionale)
    """
    errors, warnings = [], []

    if not isinstance(data, dict):
        errors.append("Il file YAML non è una mappa (dict) alla radice.")
        return {"errors": errors, "warnings": warnings}

    for k in ("version", "reviewed_at", "keep_only_listed", "tags"):
        if k not in data:
            errors.append(f"Campo mancante: '{k}'.")

    if "tags" in data and not isinstance(data.get("tags"), list):
        errors.append("Il campo 'tags' deve essere una lista.")

    if errors:
        return {"errors": errors, "warnings": warnings}

    names_seen_ci = set()
    for idx, item in enumerate(data.get("tags", []), start=1):
        ctx = f"tags[{idx}]"
        if not isinstance(item, dict):
            errors.append(f"{ctx}: elemento non è dict.")
            continue

        name = item.get("name")
        if not isinstance(name, str) or not name.strip():
            errors.append(f"{ctx}: 'name' mancante o vuoto.")
            continue
        name_stripped = name.strip()
        if len(name_stripped) > 80:
            warnings.append(f"{ctx}: 'name' troppo lungo (>80).")
        if _INVALID_CHARS_RE.search(name_stripped):
            errors.append(f"{ctx}: 'name' contiene caratteri non permessi (/ \\ : * ? \" < > |).")

        name_ci = name_stripped.lower()
        if name_ci in names_seen_ci:
            errors.append(f"{ctx}: 'name' duplicato (case-insensitive): '{name_stripped}'.")
        names_seen_ci.add(name_ci)

        action = item.get("action")
        if not isinstance(action, str) or not action:
            errors.append(f"{ctx}: 'action' mancante.")
        else:
            act = action.strip().lower()
            if act not in ("keep", "drop") and not act.startswith("merge_into:"):
                errors.append(f"{ctx}: 'action' non valida: '{action}'. Usa keep|drop|merge_into:<canonical>.")
            if act.startswith("merge_into:"):
                target = act.split(":", 1)[1].strip()
                if not target:
                    errors.append(f"{ctx}: merge_into senza target.")

        syn = item.get("synonyms", [])
        if syn is not None and not isinstance(syn, list):
            errors.append(f"{ctx}: 'synonyms' deve essere lista di stringhe.")
        else:
            for si, s in enumerate(syn or [], start=1):
                if not isinstance(s, str) or not s.strip():
                    errors.append(f"{ctx}: synonyms[{si}] non è stringa valida.")

        notes = item.get("notes", "")
        if notes is not None and not isinstance(notes, str):
            errors.append(f"{ctx}: 'notes' deve essere una stringa.")

    if data.get("keep_only_listed") and not data.get("tags"):
        warnings.append("keep_only_listed=True ma la lista 'tags' è vuota.")

    return {"errors": errors, "warnings": warnings, "count": len(data.get("tags", []))}


def write_validation_report(report_path: Path, result: dict, logger) -> None:
    """
    Scrive il report JSON della validazione in modo atomico con path-safety.

    Solleva:
        ConfigError: su problemi di path-safety o I/O bloccanti.
    """
    report_path = Path(report_path).resolve()
    # Path-safety forte: il file deve stare sotto la sua directory (anti path traversal)
    try:
        ensure_within(report_path.parent, report_path)
        report_path.parent.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        raise ConfigError(f"Percorso output non sicuro: {report_path} ({e})", file_path=str(report_path)) from e

    payload = {
        "validated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        **(result or {}),
    }
    try:
        safe_write_text(report_path, json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8", atomic=True)
    except Exception as e:
        raise ConfigError(f"Errore scrittura report: {e}", file_path=str(report_path)) from e

    logger.info("Report validazione scritto", extra={"file_path": str(report_path)})
