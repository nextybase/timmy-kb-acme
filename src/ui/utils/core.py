# SPDX-License-Identifier: GPL-3.0-only
# src/ui/utils/core.py
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, cast

from pipeline.file_utils import safe_write_text as _safe_write_text
from pipeline.path_utils import ensure_within_and_resolve as _ensure_within_and_resolve
from pipeline.path_utils import to_kebab as _to_kebab


def to_kebab(s: str) -> str:
    """Converte una stringa in kebab-case usando la utility SSoT di pipeline."""
    return str(_to_kebab(s))


def ensure_within_and_resolve(base: Path | str, candidate: Path | str) -> Path:
    """Wrapper SSoT per `pipeline.path_utils.ensure_within_and_resolve`.

    Esegue solo il cast `Path|str` â†’ `Path` e delega al backend, mantenendo la firma pubblica.
    """
    return cast(Path, _ensure_within_and_resolve(Path(base), Path(candidate)))


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
    path: Path,
    data: str,
    *,
    encoding: str = "utf-8",
    atomic: bool = True,
    fsync: bool = False,
) -> None:
    """Scrive testo su file delegando a `pipeline.file_utils.safe_write_text`.

    Mantiene la **parità di firma** con il backend (incluso `fsync`) per garantire
    contratti stabili tra UI e pipeline.
    """
    _safe_write_text(Path(path), data, encoding=encoding, atomic=atomic, fsync=fsync)


def _normalize_theme_value(value: object | None) -> str | None:
    if isinstance(value, str):
        candidate = value.strip().lower()
        if candidate in {"light", "dark"}:
            return candidate
    if isinstance(value, dict):
        return _normalize_theme_value(value.get("base"))
    return None


def get_theme_base(default: str = "light") -> str:
    """Restituisce la base tema Streamlit ('light'/'dark') sincronizzando la sessione."""
    try:
        import streamlit as st
    except Exception:
        return default

    state = getattr(st, "session_state", None)

    # 1) Theme scelto dall'utente via impostazioni Streamlit
    getter = getattr(st, "get_option", None)
    option_base: str | None = None
    if callable(getter):
        try:
            option_base = _normalize_theme_value(getter("theme.base"))
        except Exception:
            option_base = None

    # 2) Eventuale override manuale già presente in sessione
    session_base: str | None = None
    if state is not None:
        session_base = (
            _normalize_theme_value(state.get("brand_theme"))
            or _normalize_theme_value(state.get("_ui_theme_base"))
            or _normalize_theme_value(state.get("theme"))
            or _normalize_theme_value(state.get("_theme"))
            or _normalize_theme_value(state.get("_current_theme"))
        )

    # 3) Fallback da contesto runtime (caso legacy)
    runtime_base: str | None = None
    try:  # pragma: no cover -- Streamlit internals non disponibili in test
        from streamlit.runtime.scriptrunner import script_run_context as _ctx_mod

        ctx = getattr(_ctx_mod, "get_script_run_ctx", lambda: None)()
    except Exception:
        ctx = None
    if ctx is not None:
        session = getattr(ctx, "session", None)
        client = getattr(session, "client", None) if session is not None else None
        theme_obj = getattr(client, "theme", None) if client is not None else None
        runtime_base = _normalize_theme_value(getattr(theme_obj, "base", None))
        if runtime_base is None and isinstance(theme_obj, dict):
            runtime_base = _normalize_theme_value(theme_obj.get("base"))
        nested = getattr(theme_obj, "_theme", None)
        if runtime_base is None and isinstance(nested, dict):
            runtime_base = _normalize_theme_value(nested.get("base"))
        if runtime_base is None:
            runtime_base = _normalize_theme_value(getattr(theme_obj, "_user_theme", None))
        browser_theme = getattr(client, "_browser_theme", None) if client is not None else None
        if runtime_base is None and isinstance(browser_theme, dict):
            runtime_base = _normalize_theme_value(browser_theme.get("base"))

    # Se la configurazione è "system", preferiamo session/runtime
    if option_base == "system":
        option_base = None

    # Preferisci il tema scelto dal client (session/runtime); option_base è il default da config.toml
    base = session_base or runtime_base or option_base or _normalize_theme_value(default) or "light"

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
