from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from .core import resolve_theme_logo_path

DEFAULT_TITLE = "Onboarding NeXT - Clienti"


def get_favicon_path(repo_root: Path) -> Path:
    """Return the path to the UI favicon."""
    return Path(repo_root).resolve() / "assets" / "ico-next.png"


def render_brand_header(
    *,
    st_module: Any,
    repo_root: Path,
    title: str = DEFAULT_TITLE,
    subtitle: Optional[str] = None,
    include_anchor: bool = False,
) -> None:
    """Render the shared brand header with theme-aware logo."""
    if st_module is None:
        return

    if include_anchor:
        try:
            st_module.markdown("<main id='main'></main>", unsafe_allow_html=True)
        except Exception:
            pass

    try:
        col_logo, col_text = st_module.columns([1, 3])
    except Exception:
        return

    logo_path = resolve_theme_logo_path(Path(repo_root).resolve())
    try:
        if logo_path.exists():
            col_logo.image(str(logo_path), width="stretch")
    except Exception:
        pass

    try:
        col_text.title(title)
        if subtitle:
            col_text.caption(subtitle)
    except Exception:
        pass
