# SPDX-License-Identifier: GPL-3.0-or-later
# src/ui/config_store.py
from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import yaml

from pipeline.context import ClientContext
from pipeline.exceptions import ConfigError
from pipeline.file_utils import safe_write_text
from pipeline.logging_utils import get_structured_logger
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
DEFAULT_LATENCY_BUDGET_MS: int = 0

_logger = get_structured_logger("ui.config_store")


def _coerce_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _load_client_config(slug: str) -> tuple[Path, dict[str, Any]]:
    """
    Carica il config specifico del cliente, garantendo path-safety.

    Raises:
        ConfigError: se il contesto non è disponibile o il file è illeggibile.
    """
    try:
        ctx = ClientContext.load(slug=slug, interactive=False, require_env=False, run_id=None)
    except Exception as exc:
        raise ConfigError(f"Impossibile caricare il contesto per {slug}: {exc}", slug=slug) from exc

    if ctx.config_path is None:
        raise ConfigError("Config path non disponibile", slug=slug)

    cfg_path = ensure_within_and_resolve(ctx.config_path.parent, ctx.config_path)

    try:
        text = read_text_safe(cfg_path.parent, cfg_path, encoding="utf-8")
        data = yaml.safe_load(text) or {}
    except Exception as exc:
        raise ConfigError(f"Config cliente non leggibile: {exc}", slug=slug, file_path=str(cfg_path)) from exc

    if not isinstance(data, dict):
        data = {}

    return Path(cfg_path), cast(dict[str, Any], data)


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


def get_retriever_settings(slug: str | None = None) -> tuple[int, int, bool]:
    """(limit, budget_ms, auto). Clampa e fornisce default sicuri."""
    cfg: dict[str, Any] = _load_config()

    source_cfg: dict[str, Any] = cfg

    if slug:
        try:
            _, client_cfg = _load_client_config(slug)
            if client_cfg:
                source_cfg = client_cfg
        except ConfigError as exc:
            _logger.debug("get_retriever_settings.client_fallback", exc_info=exc)

    raw_section: Any = source_cfg.get("retriever")
    if isinstance(raw_section, dict):
        section: dict[str, Any] = cast(dict[str, Any], raw_section)
    else:
        section = {}

    limit = _coerce_int(section.get("candidate_limit"), DEFAULT_CANDIDATE_LIMIT)
    budget_ms = _coerce_int(
        section.get("latency_budget_ms", section.get("budget_ms")),
        DEFAULT_LATENCY_BUDGET_MS,
    )
    auto = bool(section.get("auto_by_budget", section.get("auto", False)))

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


def set_retriever_settings(
    candidate_limit: int,
    budget_ms: int,
    auto: bool,
    *,
    slug: str | None = None,
) -> None:
    """Persistenza atomica delle impostazioni retriever."""
    # Clamp in ingresso
    limit = max(MIN_CANDIDATE_LIMIT, min(MAX_CANDIDATE_LIMIT, int(candidate_limit)))
    budget = max(0, min(2000, int(budget_ms)))

    cfg: dict[str, Any] = _load_config()
    target_cfg = cfg
    target_path: Path | None = None

    if slug:
        try:
            target_path, target_cfg = _load_client_config(slug)
        except ConfigError as exc:
            _logger.warning(
                "set_retriever_settings.client_fallback",
                extra={"slug": slug, "error": str(exc)},
            )
            target_cfg = cfg

    raw_section: Any = target_cfg.get("retriever")
    if isinstance(raw_section, dict):
        section: dict[str, Any] = cast(dict[str, Any], raw_section)
    else:
        section = {}

    section["candidate_limit"] = int(limit)
    section["latency_budget_ms"] = int(budget)
    section["budget_ms"] = int(budget)  # fallback legacy
    section["auto_by_budget"] = bool(auto)
    section["auto"] = bool(auto)  # fallback legacy
    target_cfg["retriever"] = section

    if target_path is not None:
        payload: str = yaml.safe_dump(target_cfg, allow_unicode=True, sort_keys=False)
        safe_write_text(target_path, payload, encoding="utf-8", atomic=True)
    else:
        _save_config(cfg)
