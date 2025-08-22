# -*- coding: utf-8 -*-
from __future__ import annotations
import json
import re
import time
from pathlib import Path
from typing import Dict

try:
    import yaml  # PyYAML
except Exception:
    yaml = None

_INVALID_CHARS_RE = re.compile(r'[\/\\:\*\?"<>\|]')

def load_yaml(path: Path) -> Dict:
    if yaml is None:
        raise RuntimeError("PyYAML non disponibile: installa 'pyyaml'.")
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}

def validate_tags_reviewed(data: dict) -> dict:
    errors, warnings = [], []

    if not isinstance(data, dict):
        errors.append("Il file YAML non è una mappa (dict) alla radice.")
        return {"errors": errors, "warnings": warnings}

    for k in ("version", "reviewed_at", "keep_only_listed", "tags"):
        if k not in data:
            errors.append(f"Campo mancante: '{k}'.")

    if "tags" in data and not isinstance(data["tags"], list):
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
    report_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "validated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        **result,
    }
    report_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("Report validazione scritto", extra={"file_path": str(report_path)})
