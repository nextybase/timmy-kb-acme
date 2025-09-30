# src/ui/utils/core.py
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, cast

from pipeline.path_utils import ensure_within_and_resolve as _ensure_within_and_resolve
from pipeline.path_utils import to_kebab as _to_kebab


def to_kebab(s: str) -> str:
    # Cast conservativo: l'helper di pipeline ritorna str in pratica
    return str(_to_kebab(s))


def ensure_within_and_resolve(root: Path | str, target: Path | str) -> Path:
    """Wrapper compatibile che delega alla SSoT `pipeline.path_utils.ensure_within_and_resolve`.

    Effettua solo il cast `Path|str` -> `Path` e delega, mantenendo la firma pubblica.
    """
    return cast(Path, _ensure_within_and_resolve(Path(root), Path(target)))


def yaml_load(path: Path) -> Dict[str, Any]:
    # Centralizza su utility pipeline, mantenendo la stessa firma
    from pipeline.yaml_utils import yaml_read

    p = Path(path)
    data = yaml_read(p.parent, p)
    if not isinstance(data, dict):
        return {}
    return cast(Dict[str, Any], data)


def yaml_dump(data: Dict[str, Any]) -> str:
    import yaml

    return yaml.safe_dump(data or {}, allow_unicode=True, sort_keys=True)
