# src/ui/utils/core.py
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, cast

from pipeline.file_utils import safe_write_text as _safe_write_text
from pipeline.path_utils import ensure_within_and_resolve as _ensure_within_and_resolve
from pipeline.path_utils import to_kebab as _to_kebab


def to_kebab(s: str) -> str:
    """Converte una stringa in kebab-case usando lâ€™utility SSoT di pipeline."""
    return str(_to_kebab(s))


def ensure_within_and_resolve(root: Path | str, target: Path | str) -> Path:
    """Wrapper SSoT per `pipeline.path_utils.ensure_within_and_resolve`.

    Esegue solo il cast `Path|str` â†’ `Path` e delega al backend, mantenendo la firma pubblica.
    """
    return cast(Path, _ensure_within_and_resolve(Path(root), Path(target)))


def yaml_load(path: Path) -> Dict[str, Any]:
    """Legge YAML dal disco tramite le utility centralizzate di pipeline."""
    from pipeline.yaml_utils import yaml_read

    p = Path(path)
    data = yaml_read(p.parent, p)
    if not isinstance(data, dict):
        return {}
    return cast(Dict[str, Any], data)


def yaml_dump(data: Dict[str, Any]) -> str:
    """Serializza un dict in YAML con ordinamento chiavi stabile."""
    import yaml

    return yaml.safe_dump(data or {}, allow_unicode=True, sort_keys=True)


def safe_write_text(
    path: Path | str,
    data: str,
    *,
    encoding: str = "utf-8",
    atomic: bool = True,
    fsync: bool = False,
) -> None:
    """Scrive testo su file delegando a `pipeline.file_utils.safe_write_text`.

    Mantiene la **paritÃ  di firma** con il backend (incluso `fsync`) per garantire
    contratti stabili tra UI e pipeline.
    """
    _safe_write_text(Path(path), data, encoding=encoding, atomic=atomic, fsync=fsync)


def get_theme_base(default: str = "light") -> str:
    """Restituisce la base del tema Streamlit ('light'/'dark'), con fallback."""
    try:
        import streamlit as st
    except Exception:
        return default

    candidates: list[str] = []

    def _remember(value: object | None) -> None:
        if isinstance(value, str):
            value = value.strip()
            if value:
                candidates.append(value)

    getter = getattr(st, "get_option", None)
    if callable(getter):
        try:
            _remember(getter("theme.base"))
        except Exception:
            pass

    state = getattr(st, "session_state", None)
    if state is not None:
        manual = state.get("_ui_theme_base")
        if isinstance(manual, str) and manual.strip():
            return manual.strip().lower()

    def _state_lookup(key: str) -> None:
        if state is None:
            return
        getter_attr = getattr(state, "get", None)
        try:
            value = getter_attr(key) if callable(getter_attr) else state[key]
        except Exception:
            value = None
        _remember(value)

    for name in ("theme.base", "theme_base", "_theme_base", "preferred_theme"):
        _state_lookup(name)

    if state is not None:
        for ctx_key in ("theme", "_theme", "streamlit_theme"):
            getter_attr = getattr(state, "get", None)
            try:
                theme_ctx = getter_attr(ctx_key) if callable(getter_attr) else state[ctx_key]
            except Exception:
                theme_ctx = None
            if isinstance(theme_ctx, dict):
                _remember(theme_ctx.get("base"))

    ctx = None
    try:  # pragma: no cover -- Streamlit internals not available in tests
        from streamlit.runtime.scriptrunner import script_run_context as _ctx_mod

        ctx = getattr(_ctx_mod, "get_script_run_ctx", lambda: None)()
    except Exception:
        ctx = None

    if ctx is not None:
        session = getattr(ctx, "session", None)
        client = getattr(session, "client", None) if session is not None else None
        theme_obj = getattr(client, "theme", None) if client is not None else None
        _remember(getattr(theme_obj, "base", None))
        if isinstance(theme_obj, dict):
            _remember(theme_obj.get("base"))
        nested = getattr(theme_obj, "_theme", None)
        if isinstance(nested, dict):
            _remember(nested.get("base"))

    for candidate in candidates:
        return candidate.lower()
    return default


def resolve_theme_logo_path(repo_root: Path) -> Path:
    """Restituisce il percorso del logo coerente con il tema corrente."""
    theme_img_dir = Path(repo_root) / "src" / "ui" / "theme" / "img"
    default_logo = theme_img_dir / "next-logo.png"
    dark_logo = theme_img_dir / "next-logo-bianco.png"

    override = os.getenv("TIMMY_UI_BRAND_THEME")
    forced_base = override.strip().lower() if override else None
    base = forced_base or get_theme_base()
    import logging

    logging.getLogger("ui.brand").info("resolve_theme_logo_path base=%%s override=%%s", base, override)

    if base == "dark" and dark_logo.is_file():
        return dark_logo
    if default_logo.is_file():
        return default_logo
    if dark_logo.is_file():
        return dark_logo
    return default_logo
