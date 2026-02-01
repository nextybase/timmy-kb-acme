# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from pathlib import Path
from typing import List

import yaml

from pipeline.exceptions import ConfigError
from pipeline.path_utils import ensure_within_and_resolve, read_text_safe, to_kebab_strict
from pipeline.semantic_mapping_validation import validate_area_dict, validate_area_key, validate_areas_list

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

# Campo canonico per derivare i nomi cartella raw/ dalle aree Vision.
_AREA_NAME_FIELD = "key"


def raw_categories_from_semantic_mapping(*, semantic_dir: Path, mapping_path: Path) -> List[str]:
    """Deriva l'elenco delle sottocartelle raw/ direttamente da semantic_mapping.yaml.

    Supporta:
    - formato Vision: mapping["areas"] = [ {...} ... ]

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

    areas = validate_areas_list(
        data.get("areas"),
        error_message="semantic_mapping.yaml non conforme: 'areas' mancante o vuoto.",
        min_len=1,
    )

    for idx, area in enumerate(areas):
        area_dict = validate_area_dict(
            area,
            error_message=f"semantic_mapping.yaml non conforme: areas[{idx}] deve essere un oggetto.",
        )
        raw_name = validate_area_key(
            area_dict,
            key_field=_AREA_NAME_FIELD,
            error_message=f"semantic_mapping.yaml non conforme: areas[{idx}] manca del campo '{_AREA_NAME_FIELD}'.",
        )
        names.append(
            to_kebab_strict(
                raw_name,
                context=f"semantic_mapping.areas[{idx}].{_AREA_NAME_FIELD}",
            )
        )

    # determinismo
    return sorted(set(names))
