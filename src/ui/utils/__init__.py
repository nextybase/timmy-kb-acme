# src/ui/utils/__init__.py
from __future__ import annotations

from .branding import get_favicon_path, render_brand_header, render_sidebar_brand
from .core import ensure_within_and_resolve, to_kebab, yaml_dump, yaml_load

# 🔄 passa a slug manager unificato
from .slug import get_active_slug as get_slug
from .slug import require_active_slug
from .slug import set_active_slug as set_slug
from .workspace import has_raw_pdfs, resolve_raw_dir

__all__: list[str] = [
    "ensure_within_and_resolve",
    "to_kebab",
    "yaml_dump",
    "yaml_load",
    "get_favicon_path",
    "render_brand_header",
    "render_sidebar_brand",
    "get_slug",
    "set_slug",
    "require_active_slug",
    "has_raw_pdfs",
    "resolve_raw_dir",
]
