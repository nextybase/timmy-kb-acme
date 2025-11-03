# SPDX-License-Identifier: GPL-3.0-or-later
# src/ui/utils/branding.py
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

try:
    import streamlit as st
except Exception:  # pragma: no cover
    st = None

from .core import get_theme_base, resolve_theme_logo_path


def _theme_img_dir(repo_root: Path) -> Path:
    return Path(repo_root) / "src" / "ui" / "theme" / "img"


def _logo_for_theme(repo_root: Path) -> Path:
    base = get_theme_base()
    img_dir = _theme_img_dir(repo_root)
    if base == "dark":
        dark_logo = img_dir / "next-logo-bianco.png"
        if dark_logo.is_file():
            return dark_logo
    light_logo = img_dir / "next-logo.png"
    if light_logo.is_file():
        return light_logo
    return resolve_theme_logo_path(repo_root)


def get_favicon_path(repo_root: Path) -> Path:
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
    subtitle: Optional[str] = None,
    include_anchor: bool = False,
    show_logo: bool = True,
) -> None:
    if st_module is None:
        return

    logo_path = _logo_for_theme(repo_root)

    if include_anchor:
        st_module.write("")  # no-op placeholder per compatibilità

    def _call(obj: Any, method: str, *args: Any, **kwargs: Any) -> None:
        fn = getattr(obj, method, None)
        if callable(fn):
            try:
                fn(*args, **kwargs)
            except Exception:
                pass

    if show_logo and logo_path.is_file():
        col_logo, col_title = st_module.columns([1, 5])
        with col_logo:
            st_module.image(str(logo_path), use_column_width=True)
        with col_title:
            _call(col_title, "title", "Onboarding NeXT - Clienti")
            if subtitle:
                _call(col_title, "caption", subtitle)
    else:
        _call(st_module, "title", "Onboarding NeXT - Clienti")
        if subtitle:
            _call(st_module, "caption", subtitle)


def render_sidebar_brand(*, st_module: Any | None, repo_root: Path) -> None:
    if st_module is None:
        return
    logo_path = _logo_for_theme(repo_root)
    target = getattr(st_module, "sidebar", st_module)
    image_fn = getattr(target, "image", None)
    if callable(image_fn) and logo_path.is_file():
        try:
            image_fn(str(logo_path), use_column_width=True)
        except Exception:
            pass


__all__ = ["get_favicon_path", "render_brand_header", "render_sidebar_brand"]
