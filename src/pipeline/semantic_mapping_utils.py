# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from pathlib import Path
from typing import List

import yaml

from pipeline.exceptions import ConfigError
from pipeline.path_utils import ensure_within_and_resolve, read_text_safe, to_kebab

_RESERVED = {
    "context",
    "taxonomy",
    "synonyms",
    "canonical",
    "rules",
    "meta",
    "defaults",
    "settings",
    "about",
    "note",
    "system_folders",
    "metadata_policy",
}


def raw_categories_from_semantic_mapping(*, semantic_dir: Path, mapping_path: Path) -> List[str]:
    """Deriva l'elenco delle sottocartelle raw/ direttamente da semantic_mapping.yaml.

    Supporta:
    - formato Vision: mapping["areas"] = [ {...} ... ]
    - fallback interno (senza file legacy): top-level dict keys non riservate

    Ritorna una lista kebab-case, ordinata e senza duplicati.
    """
    safe_mapping = ensure_within_and_resolve(semantic_dir, mapping_path)
    if not Path(safe_mapping).exists():
        raise ConfigError(f"semantic_mapping.yaml mancante: {safe_mapping}")

    raw = read_text_safe(semantic_dir, safe_mapping, encoding="utf-8")
    data = yaml.safe_load(raw) or {}
    if not isinstance(data, dict):
        raise ConfigError("semantic_mapping.yaml non valido: root deve essere una mappa YAML.")

    names: List[str] = []

    areas = data.get("areas")
    if isinstance(areas, list) and areas:
        for a in areas:
            if not isinstance(a, dict):
                continue
            key_raw = a.get("key") or a.get("ambito") or a.get("title") or ""
            k = to_kebab(str(key_raw))
            if k:
                names.append(k)
    else:
        # fallback "shape-based" (non crea file, non usa cartelle_raw.yaml)
        for k, v in data.items():
            if k in _RESERVED:
                continue
            if isinstance(v, dict):
                kk = to_kebab(str(k))
                if kk:
                    names.append(kk)

    # determinismo
    return sorted(set(names))
