# SPDX-License-Identifier: GPL-3.0-only
"""
Namespace package per le API pubbliche di Timmy KB.

Espone alias stabili `timmykb.*` verso i moduli storici (ingest, retriever, ecc.)
in modo da poter importare sia dopo `pip install` che dal workspace locale.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from types import ModuleType
from typing import Dict

_PKG_DIR = Path(__file__).resolve().parent
_SRC_ROOT = _PKG_DIR.parent
__path__ = [str(_PKG_DIR), str(_SRC_ROOT)]

_ALIASES: Dict[str, str] = {
    # Moduli top-level
    "ingest": "src.ingest",
    "kb_db": "src.kb_db",
    "prompt_builder": "src.prompt_builder",
    "retriever": "src.retriever",
    "pre_onboarding": "src.pre_onboarding",
    "onboarding_full": "src.onboarding_full",
    "semantic_headless": "src.semantic_headless",
    "semantic_onboarding": "src.semantic_onboarding",
    "tag_onboarding": "src.tag_onboarding",
    "vscode_bridge": "src.vscode_bridge",
}

# I sotto-package principali vengono aliasati da file dedicati (timmykb/ui, ecc.)
__all__ = sorted(
    [
        *list(_ALIASES.keys()),
        "ai",
        "pipeline",
        "security",
        "semantic",
        "storage",
        "tools",
        "ui",
    ]
)


def _load_alias(name: str) -> ModuleType:
    target = _ALIASES[name]
    module = importlib.import_module(target)
    sys.modules[f"{__name__}.{name}"] = module
    return module


def __getattr__(name: str) -> ModuleType:
    if name in _ALIASES:
        return _load_alias(name)
    raise AttributeError(f"Modulo timmykb.{name} non disponibile.")


def __dir__() -> list[str]:
    return sorted(list(globals().keys()) + list(_ALIASES.keys()))
