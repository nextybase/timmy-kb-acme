# SPDX-License-Identifier: GPL-3.0-or-later
# src/ui/utils/__init__.py
from __future__ import annotations

from importlib import import_module
from typing import Any

from .branding import get_favicon_path, render_brand_header, render_sidebar_brand
from .core import ensure_within_and_resolve, to_kebab, yaml_dump, yaml_load
from .workspace import (
    get_ui_workspace_layout,
    has_normalized_markdown,
    normalized_ready,
    resolve_raw_dir,
    tagging_ready,
)

_SLUG_EXPORTS = {
    "clear_active_slug",
    "clear_slug",
    "get_active_slug",
    "get_slug",
    "get_runtime_slug",
    "require_active_slug",
    "set_active_slug",
    "set_slug",
}

__all__: list[str] = [
    "ensure_within_and_resolve",
    "to_kebab",
    "yaml_dump",
    "yaml_load",
    "get_favicon_path",
    "render_brand_header",
    "render_sidebar_brand",
    "clear_active_slug",
    "clear_slug",
    "get_slug",
    "get_runtime_slug",
    "set_slug",
    "require_active_slug",
    "get_ui_workspace_layout",
    "has_normalized_markdown",
    "normalized_ready",
    "tagging_ready",
    "resolve_raw_dir",
]


def __getattr__(name: str) -> Any:
    if name not in _SLUG_EXPORTS:
        raise AttributeError(f"module 'ui.utils' has no attribute {name!r}") from None
    module = import_module("ui.utils.slug")
    if name == "get_slug":
        return getattr(module, "get_active_slug")
    if name == "set_slug":
        return getattr(module, "set_active_slug")
    return getattr(module, name)


def __dir__() -> list[str]:
    return sorted(__all__)
