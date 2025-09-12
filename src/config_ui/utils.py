# src/config_ui/utils.py
from __future__ import annotations

from pathlib import Path
from typing import Dict, Any

from pipeline.path_utils import (
    ensure_within,
    to_kebab as _to_kebab,
    ensure_within_and_resolve as _ensure_within_and_resolve,
)
from pipeline.file_utils import safe_write_text


def to_kebab(s: str) -> str:
    # Cast conservativo: l'helper di pipeline ritorna str in pratica
    return str(_to_kebab(s))


def ensure_within_and_resolve(root: Path | str, target: Path | str) -> Path:
    """Wrapper compatibile che delega alla SSoT `pipeline.path_utils.ensure_within_and_resolve`.

    Effettua solo il cast `Path|str` -> `Path` e delega, mantenendo la firma pubblica.
    """
    return _ensure_within_and_resolve(Path(root), Path(target))


def safe_write_text_compat(path: Path | str, content: str, *, encoding: str = "utf-8") -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    safe_write_text(p, content, encoding=encoding, atomic=True)


def yaml_load(path: Path) -> Dict[str, Any]:
    # Centralizza su utility pipeline, mantenendo la stessa firma
    from pipeline.yaml_utils import yaml_read

    p = Path(path)
    return yaml_read(p.parent, p) or {}


def yaml_dump(data: Dict[str, Any]) -> str:
    import yaml

    return yaml.safe_dump(data or {}, allow_unicode=True, sort_keys=True)
