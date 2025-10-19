# SPDX-License-Identifier: GPL-3.0-or-later
# src/ui/config_store.py
from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import yaml

from pipeline.file_utils import safe_write_text
from pipeline.path_utils import ensure_within_and_resolve, read_text_safe

# Base sicura ancorata al repo
REPO_ROOT: Path = Path(__file__).resolve().parents[2]


def _resolve_path(base: Path, target: Path) -> Path:
    """Path-safety: garantisce che target resti entro base."""
    return cast(Path, ensure_within_and_resolve(base, target))


# Posizioni config (SSoT)
CONFIG_DIR: Path = _resolve_path(REPO_ROOT, REPO_ROOT / "config")
CONFIG_FILE: Path = _resolve_path(CONFIG_DIR, CONFIG_DIR / "config.yaml")

# Limiti retriever (SSoT)
MIN_CANDIDATE_LIMIT: int = 500
MAX_CANDIDATE_LIMIT: int = 20_000
DEFAULT_CANDIDATE_LIMIT: int = 4_000


def get_config_dir() -> Path:
    return CONFIG_DIR


def get_config_path() -> Path:
    return CONFIG_FILE


def get_vision_model(default: str = "gpt-4o-mini-2024-07-18") -> str:
    """Restituisce vision.model dal config UI (fallback sul default)."""
    cfg = _load_config()
    vision = cfg.get("vision")
    if isinstance(vision, dict):
        model = vision.get("model")
        if isinstance(model, str) and model.strip():
            return model.strip()
    return default


def _load_config() -> dict[str, Any]:
    """Carica config.yaml; se assente o malformato, ritorna {}."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if not CONFIG_FILE.exists():
        safe_write_text(CONFIG_FILE, "{}\n", encoding="utf-8", atomic=True)
        return {}
    try:
        text: str = read_text_safe(CONFIG_DIR, CONFIG_FILE, encoding="utf-8")
    except Exception:
        return {}
    try:
        data = yaml.safe_load(text) or {}
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}
    return cast(dict[str, Any], data)


def _save_config(cfg: dict[str, Any]) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    payload: str = yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False)
    safe_write_text(CONFIG_FILE, payload, encoding="utf-8", atomic=True)


# ------------------- UI flags (config globale repo) -------------------
def get_skip_preflight() -> bool:
    """
    Flag persistente per saltare il preflight (config/config.yaml -> ui.skip_preflight).
    """
    cfg: dict[str, Any] = _load_config()
    ui_section: Any = cfg.get("ui")
    if isinstance(ui_section, dict):
        try:
            return bool(ui_section.get("skip_preflight", False))
        except Exception:
            return False
    try:
        return bool(cfg.get("skip_preflight", False))
    except Exception:
        return False


def set_skip_preflight(flag: bool) -> None:
    """
    Aggiorna ui.skip_preflight persistendo la configurazione in modo atomico.
    """
    cfg: dict[str, Any] = _load_config()
    ui_section: Any = cfg.get("ui")
    if not isinstance(ui_section, dict):
        ui_section = {}
    ui_section["skip_preflight"] = bool(flag)
    cfg["ui"] = ui_section
    _save_config(cfg)


def get_retriever_settings() -> tuple[int, int, bool]:
    """(limit, budget_ms, auto). Clampa e fornisce default sicuri."""
    cfg: dict[str, Any] = _load_config()

    raw_section: Any = cfg.get("retriever")
    if isinstance(raw_section, dict):
        section: dict[str, Any] = cast(dict[str, Any], raw_section)
    else:
        section = {}

    limit: int = int(section.get("candidate_limit", DEFAULT_CANDIDATE_LIMIT))
    budget_ms: int = int(section.get("budget_ms", 300))
    auto: bool = bool(section.get("auto", False))

    # Clamp
    if limit < MIN_CANDIDATE_LIMIT:
        limit = MIN_CANDIDATE_LIMIT
    if limit > MAX_CANDIDATE_LIMIT:
        limit = MAX_CANDIDATE_LIMIT
    if budget_ms < 0:
        budget_ms = 0
    if budget_ms > 2000:
        budget_ms = 2000

    return limit, budget_ms, auto


def set_retriever_settings(candidate_limit: int, budget_ms: int, auto: bool) -> None:
    """Persistenza atomica delle impostazioni retriever."""
    # Clamp in ingresso
    limit = max(MIN_CANDIDATE_LIMIT, min(MAX_CANDIDATE_LIMIT, int(candidate_limit)))
    budget = max(0, min(2000, int(budget_ms)))

    cfg: dict[str, Any] = _load_config()

    raw_section: Any = cfg.get("retriever")
    if isinstance(raw_section, dict):
        section: dict[str, Any] = cast(dict[str, Any], raw_section)
    else:
        section = {}

    section["candidate_limit"] = int(limit)
    section["budget_ms"] = int(budget)
    section["auto"] = bool(auto)
    cfg["retriever"] = section

    _save_config(cfg)
