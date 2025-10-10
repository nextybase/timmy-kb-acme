# src/ui/utils/branding.py
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

try:
    import streamlit as st
except Exception:  # pragma: no cover
    st = None

# Usa l’helper centralizzato che sceglie il logo in base al tema
from src.ui.utils.core import resolve_theme_logo_path


def get_favicon_path(repo_root: Path) -> Path:
    """Restituisce il percorso del favicon per l’app.

    Proviamo prima favicon dedicati; in fallback usiamo il logo di tema.
    """
    theme_img = Path(repo_root) / "src" / "ui" / "theme" / "img"
    candidates: list[Path] = [
        theme_img / "favicon.png",
        theme_img / "favicon.ico",
        theme_img / "next-favicon.png",
    ]
    for p in candidates:
        if p.is_file():
            return p
    # Fallback: usa il logo coerente con il tema
    return Path(resolve_theme_logo_path(repo_root))


def render_brand_header(
    *,
    st_module: Any | None,
    repo_root: Path,
    subtitle: Optional[str] = None,
    include_anchor: bool = False,
    show_logo: bool = True,
) -> None:
    """Renderizza l’header brand dell’app (logo + titolo + sottotitolo opzionale).

    Args:
        st_module: modulo streamlit (passato dall’app); se None, non esegue nulla.
        repo_root: root del repository (per risolvere i path degli asset).
        subtitle: testo facoltativo sotto il titolo.
        include_anchor: se True, aggiunge un’ancora HTML all’inizio della pagina.
        show_logo: se False evita di mostrare il logo (solo titolo/testi).
    """
    if st_module is None:
        return

    if include_anchor:
        try:
            st_module.html("<a id='top'></a>")
        except Exception:
            pass

    try:
        logo_path = resolve_theme_logo_path(repo_root)
        logo_ok = bool(show_logo) and getattr(logo_path, "exists", lambda: False)()

        if logo_ok:
            col_logo, col_title = st_module.columns([1, 5])
            with col_logo:
                st_module.image(str(logo_path), width="stretch")
            with col_title:
                st_module.title("Onboarding NeXT – Clienti")
                if subtitle:
                    st_module.caption(subtitle)
        else:
            # Nessun logo → nessuna colonna: niente gap a sinistra
            st_module.title("Onboarding NeXT – Clienti")
            if subtitle:
                st_module.caption(subtitle)
    except Exception:
        # Header non deve mai spezzare il rendering
        pass


def render_sidebar_brand(*, st_module: Any | None, repo_root: Path) -> None:
    """Renderizza il brand nella sidebar (logo compatto)."""
    if st_module is None:
        return
    try:
        logo_path = resolve_theme_logo_path(repo_root)
        # Supporta sia il passaggio del modulo 'st' sia di 'st.sidebar'
        sidebar = getattr(st_module, "sidebar", st_module)
        if logo_path.exists():
            sidebar.image(str(logo_path), width="stretch")
    except Exception:
        pass
