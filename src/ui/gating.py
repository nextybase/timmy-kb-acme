from __future__ import annotations

import importlib.util
import os
from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence

from pipeline.logging_utils import get_structured_logger
from ui.pages.registry import PagePaths, PageSpec, page_specs
from ui.utils import get_active_slug
from ui.utils.workspace import has_raw_pdfs

_DISABLE_VALUES = {"0", "false", "off", "no", ""}

_LOGGER = get_structured_logger("ui.gating")
_LAST_RAW_READY: dict[str, bool] = {}


def _flag(env: Mapping[str, str], name: str, default: bool) -> bool:
    raw = env.get(name)
    if raw is None:
        return default
    return raw.strip().casefold() not in _DISABLE_VALUES


def _module_available(module_name: str) -> bool:
    """Ritorna True se il modulo è importabile senza eseguirlo."""
    return importlib.util.find_spec(module_name) is not None


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

    drive_available = _module_available("ui.services.drive_runner")
    vision_available = _module_available("ui.services.vision_provision")
    tags_available = _module_available("ui.services.tags_adapter")

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
    slug_key = slug or "<none>"
    last_state = _LAST_RAW_READY.get(slug_key)
    if not raw_ready and last_state is not False:
        try:
            _LOGGER.info("ui.gating.sem_hidden", extra={"slug": slug or "", "raw_ready": raw_ready})
        except Exception:
            pass
    _LAST_RAW_READY[slug_key] = raw_ready
    for group, specs in page_specs().items():
        allowed = [spec for spec in specs if _satisfied(_requires(spec), gates)]
        if not raw_ready:
            allowed = [spec for spec in allowed if spec.path != PagePaths.SEMANTICS]
        if allowed:
            groups[group] = allowed
    return groups
