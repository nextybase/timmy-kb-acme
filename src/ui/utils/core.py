# SPDX-License-Identifier: GPL-3.0-or-later
# src/ui/utils/core.py
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, cast

from ui.utils import backend as _backend

ensure_within_and_resolve = _backend.ensure_within_and_resolve
to_kebab = _backend.to_kebab
to_kebab_soft = _backend.to_kebab_soft
_safe_write_text = _backend.safe_write_text  # hook per test/monkeypatch UI


def safe_write_text(
    path: Path,
    data: str,
    *,
    encoding: str = "utf-8",
    atomic: bool = True,
    fsync: bool = False,
) -> None:
    """Wrapper UI che delega a pipeline.file_utils.safe_write_text (monkeypatchabile nei test)."""
    _safe_write_text(path, data, encoding=encoding, atomic=atomic, fsync=fsync)
    return None


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


def _normalize_theme_value(value: object | None) -> str | None:
    if isinstance(value, str):
        candidate = value.strip().lower()
        if candidate in {"light", "dark"}:
            return candidate
    if isinstance(value, dict):
        return _normalize_theme_value(value.get("base"))
    return None


def get_theme_base(default: str = "light") -> str:
    """Restituisce la base tema Streamlit ('light'/'dark') usando solo API supportate."""
    try:
        import streamlit as st
    except Exception:
        return default

    state = getattr(st, "session_state", None)

    getter = getattr(st, "get_option", None)
    option_base: str | None = None
    if callable(getter):
        try:
            option_base = _normalize_theme_value(getter("theme.base"))
        except Exception:
            option_base = None

    if option_base == "system":
        option_base = None

    base = option_base or _normalize_theme_value(default) or "light"

    if state is not None:
        state["brand_theme"] = base
        state["_ui_theme_base"] = base

    return base


def resolve_theme_logo_path(repo_root: Path) -> Path:
    theme_img_dir = Path(repo_root) / "src" / "ui" / "theme" / "img"
    default_logo = theme_img_dir / "next-logo.png"
    dark_logo = theme_img_dir / "next-logo-bianco.png"

    base = get_theme_base()
    if base == "dark" and dark_logo.is_file():
        return dark_logo
    if default_logo.is_file():
        return default_logo
    if dark_logo.is_file():
        return dark_logo
    return default_logo
