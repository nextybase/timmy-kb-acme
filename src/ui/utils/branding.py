# SPDX-License-Identifier: GPL-3.0-or-later
# src/ui/utils/branding.py
from __future__ import annotations

import base64
from pathlib import Path
from typing import Any, Dict, Optional

try:
    import streamlit as st
except Exception:  # pragma: no cover
    st = None

from pipeline.path_utils import open_for_read_bytes_selfguard

from .core import get_theme_base, resolve_theme_logo_path

_ASSET_CACHE_KEY = "_brand_theme_assets"


def _build_data_uri(path: Path) -> str | None:
    if not path.is_file():
        return None
    mime = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".svg": "image/svg+xml",
        ".ico": "image/x-icon",
    }.get(path.suffix.lower())
    if mime is None:
        return None
    with open_for_read_bytes_selfguard(path) as fh:
        data = base64.b64encode(fh.read()).decode("ascii")
    return f"data:{mime};base64,{data}"


def _ensure_brand_assets(repo_root: Path) -> Dict[str, str]:
    """Prepara logo/icon per tema chiaro/scuro e inietta JS per aggiornare dinamicamente."""
    if st is None:
        return {}

    session = getattr(st, "session_state", {})
    cached = session.get(_ASSET_CACHE_KEY)
    if isinstance(cached, dict) and cached.get("light_logo"):
        return cached

    theme_img = Path(repo_root) / "src" / "ui" / "theme" / "img"
    light_logo_path = theme_img / "next-logo.png"
    dark_logo_path = theme_img / "next-logo-bianco.png"
    light_icon_path = theme_img / "favicon.ico"
    dark_icon_candidates = [
        theme_img / "favicon-dark.ico",
        theme_img / "ico-next.png",
        theme_img / "favicon.png",
    ]
    dark_icon_path = next((p for p in dark_icon_candidates if p.is_file()), light_icon_path)

    assets: Dict[str, str] = {
        "light_logo": _build_data_uri(light_logo_path) or "",
        "dark_logo": _build_data_uri(dark_logo_path) or _build_data_uri(light_logo_path) or "",
        "light_icon": _build_data_uri(light_icon_path) or "",
        "dark_icon": _build_data_uri(dark_icon_path) or _build_data_uri(light_icon_path) or "",
        "light_logo_path": str(light_logo_path),
        "dark_logo_path": str(dark_logo_path),
        "light_icon_path": str(light_icon_path),
        "dark_icon_path": str(dark_icon_path),
    }
    session[_ASSET_CACHE_KEY] = assets

    light_logo = assets["light_logo"]
    dark_logo = assets["dark_logo"] or light_logo
    light_icon = assets["light_icon"]
    dark_icon = assets["dark_icon"] or light_icon

    script = f"""
    <script>
    (function() {{
      const LIGHT_LOGO = "{light_logo}";
      const DARK_LOGO = "{dark_logo}";
      const LIGHT_ICON = "{light_icon}";
      const DARK_ICON = "{dark_icon}";

      function currentTheme() {{
        const doc = window.parent.document;
        const attr = doc.documentElement.getAttribute("data-theme");
        if (attr) {{
          return attr;
        }}
        try {{
          const stored = window.parent.localStorage.getItem("st-theme");
          if (stored) {{
            const parsed = JSON.parse(stored);
            if (parsed?.theme?.base) return parsed.theme.base;
            if (parsed?.base) return parsed.base;
          }}
        }} catch (err) {{}}
        return "light";
      }}

      function updateLogoNodes(root, src) {{
        if (!root) return;
        try {{
          root.querySelectorAll("img[data-brand-logo]").forEach((img) => {{
            if (img.src !== src) {{
              img.src = src;
            }}
          }});
        }} catch (err) {{}}
      }}

      function setFavicon(theme) {{
        if (!LIGHT_ICON) return;
        const doc = window.parent.document;
        let link = doc.querySelector("link[rel='icon']");
        if (!link) {{
          link = doc.createElement("link");
          link.rel = "icon";
          doc.head.appendChild(link);
        }}
        link.href = theme === "dark" ? (DARK_ICON || LIGHT_ICON) : LIGHT_ICON;
      }}

      function setLogo(theme) {{
        const src = theme === "dark" ? (DARK_LOGO || LIGHT_LOGO) : LIGHT_LOGO;
        if (!src) return;
        const doc = window.parent.document;
        updateLogoNodes(doc, src);
        doc.querySelectorAll("iframe").forEach((frame) => {{
          try {{
            updateLogoNodes(frame.contentDocument, src);
          }} catch (err) {{}}
        }});
      }}

      function applyTheme() {{
        const theme = currentTheme();
        setLogo(theme);
        setFavicon(theme);
      }}

      const doc = window.parent.document;
      new MutationObserver(applyTheme).observe(doc.documentElement, {{
        attributes: true,
        attributeFilter: ["data-theme"]
      }});
      window.parent.addEventListener("storage", (event) => {{
        if (event.key === "st-theme") {{
          applyTheme();
        }}
      }});
      setTimeout(applyTheme, 50);
      applyTheme();
    }})();
    </script>
    """

    try:
        st.html(script)
    except Exception:
        pass

    return assets


