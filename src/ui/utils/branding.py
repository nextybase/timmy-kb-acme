# SPDX-License-Identifier: GPL-3.0-or-later
# src/ui/utils/branding.py
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

try:
    import streamlit as st
except Exception:  # pragma: no cover
    st = None

from ui.theme.tokens import resolve_tokens

from .core import get_theme_base


def _theme_img_dir(repo_root: Path) -> Path:
    return Path(repo_root) / "src" / "ui" / "theme" / "img"


def _resolve_theme_base() -> str:
    """
    Seleziona in modo centralizzato il tema di base ("light" / "dark").

    Ordine di precedenza:
    1. Valore di Streamlit (st.get_option("theme.base")) se disponibile e valido.
    2. Fallback applicativo tramite get_theme_base().
    3. "light" come ultima ancora di salvataggio.
    """
    # Default prudenziale
    base = "light"

    # 1) Tentativo: opzioni Streamlit
    try:
        opt_base = None
        if st is not None:
            get_opt = getattr(st, "get_option", None)
            if callable(get_opt):
                opt_base = get_opt("theme.base")
        if isinstance(opt_base, str):
            normalized = opt_base.strip().lower()
            if normalized in {"light", "dark"}:
                return normalized
    except Exception:
        # Ignora errori di Streamlit e passa al fallback applicativo
        pass

    # 2) Fallback: configurazione applicativa
    try:
        cfg_base = get_theme_base()
        if isinstance(cfg_base, str):
            normalized = cfg_base.strip().lower()
            if normalized in {"light", "dark"}:
                base = normalized
    except Exception:
        # 3) Se anche qui fallisce, restiamo su "light"
        base = "light"

    return base


def _logo_for_theme(repo_root: Path) -> Path:
    """
    Determina il logo corretto per il tema corrente (light/dark) usando i tokens.
    """
    base = _resolve_theme_base()
    tokens = resolve_tokens(base)
    token_logo = getattr(tokens, "LOGO_IMAGE", None)

    if not isinstance(token_logo, str) or not token_logo:
        return Path()

    logo_path = (Path(repo_root) / token_logo).resolve()
    return logo_path


def get_main_logo_path(repo_root: Path) -> Path:
    """Logo principale usato in header/sidebar (non la favicon)."""
    return _logo_for_theme(repo_root)


def get_favicon_path(repo_root: Path) -> Path:
    """
    Restituisce il percorso della favicon.

    Ordine:
    1. favicon.ico / favicon.png / ico-next.png nella cartella theme/img.
    2. Fallback sul logo del tema corrente.
    """
    img_dir = _theme_img_dir(repo_root)
    for name in ("favicon.ico", "favicon.png", "ico-next.png"):
        candidate = img_dir / name
        if candidate.is_file():
            return candidate
    return _logo_for_theme(repo_root)


def render_brand_header(
    *,
    st_module: Any | None,
    repo_root: Path,
    title: Optional[str] = None,
    subtitle: Optional[str] = None,
    include_anchor: bool = False,
    show_logo: bool = True,
) -> None:
    if st_module is None:
        return

    page_title = title or None
    logo_path = _logo_for_theme(repo_root)

    def _call(obj: Any, method: str, *args: Any, **kwargs: Any) -> None:
        fn = getattr(obj, method, None)
        if callable(fn):
            try:
                fn(*args, **kwargs)
            except Exception:
                # Non blocchiamo il rendering dell'header per errori cosmetici
                pass

    if include_anchor:
        _call(st_module, "write", "")

    if show_logo and logo_path.is_file():
        columns_fn = getattr(st_module, "columns", None)
        if callable(columns_fn):
            try:
                columns = columns_fn([1, 5])
            except Exception:
                columns = None
        else:
            columns = None

        if not columns or len(columns) < 2:
            _call(st_module, "image", str(logo_path))
            if page_title:
                _call(st_module, "title", page_title)
                if subtitle:
                    _call(st_module, "caption", subtitle)
            return

        col_logo, col_title = columns[0], columns[1]
        try:
            with col_logo:
                _call(col_logo, "image", str(logo_path))
        except Exception:
            _call(col_logo, "image", str(logo_path))

        try:
            with col_title:
                if page_title:
                    _call(col_title, "title", page_title)
                    if subtitle:
                        _call(col_title, "caption", subtitle)
        except Exception:
            if page_title:
                _call(col_title, "title", page_title)
                if subtitle:
                    _call(col_title, "caption", subtitle)
    else:
        if page_title:
            _call(st_module, "title", page_title)
            if subtitle:
                _call(st_module, "caption", subtitle)


def render_sidebar_brand(*, st_module: Any | None, repo_root: Path) -> None:
    """
    Logo nella sidebar, coerente con lo stesso logo dell'header.
    """
    if st_module is None:
        return
    logo_path = _logo_for_theme(repo_root)
    target = getattr(st_module, "sidebar", st_module)
    image_fn = getattr(target, "image", None)
    if callable(image_fn) and logo_path.is_file():
        try:
            image_fn(str(logo_path))
        except Exception:
            pass


__all__ = ["get_favicon_path", "get_main_logo_path", "render_brand_header", "render_sidebar_brand"]
