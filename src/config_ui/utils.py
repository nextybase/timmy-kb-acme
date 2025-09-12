# src/config_ui/utils.py
from __future__ import annotations

from pathlib import Path
from typing import Dict, Any

from pipeline.path_utils import ensure_within, to_kebab as _to_kebab
from pipeline.file_utils import safe_write_text


def to_kebab(s: str) -> str:
    # Cast conservativo: l'helper di pipeline ritorna str in pratica
    return str(_to_kebab(s))


def ensure_within_and_resolve(root: Path | str, target: Path | str) -> Path:
    """Valida che `target` ricada sotto `root` e ritorna il path risolto.

    Usa `ensure_within` (SSoT) per la guardia STRONG e restituisce `Path.resolve()`
    del target per coerenza con il nome della funzione.
    """
    root_p = Path(root)
    tgt_p = Path(target)
    ensure_within(root_p, tgt_p)
    return tgt_p.resolve()


def safe_write_text_compat(path: Path | str, content: str, *, encoding: str = "utf-8") -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    safe_write_text(p, content, encoding=encoding, atomic=True)


def yaml_load(path: Path) -> Dict[str, Any]:
    import yaml

    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def yaml_dump(data: Dict[str, Any]) -> str:
    import yaml

    return yaml.safe_dump(data or {}, allow_unicode=True, sort_keys=True)