def get_favicon_path(repo_root: Path) -> Path:
    """Restituisce il percorso del favicon piu' appropriato per il tema attuale."""
    assets = _ensure_brand_assets(repo_root)
    base = get_theme_base()
    if base == "dark" and Path(assets.get("dark_icon_path", "")).is_file():
        return Path(assets["dark_icon_path"])
    if Path(assets.get("light_icon_path", "")).is_file():
        return Path(assets["light_icon_path"])
    return Path(resolve_theme_logo_path(repo_root))


def render_brand_header(
    *,
    st_module: Any | None,
    repo_root: Path,
    subtitle: Optional[str] = None,
    include_anchor: bool = False,
    show_logo: bool = True,
) -> None:
    """Renderizza l'header brand dell'app (logo + titolo + sottotitolo opzionale)."""
    if st_module is None or st is None:
        return

    if include_anchor:
        try:
            st_module.html("<a id='top'></a>")
        except Exception:
            pass

    assets = _ensure_brand_assets(repo_root)

    try:
        logo_path = resolve_theme_logo_path(repo_root)
        logo_ok = bool(show_logo) and getattr(logo_path, "exists", lambda: False)()
        base = get_theme_base()
        initial_logo = (
            assets["dark_logo"] if base == "dark" and assets.get("dark_logo") else assets.get("light_logo") or ""
        )
        img_tag = ""
        if initial_logo:
            img_tag = (
                '<img data-brand-logo="header" class="brand-logo brand-logo--header" '
                f'src="{initial_logo}" alt="NeXT logo" />'
            )

        if logo_ok:
            col_logo, col_title = st_module.columns([1, 5])
            with col_logo:
                if img_tag:
                    st.html(img_tag)
                else:
                    st.image(str(logo_path))
            with col_title:
                st_module.title("Onboarding NeXT - Clienti")
                if subtitle:
                    st_module.caption(subtitle)
        else:
            st_module.title("Onboarding NeXT - Clienti")
            if subtitle:
                st_module.caption(subtitle)
    except Exception:
        pass


def render_sidebar_brand(*, st_module: Any | None, repo_root: Path) -> None:
    """Renderizza il brand nella sidebar (logo compatto)."""
    if st_module is None:
        return
    try:
        logo_path = resolve_theme_logo_path(repo_root)
        sidebar = getattr(st_module, "sidebar", st_module)
        assets = _ensure_brand_assets(repo_root)
        base = get_theme_base()
        initial_logo = (
            assets["dark_logo"] if base == "dark" and assets.get("dark_logo") else assets.get("light_logo") or ""
        )
        if initial_logo:
            snippet = (
                '<img data-brand-logo="sidebar" class="brand-logo brand-logo--sidebar" '
                f'src="{initial_logo}" alt="NeXT logo" />'
            )
            st.html(snippet)
        elif logo_path.exists():
            sidebar.image(str(logo_path))
    except Exception:
        pass
