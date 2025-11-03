# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

import importlib
import importlib.util
import os
from dataclasses import dataclass
from functools import lru_cache
from typing import Iterable, Mapping, Sequence

from pipeline.logging_utils import get_structured_logger
from ui.clients_store import get_state
from ui.constants import SEMANTIC_READY_STATES
from ui.pages.registry import PagePaths, PageSpec, page_specs
from ui.utils import get_active_slug
from ui.utils.workspace import has_raw_pdfs

_DISABLE_VALUES = {"0", "false", "off", "no", ""}

_LOGGER = get_structured_logger("ui.gating")
_LAST_RAW_READY: dict[str, bool] = {}
_LAST_PREVIEW_READY: dict[str, bool] = {}


def _flag(env: Mapping[str, str], name: str, default: bool) -> bool:
    raw = env.get(name)
    if raw is None:
        return default
    return raw.strip().casefold() not in _DISABLE_VALUES


@lru_cache(maxsize=16)
def _module_available(module_name: str, *, attr: str | None = None) -> bool:
    """Ritorna True se il modulo e, opzionalmente, l'attributo richiesto sono disponibili."""
    if importlib.util.find_spec(module_name) is None:
        return False
    if attr is None:
        return True
    try:
        module = importlib.import_module(module_name)
    except Exception:
        return False
    return callable(getattr(module, attr, None))


@dataclass(frozen=True)
class GateState:
    drive: bool
    vision: bool
    tags: bool

    def as_dict(self) -> dict[str, bool]:
        return {"drive": self.drive, "vision": self.vision, "tags": self.tags}


def compute_gates(env: Mapping[str, str] | None = None) -> GateState:
    """
    Calcola lo stato dei gate combinando disponibilità runtime e override da env.
    - DRIVE: dipende dai servizi Drive (`ui.services.drive_runner`) e da $DRIVE (0/1).
    - VISION: dipende dai servizi Vision (`ui.services.vision_provision`) e da $VISION.
    - TAGS: dipende dal tagging (`ui.services.tags_adapter`) e da $TAGS.
    """
    env_map = env if env is not None else os.environ

    drive_available = _module_available("ui.services.drive_runner", attr="plan_raw_download")
    vision_available = _module_available("ui.services.vision_provision", attr="run_vision")
    tags_available = _module_available("ui.services.tags_adapter", attr="run_tags_update")

    drive = _flag(env_map, "DRIVE", drive_available)
    vision = _flag(env_map, "VISION", vision_available)
    tags = _flag(env_map, "TAGS", tags_available)

    return GateState(drive=drive, vision=vision, tags=tags)


_PAGE_DEPENDENCIES: dict[str, tuple[str, ...]] = {
    PagePaths.CLEANUP: ("drive",),
    PagePaths.TUNING: ("vision",),
    PagePaths.SEMANTICS: ("tags",),
    PagePaths.PREVIEW: ("tags",),
}


def _requires(page: PageSpec) -> Sequence[str]:
    return _PAGE_DEPENDENCIES.get(page.path, ())


def _satisfied(requirements: Iterable[str], gates: GateState) -> bool:
    for name in requirements:
        if not getattr(gates, name, False):
            return False
    return True


def visible_page_specs(gates: GateState) -> dict[str, list[PageSpec]]:
    """
    Ritorna la mappa {gruppo: [PageSpec, ...]} filtrata in base ai gate.
    """
    groups: dict[str, list[PageSpec]] = {}
    slug: str | None
    raw_ready = False
    semantic_ready = False
    state_norm = ""
    try:
        slug = get_active_slug()
    except Exception:
        slug = None
    if slug:
        try:
            ready, _path = has_raw_pdfs(slug)
            raw_ready = bool(ready)
        except Exception:
            raw_ready = False
        try:
            state_value = get_state(slug) or ""
            state_norm = state_value.strip().lower()
            semantic_ready = state_norm in SEMANTIC_READY_STATES
        except Exception:
            semantic_ready = False
    slug_key = slug or "<none>"
    last_state = _LAST_RAW_READY.get(slug_key)
    if not raw_ready and last_state is not False:
        try:
            _LOGGER.info("ui.gating.sem_hidden", extra={"slug": slug or "", "raw_ready": raw_ready})
        except Exception:
            pass
    _LAST_RAW_READY[slug_key] = raw_ready
    last_preview = _LAST_PREVIEW_READY.get(slug_key)
    for group, specs in page_specs().items():
        allowed = [spec for spec in specs if _satisfied(_requires(spec), gates)]
        if not raw_ready:
            allowed = [spec for spec in allowed if spec.path not in {PagePaths.SEMANTICS, PagePaths.PREVIEW}]
        elif not semantic_ready:
            allowed = [spec for spec in allowed if spec.path != PagePaths.PREVIEW]
        if allowed:
            groups[group] = allowed
    preview_visible = any(spec.path == PagePaths.PREVIEW for specs in groups.values() for spec in specs)
    if not preview_visible and last_preview is not False:
        try:
            _LOGGER.info(
                "ui.gating.preview_hidden",
                extra={
                    "slug": slug or "",
                    "raw_ready": raw_ready,
                    "semantic_ready": semantic_ready,
                    "state": state_norm,
                },
            )
        except Exception:
            pass
    _LAST_PREVIEW_READY[slug_key] = preview_visible
    return groups
