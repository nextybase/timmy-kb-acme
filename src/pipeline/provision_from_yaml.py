# src/pipeline/provision_from_yaml.py
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Tuple

import yaml

from pipeline.exceptions import ConfigError
from pipeline.path_utils import ensure_within_and_resolve, read_text_safe


@dataclass(frozen=True)
class _Paths:
    base_dir: Path
    docs_dir: Path


def _resolve_paths(ctx_base_dir: str) -> _Paths:
    base = Path(ctx_base_dir)
    docs_dir = ensure_within_and_resolve(base, base / "docs")
    return _Paths(base, docs_dir)


def _load_cartelle_yaml(base_dir: Path, yaml_path: Path) -> Dict[str, Any]:
    resolved = ensure_within_and_resolve(base_dir, yaml_path)
    if not resolved.exists():
        raise ConfigError(f"YAML non trovato: {resolved}")
    try:
        raw_text = read_text_safe(base_dir, resolved)
        data = yaml.safe_load(raw_text)
    except Exception as e:
        raise ConfigError(f"Impossibile leggere/parsing YAML: {resolved}") from e
    if not isinstance(data, dict):
        raise ConfigError("YAML invalido: root non è un oggetto.")
    return data


def _validate_payload(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    if "version" not in data:
        raise ConfigError("YAML invalido: manca `version`.")
    folders = data.get("folders")
    if not isinstance(folders, list) or not folders:
        raise ConfigError("YAML invalido: `folders` deve essere una lista non vuota.")
    norm: List[Dict[str, Any]] = []
    for i, item in enumerate(folders):
        if not isinstance(item, dict):
            raise ConfigError(f"YAML invalido: folders[{i}] non è un oggetto.")
        key = (item.get("key") or "").strip()
        title = (item.get("title") or "").strip()
        if not key or not title:
            raise ConfigError(f"YAML invalido: folders[{i}] richiede `key` e `title` non vuoti.")
        norm.append({"key": key, "title": title})
    return norm


def _create_directory(docs_dir: Path, key: str) -> Tuple[bool, Path]:
    # Crea docs/<key> in modo idempotente, con path-safety
    target = ensure_within_and_resolve(docs_dir, docs_dir / key)
    existed_before = target.exists()
    target.mkdir(parents=True, exist_ok=True)
    return (not existed_before), target


def provision_directories_from_cartelle_raw(
    ctx,
    logger,
    *,
    slug: str,
    yaml_path: Path,
) -> Dict[str, Any]:
    """
    Crea la struttura di directory sotto output/timmy-kb-<slug>/docs/<key> in base a cartelle_raw.yaml.
    - Valida YAML (minimo): `version`, `folders: [{key,title}]`
    - Usa ensure_within_and_resolve per path-safety
    - Idempotente: directory già esistenti vanno in `skipped`
    Ritorna: {"created": [paths], "skipped": [paths]}
    """
    paths = _resolve_paths(ctx.base_dir)
    paths.docs_dir.mkdir(parents=True, exist_ok=True)

    data = _load_cartelle_yaml(paths.base_dir, yaml_path)
    folders = _validate_payload(data)

    created: List[str] = []
    skipped: List[str] = []

    seen_keys: set[str] = set()
    for item in folders:
        key = item["key"]
        if key in seen_keys:
            # Duplicato nel YAML: segnala come skipped senza toccare FS
            dup_path = str(ensure_within_and_resolve(paths.docs_dir, paths.docs_dir / key))
            skipped.append(dup_path)
            continue
        seen_keys.add(key)

        did_create, dir_path = _create_directory(paths.docs_dir, key)
        (created if did_create else skipped).append(str(dir_path))

    logger.info(
        "provision_from_yaml: done",
        extra={"slug": slug, "yaml": str(yaml_path), "created": len(created), "skipped": len(skipped)},
    )
    return {"created": created, "skipped": skipped}
