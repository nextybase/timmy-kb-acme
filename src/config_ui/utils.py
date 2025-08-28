# src/config_ui/utils.py
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Dict, Any

# Import compatibili dal repo
try:
    from pipeline.path_utils import ensure_within as _repo_ensure_within  # type: ignore
except Exception:
    _repo_ensure_within = None  # type: ignore

try:
    from pipeline.file_utils import safe_write_text as _repo_safe_write_text  # type: ignore
except Exception:
    _repo_safe_write_text = None  # type: ignore


# ========= Normalizzazione chiavi (SSoT) =========
def to_kebab(s: str) -> str:
    """
    Normalizza una stringa in kebab-case tollerante:
    - strip + lower
    - converte spazi/underscore in '-'
    - riduce multipli '-'
    - elimina caratteri non [a-z0-9-]
    Questa è la funzione CANONICA da riusare in tutta la codebase.
    """
    s = (s or "").strip().lower().replace("_", "-").replace(" ", "-")
    s = re.sub(r"[^a-z0-9-]+", "-", s)
    s = re.sub(r"-{2,}", "-", s).strip("-")
    return s


def ensure_within_and_resolve(root: Path | str, target: Path | str) -> Path:
    """
    Verifica che `target` sia sotto `root` (path-safety) e ritorna Path (non forzatamente risolto).
    Se il repo espone pipeline.path_utils.ensure_within, la utilizza.
    """
    root_p = Path(root)
    tgt_p = Path(target)
    if _repo_ensure_within is not None:
        _repo_ensure_within(root_p, tgt_p)  # valida
        return tgt_p
    rr = root_p.resolve()
    tr = tgt_p.resolve()
    if rr not in tr.parents and tr != rr:
        raise ValueError(f"Path fuori root: {tr} !⊂ {rr}")
    return tgt_p


def safe_write_text_compat(path: Path | str, content: str, *, encoding: str = "utf-8") -> None:
    """
    Scrittura atomica (fallback) oppure delega a pipeline.file_utils.safe_write_text.
    """
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    if _repo_safe_write_text is not None:
        try:
            _repo_safe_write_text(str(p), content, encoding=encoding)  # type: ignore
            return
        except TypeError:
            try:
                _repo_safe_write_text(str(p), content)  # type: ignore
                return
            except Exception:
                pass
    tmp = p.with_suffix(p.suffix + ".tmp")
    with open(tmp, "w", encoding=encoding) as f:
        f.write(content)
    os.replace(tmp, p)


def yaml_load(path: Path) -> Dict[str, Any]:
    import yaml
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def yaml_dump(data: Dict[str, Any]) -> str:
    import yaml
    # Ordine deterministico per stabilità Git
    return yaml.safe_dump(data or {}, allow_unicode=True, sort_keys=True)
