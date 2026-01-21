# SPDX-License-Identifier: GPL-3.0-or-later
# src/ui/config_store.py
from __future__ import annotations

from pathlib import Path
from typing import Any, TypedDict, cast

import yaml

from pipeline.config_utils import load_client_settings
from pipeline.exceptions import ConfigError
from pipeline.file_utils import safe_write_text
from pipeline.logging_utils import get_structured_logger
from pipeline.path_utils import ensure_within_and_resolve
from pipeline.settings import Settings
from ui.utils.context_cache import get_client_context

try:
    from pipeline.context import ClientContext
except Exception:  # pragma: no cover
    ClientContext = type("ClientContext", (), {})

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
DEFAULT_THROTTLE_PARALLELISM: int = 1
DEFAULT_THROTTLE_SLEEP_MS: int = 0

_logger = get_structured_logger("ui.config_store")


def _coerce_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return default


class RetrieverConfig(TypedDict, total=False):
    candidate_limit: int
    latency_budget_ms: int
    auto_by_budget: bool
    throttle: dict[str, Any]


class GlobalConfig(TypedDict, total=False):
    meta: dict[str, Any]
    ai: dict[str, Any]
    ui: dict[str, Any]
    pipeline: dict[str, Any]
    security: dict[str, Any]
    integrations: dict[str, Any]


def _load_client_config(slug: str) -> tuple[Path, GlobalConfig]:
    """
    Carica il config specifico del cliente, garantendo path-safety.

    Raises:
        ConfigError: se il contesto non è disponibile o il file è illeggibile.
    """
    ctx: Any | None = None
    try:
        if hasattr(ClientContext, "load"):
            try:
                ctx = ClientContext.load(
                    slug=slug,
                    require_env=False,
                )
            except Exception:
                ctx = None
        if ctx is None:
            ctx = get_client_context(slug, require_env=False)
    except Exception as exc:
        raise ConfigError(f"Impossibile caricare il contesto per {slug}: {exc}", slug=slug) from exc

    if ctx.config_path is None:
        raise ConfigError("Config path non disponibile", slug=slug)

    cfg_path = ensure_within_and_resolve(ctx.config_path.parent, ctx.config_path)

    try:
        settings = load_client_settings(ctx, reload=True, logger=_logger)
        if hasattr(settings, "as_dict"):
            return Path(cfg_path), cast(GlobalConfig, settings.as_dict())
        if isinstance(settings, dict):
            return Path(cfg_path), cast(GlobalConfig, settings)
        try:
            raw = dict(vars(settings))
        except Exception as exc:  # noqa: BLE001
            raise ConfigError(
                "Impossibile convertire le settings cliente in dict (as_dict/dict/vars falliti).",
                slug=slug,
                file_path=str(cfg_path),
            ) from exc
        if not raw:
            raise ConfigError(
                "Impossibile convertire le settings cliente in dict (as_dict/dict/vars falliti).",
                slug=slug,
                file_path=str(cfg_path),
            )
        return Path(cfg_path), cast(GlobalConfig, raw)
    except Exception as exc:  # noqa: BLE001
        _logger.error(
            "ui.config_store.client_config_load_failed",
            extra={"slug": slug, "file_path": str(cfg_path), "error": str(exc)},
        )
        raise ConfigError(
            "Config cliente non caricabile: provisioning/config non valida.",
            slug=slug,
            file_path=str(cfg_path),
        ) from exc


def get_config_dir() -> Path:
    return CONFIG_DIR


def get_config_path() -> Path:
    return CONFIG_FILE


def _load_config() -> GlobalConfig:
    """Carica config/config.yaml tramite Settings (SSoT non segreto)."""
    if not CONFIG_FILE.exists():
        raise ConfigError(
            "Config globale mancante: atteso config/config.yaml (provisioning richiesto).",
            file_path=str(CONFIG_FILE),
        )
    try:
        settings = Settings.load(REPO_ROOT, config_path=CONFIG_FILE, logger=_logger)
        if hasattr(settings, "as_dict"):
            return cast(GlobalConfig, settings.as_dict())
        raise AttributeError("settings.as_dict missing")
    except Exception as exc:  # noqa: BLE001
        _logger.error(
            "ui.config_store.global_config_load_failed",
            extra={"error": str(exc), "file_path": str(CONFIG_FILE)},
        )
        raise ConfigError(
            "Impossibile caricare la config globale (config/config.yaml). "
            "Runtime strict: correggi provisioning/config.",
            file_path=str(CONFIG_FILE),
        ) from exc


def _load_repo_config(repo_root: Path) -> GlobalConfig:
    """Carica config/config.yaml per un repo specifico."""
    cfg_dir = _resolve_path(repo_root, repo_root / "config")
    cfg_file = _resolve_path(cfg_dir, cfg_dir / "config.yaml")
    if not cfg_file.exists():
        raise ConfigError(
            "Config repo mancante: atteso config/config.yaml (provisioning richiesto).",
            file_path=str(cfg_file),
        )
    try:
        settings = Settings.load(repo_root, config_path=cfg_file, logger=_logger)
        if hasattr(settings, "as_dict"):
            return cast(GlobalConfig, settings.as_dict())
        raise AttributeError("settings.as_dict missing")
    except Exception as exc:  # noqa: BLE001
        _logger.error(
            "ui.config_store.repo_config_load_failed",
            extra={"error": str(exc), "file_path": str(cfg_file)},
        )
        raise ConfigError(
            "Impossibile caricare la config repo (config/config.yaml). Runtime strict: correggi provisioning/config.",
            file_path=str(cfg_file),
        ) from exc


