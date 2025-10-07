"""Entry point package per i tab della UI (stub)."""

from .home import render_home
from .manage import render_manage
from .semantics import render_semantics

__all__ = ["render_home", "render_manage", "render_semantics"]
