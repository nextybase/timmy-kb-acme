# src/ui/config_store.py
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Tuple

from pipeline.file_utils import safe_write_text
from pipeline.path_utils import ensure_within_and_resolve, read_text_safe

# Root del repo (…/src/ui/config_store.py → repo)
REPO_ROOT: Path = Path(__file__).resolve().parents[2]

# ----------------------------- Limiti retriever (SSoT) -----------------------------
MIN_CANDIDATE_LIMIT: int = 500
MAX_CANDIDATE_LIMIT: int = 20_000
DEFAULT_CANDIDATE_LIMIT: int = 4_000

try:
    # Se presenti, prendi i valori dal retriever
    from retriever import DEFAULT_CANDIDATE_LIMIT as _DEF
    from retriever import MAX_CANDIDATE_LIMIT as _MAX
    from retriever import MIN_CANDIDATE_LIMIT as _MIN

    MIN_CANDIDATE_LIMIT = int(_MIN)
    MAX_CANDIDATE_LIMIT = int(_MAX)
    DEFAULT_CANDIDATE_LIMIT = int(_DEF)
except Exception:
    try:
        from retriever import MAX_CANDIDATE_LIMIT as _MAX2
        from retriever import MIN_CANDIDATE_LIMIT as _MIN2
        from retriever import _default_candidate_limit as _def_fn

        MIN_CANDIDATE_LIMIT = int(_MIN2)
        MAX_CANDIDATE_LIMIT = int(_MAX2)
        DEFAULT_CANDIDATE_LIMIT = int(_def_fn())
    except Exception:
        # Fallback già impostati
        pass


# ----------------------------- Path sicuri per config UI -----------------------------
def _resolve_cfg_dir() -> Path:
    raw = Path(os.getenv("UI_CONFIG_DIR", str(REPO_ROOT / "data" / "ui")))
    # Ancoraggio e validazione in perimetro repo
    anchored = REPO_ROOT / raw if not raw.is_absolute() else raw
    return ensure_within_and_resolve(REPO_ROOT, anchored)


def _resolve_cfg_file() -> Path:
    env = os.getenv("UI_CONFIG_FILE")
    if env:
        raw = Path(env)
    else:
        raw = _resolve_cfg_dir() / "config.yaml"
    anchored = REPO_ROOT / raw if not raw.is_absolute() else raw
    return ensure_within_and_resolve(REPO_ROOT, anchored)


CFG_FILE: Path = _resolve_cfg_file()


def _ensure_cfg_file() -> Path:
    p = CFG_FILE
    p.parent.mkdir(parents=True, exist_ok=True)
    if not p.exists():
        safe_write_text(p, "{}", encoding="utf-8", atomic=True)
    return p


# ----------------------------- Modello e I/O -----------------------------
@dataclass
class RetrieverSettings:
    limit: int = DEFAULT_CANDIDATE_LIMIT
    budget_ms: int = 300
    auto: bool = False


def _load_cfg() -> dict:
    """Carica YAML come dict in modo *safe* (path-safe + atomic-friendly)."""
    _ensure_cfg_file()
    try:
        txt = read_text_safe(REPO_ROOT, CFG_FILE, encoding="utf-8")
    except Exception:
        return {}
    try:
        import yaml
    except Exception:
        return {}
    try:
        data = yaml.safe_load(txt) or {}
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_cfg(cfg: dict) -> None:
    """Scrive YAML in modo atomico e path-safe."""
    try:
        import yaml
    except Exception:
        # Fallback minimale
        safe_write_text(ensure_within_and_resolve(REPO_ROOT, CFG_FILE), "{}", encoding="utf-8", atomic=True)
        return
    txt = yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False)
    safe_write_text(ensure_within_and_resolve(REPO_ROOT, CFG_FILE), txt, encoding="utf-8", atomic=True)


# ----------------------------- API pubblica -----------------------------
def get_retriever_settings() -> Tuple[int, int, bool]:
    """Restituisce (limit, budget_ms, auto) con clamp ai limiti SSoT."""
    cfg = _load_cfg()
    node = cfg.get("retriever") if isinstance(cfg, dict) else {}
    if not isinstance(node, dict):
        node = {}
    limit = int(node.get("limit", DEFAULT_CANDIDATE_LIMIT))
    budget_ms = int(node.get("budget_ms", 300))
    auto = bool(node.get("auto", False))

    # Clamp ai limiti SSoT
    limit = max(MIN_CANDIDATE_LIMIT, min(MAX_CANDIDATE_LIMIT, limit))
    budget_ms = max(0, min(2000, budget_ms))
    return limit, budget_ms, auto


def set_retriever_settings(limit: int, budget_ms: int, auto: bool) -> None:
    """Aggiorna i settaggi retriever (persistenza YAML atomica)."""
    cfg = _load_cfg()
    if not isinstance(cfg, dict):
        cfg = {}
    cfg.setdefault("retriever", {})
    node = cfg["retriever"]
    if not isinstance(node, dict):
        node = {}
        cfg["retriever"] = node

    node["limit"] = int(max(MIN_CANDIDATE_LIMIT, min(MAX_CANDIDATE_LIMIT, limit)))
    node["budget_ms"] = int(max(0, min(2000, budget_ms)))
    node["auto"] = bool(auto)
    _save_cfg(cfg)