def _save_repo_config(cfg: GlobalConfig, repo_root: Path) -> None:
    cfg_dir = _resolve_path(repo_root, repo_root / "config")
    cfg_file = _resolve_path(cfg_dir, cfg_dir / "config.yaml")
    cfg_dir.mkdir(parents=True, exist_ok=True)
    payload: str = yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False)
    safe_write_text(cfg_file, payload, encoding="utf-8", atomic=True)


def _save_config(cfg: GlobalConfig) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    payload: str = yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False)
    safe_write_text(CONFIG_FILE, payload, encoding="utf-8", atomic=True)


# ------------------- UI flags (config globale repo) -------------------
def get_vision_model(default: str | None = None) -> str:
    """Restituisce ai.vision.model dal config UI (contratto unico ai.vision.*)."""
    cfg = _load_config()
    ai_section = cfg.get("ai")
    if isinstance(ai_section, dict):
        vision = ai_section.get("vision")
        if isinstance(vision, dict):
            model = vision.get("model")
            if isinstance(model, str) and model.strip():
                return model.strip()
    if default is not None:
        return default
    raise ConfigError("Modello Vision mancante in ai.vision.model", file_path=str(CONFIG_FILE))


def get_skip_preflight(*, repo_root: Path | None = None) -> bool:
    """
    True => la UI può saltare il preflight (modalità dev/ambienti controllati).
    Fonte: config/config.yaml

    Chiave canonica: ui.skip_preflight
    Legacy supportato (OR secco, non "fallback morbidi"): skip_preflight top-level
    """
    root = repo_root or REPO_ROOT
    cfg: GlobalConfig = _load_repo_config(root)

    ui = cfg.get("ui")
    ui_skip = False
    if isinstance(ui, dict):
        ui_skip = bool(ui.get("skip_preflight", False))

    legacy_skip = bool(cfg.get("skip_preflight", False))
    return bool(ui_skip or legacy_skip)


def set_skip_preflight(flag: bool, *, repo_root: Path | None = None) -> None:
    """
    Setter coerente con la chiave canonica: ui.skip_preflight
    """
    root = repo_root or REPO_ROOT
    cfg: GlobalConfig = _load_repo_config(root)
    ui = cfg.get("ui")
    if not isinstance(ui, dict):
        ui = {}
        cfg["ui"] = ui
    ui["skip_preflight"] = bool(flag)
    _save_repo_config(cfg, root)


def get_retriever_settings(slug: str | None = None) -> tuple[int, int, bool]:
    """(limit, budget_ms, auto). Clampa e fornisce default sicuri."""
    cfg: GlobalConfig = _load_config()
    source_cfg: GlobalConfig = cfg

    if slug:
        try:
            _, client_cfg = _load_client_config(slug)
            if client_cfg:
                source_cfg = client_cfg
        except ConfigError as exc:
            _logger.debug(
                "get_retriever_settings.client_fallback",
                exc_info=exc,
                extra={"slug": slug, "error": str(exc)},
            )

    # Atteso: pipeline.retriever.throttle.* + pipeline.retriever.auto_by_budget.
    pipeline_section: Any = source_cfg.get("pipeline") if isinstance(source_cfg, dict) else {}
    section: RetrieverConfig = {}
    if isinstance(pipeline_section, dict):
        raw_section = pipeline_section.get("retriever")
        if isinstance(raw_section, dict):
            section = cast(RetrieverConfig, raw_section)

    throttle = section.get("throttle")
    throttle_section: dict[str, Any] = throttle if isinstance(throttle, dict) else {}

    limit = _coerce_int(
        throttle_section.get("candidate_limit", section.get("candidate_limit")),
        DEFAULT_CANDIDATE_LIMIT,
    )
    budget_ms = _coerce_int(
        throttle_section.get("latency_budget_ms", section.get("latency_budget_ms", section.get("budget_ms"))),
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

    cfg: GlobalConfig = _load_config()
    target_cfg: GlobalConfig = cfg
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

    pipeline_section: dict[str, Any] = {}
    if isinstance(target_cfg.get("pipeline"), dict):
        pipeline_section = cast(dict[str, Any], target_cfg.get("pipeline"))
    section: RetrieverConfig = {}
    if isinstance(pipeline_section.get("retriever"), dict):
        section = cast(RetrieverConfig, pipeline_section.get("retriever"))

    throttle = section.get("throttle")
    throttle_section: dict[str, Any] = throttle if isinstance(throttle, dict) else {}
    throttle_section.setdefault("parallelism", DEFAULT_THROTTLE_PARALLELISM)
    throttle_section.setdefault("sleep_ms_between_calls", DEFAULT_THROTTLE_SLEEP_MS)
    throttle_section["candidate_limit"] = int(limit)
    throttle_section["latency_budget_ms"] = int(budget)
    section["throttle"] = throttle_section
    section["auto_by_budget"] = bool(auto)
    pipeline_section = pipeline_section or {}
    pipeline_section["retriever"] = section
    target_cfg["pipeline"] = pipeline_section

    if target_path is not None:
        payload: str = yaml.safe_dump(target_cfg, allow_unicode=True, sort_keys=False)
        safe_write_text(target_path, payload, encoding="utf-8", atomic=True)
    else:
        _save_config(cfg)
