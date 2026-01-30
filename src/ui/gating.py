# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

import importlib
import importlib.util
import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Iterable, Mapping, Sequence

from pipeline.exceptions import CapabilityUnavailableError, PipelineError
from pipeline.file_utils import safe_write_text
from pipeline.logging_utils import get_structured_logger
from pipeline.path_utils import ensure_within_and_resolve
from ui.utils.strict_mode import is_ui_strict

__all__ = [
    "GateState",
    "build_gate_capability_manifest",
    "compute_gates",
    "gate_capability_manifest_path",
    "reset_gating_cache",
    "visible_page_specs",
    "write_gate_capability_manifest",
]
from ui.clients_store import get_state
from ui.constants import SEMANTIC_READY_STATES
from ui.navigation_spec import PagePaths, requirements_for
from ui.pages.registry import PageSpec, page_specs
from ui.utils import get_active_slug
from ui.utils.workspace import normalized_ready, tagging_ready

_DISABLE_VALUES = {"0", "false", "off", "no", ""}

_LOGGER = get_structured_logger("ui.gating")
_LAST_NORMALIZED_READY: dict[str, bool] = {}
_LAST_PREVIEW_READY: dict[str, bool] = {}
_CAPABILITY_CACHE: dict[Path, dict[str, object]] = {}
_CAPABILITY_SCHEMA_VERSION = 1
_CAPABILITY_FILENAME = "gate_capabilities.json"
_OPTIONAL_GATES = {"drive", "vision", "tags"}
_LAST_OPTIONAL_GATES: dict[str, dict[str, bool]] = {}


def _log_gating_failure(event: str, exc: Exception, *, extra: dict[str, object] | None = None) -> None:
    payload = {"error": repr(exc)}
    if isinstance(exc, CapabilityUnavailableError):
        cap = getattr(exc, "capability", None)
        detail = getattr(exc, "capability_detail", None)
        provider_issue = getattr(exc, "provider_issue", None)
        if cap is not None:
            payload["capability"] = cap
        if detail is not None:
            payload["capability_detail"] = detail
        if provider_issue is not None:
            payload["provider_issue"] = provider_issue
    if extra:
        payload.update(extra)
    try:
        _LOGGER.warning(event, extra=payload)
    except Exception:
        logging.getLogger("ui.gating").warning("%s error=%r", event, exc)


def reset_gating_cache(slug: str | None = None) -> None:
    """Resetta le cache gating per lo slug indicato (o completamente se slug=None)."""
    if slug is None:
        _LAST_NORMALIZED_READY.clear()
        _LAST_PREVIEW_READY.clear()
        _CAPABILITY_CACHE.clear()
        try:
            _module_available.cache_clear()
        except AttributeError:
            pass
        return
    slug_key = slug or "<none>"
    _LAST_NORMALIZED_READY.pop(slug_key, None)
    _LAST_PREVIEW_READY.pop(slug_key, None)


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
    except Exception as exc:
        _log_gating_failure(
            "ui.gating.module_import_failed",
            exc,
            extra={"module": module_name, "attr": attr or ""},
        )
        return False
    try:
        target = getattr(module, attr)
    except Exception as exc:
        _log_gating_failure(
            "ui.gating.module_attr_failed",
            exc,
            extra={"module": module_name, "attr": attr},
        )
        return False
    return callable(target)


@dataclass(frozen=True)
class GateState:
    drive: bool
    vision: bool
    tags: bool

    def as_dict(self) -> dict[str, bool]:
        return {"drive": self.drive, "vision": self.vision, "tags": self.tags}


_KNOWN_GATES = frozenset(GateState.__annotations__.keys())


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


def _iso_utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _gate_reason(
    env: Mapping[str, str],
    *,
    env_var: str,
    module_available: bool,
) -> str:
    raw = env.get(env_var)
    if raw is None:
        return "module_available" if module_available else "module_missing"
    enabled = _flag(env, env_var, module_available)
    if enabled and not module_available:
        return "env_enabled_module_missing"
    return "env_enabled" if enabled else "env_disabled"


def build_gate_capability_manifest(env: Mapping[str, str] | None = None) -> dict[str, object]:
    env_map = env if env is not None else os.environ
    gates = compute_gates(env_map)

    drive_available = _module_available("ui.services.drive_runner", attr="plan_raw_download")
    vision_available = _module_available("ui.services.vision_provision", attr="run_vision")
    tags_available = _module_available("ui.services.tags_adapter", attr="run_tags_update")
    qa_available = _module_available("pipeline.qa_evidence", attr="write_qa_evidence")

    return {
        "schema_version": _CAPABILITY_SCHEMA_VERSION,
        "computed_at": _iso_utc_now(),
        "gates": {
            "drive": {
                "available": gates.drive,
                "reason": _gate_reason(env_map, env_var="DRIVE", module_available=drive_available),
            },
            "vision": {
                "available": gates.vision,
                "reason": _gate_reason(env_map, env_var="VISION", module_available=vision_available),
            },
            "tags": {
                "available": gates.tags,
                "reason": _gate_reason(env_map, env_var="TAGS", module_available=tags_available),
            },
            "qa": {
                "available": qa_available,
                "reason": "module_available" if qa_available else "module_missing",
            },
        },
    }


def gate_capability_manifest_path(log_dir: Path) -> Path:
    return Path(ensure_within_and_resolve(log_dir, log_dir / _CAPABILITY_FILENAME))


def write_gate_capability_manifest(log_dir: Path, env: Mapping[str, str] | None = None) -> dict[str, object]:
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        path = gate_capability_manifest_path(log_dir)
        cached = _CAPABILITY_CACHE.get(path)
        if cached is not None:
            return cached
        payload = build_gate_capability_manifest(env)
        safe_write_text(
            path,
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
            atomic=True,
        )
        _CAPABILITY_CACHE[path] = payload
        return payload
    except Exception as exc:
        raise PipelineError("Unable to write gate capability manifest.", code="gate_manifest_write_failed") from exc


def _requires(page: PageSpec) -> Sequence[str]:
    return tuple(requirements_for(page.path))


def _satisfied(requirements: Iterable[str], gates: GateState) -> bool:
    for name in requirements:
        if not getattr(gates, name, False):
            return False
    return True


def visible_page_specs(gates: GateState) -> dict[str, list[PageSpec]]:
    """
    Ritorna la mappa {gruppo: [PageSpec, ...]} filtrata in base ai gate.
    """

    def _stop_gating_error(event: str, message: str, *, slug: str | None, error: Exception) -> None:
        _LOGGER.error(
            event,
            extra={"slug": slug or "", "path": "", "error": str(error)},
        )
        from ui.utils.stubs import get_streamlit

        st = get_streamlit()
        st.error(message)
        st.stop()

    groups: dict[str, list[PageSpec]] = {}
    specs_by_group = page_specs()
    required_gates = {name for specs in specs_by_group.values() for spec in specs for name in _requires(spec)}
    slug: str | None
    normalized_ready_flag = False
    semantic_ready = False
    tagging_ready_flag = False
    state_norm = ""
    strict_mode = is_ui_strict()
    try:
        slug = get_active_slug()
    except Exception as exc:
        _stop_gating_error(
            "ui.gating.slug_failed",
            "Errore nel routing UI: impossibile determinare lo slug attivo.",
            slug=None,
            error=exc,
        )
        return {}
    unknown = required_gates - _KNOWN_GATES
    if unknown:
        _stop_gating_error(
            "ui.gating.unknown_gate",
            "Errore nel gating UI: gate non riconosciuto.",
            slug=slug if "slug" in locals() else None,
            error=RuntimeError(f"Gate non riconosciuto: {sorted(unknown)}"),
        )
        return {}

    if slug:
        try:
            ready, _path = normalized_ready(slug, strict=strict_mode)
            normalized_ready_flag = bool(ready)
        except Exception as exc:
            if strict_mode:
                _stop_gating_error(
                    "ui.gating.normalized_ready_failed",
                    "Errore nel gating UI: normalized_ready fallito.",
                    slug=slug,
                    error=exc,
                )
            _log_gating_failure(
                "ui.gating.normalized_ready_failed",
                exc,
                extra={"slug": slug, "path": "", "strict": bool(strict_mode), "reason": "exception"},
            )
            normalized_ready_flag = False
        try:
            tagging_ready_flag, _ = tagging_ready(slug, strict=strict_mode)
        except Exception as exc:
            if strict_mode:
                _stop_gating_error(
                    "ui.gating.tagging_ready_failed",
                    "Errore nel gating UI: tagging_ready fallito.",
                    slug=slug,
                    error=exc,
                )
            _log_gating_failure(
                "ui.gating.tagging_ready_failed",
                exc,
                extra={"slug": slug, "path": "", "strict": bool(strict_mode), "reason": "exception"},
            )
            tagging_ready_flag = False
        try:
            state_value = get_state(slug) or ""
            state_norm = state_value.strip().lower()
            semantic_ready = state_norm in SEMANTIC_READY_STATES
        except Exception as exc:
            if strict_mode:
                _stop_gating_error(
                    "ui.gating.state_failed",
                    "Errore nel gating UI: stato cliente non disponibile.",
                    slug=slug,
                    error=exc,
                )
            _log_gating_failure(
                "ui.gating.state_failed",
                exc,
                extra={"slug": slug, "path": "", "strict": bool(strict_mode), "reason": "exception"},
            )
            state_norm = ""
            semantic_ready = False
    slug_key = slug or "<none>"
    last_state = _LAST_NORMALIZED_READY.get(slug_key)
    if not normalized_ready_flag and last_state is not False:
        try:
            _LOGGER.debug(
                "ui.gating.sem_hidden",
                extra={
                    "slug": slug or "",
                    "normalized_ready": normalized_ready_flag,
                    "tagging_ready": tagging_ready_flag,
                },
            )
        except Exception:
            pass
    _LAST_NORMALIZED_READY[slug_key] = normalized_ready_flag
    optional_required = sorted(required_gates & _OPTIONAL_GATES)
    if optional_required:
        last_optional = _LAST_OPTIONAL_GATES.get(slug_key, {})
        try:
            from ui.utils.stubs import get_streamlit

            st = get_streamlit()
        except Exception:
            st = None
        current_optional: dict[str, bool] = {}
        for name in optional_required:
            enabled = bool(getattr(gates, name, False))
            current_optional[name] = enabled
            if not enabled and last_optional.get(name) is not False:
                _LOGGER.warning(
                    "ui.gating.optional_gate_disabled",
                    extra={"slug": slug or "", "gate": name},
                )
                if st is not None:
                    try:
                        st.warning(f"Funzionalita' opzionale non disponibile: {name}.")
                    except Exception:
                        pass
        _LAST_OPTIONAL_GATES[slug_key] = current_optional
    last_preview = _LAST_PREVIEW_READY.get(slug_key)
    for group, specs in specs_by_group.items():
        allowed = [spec for spec in specs if _satisfied(_requires(spec), gates)]
        if not normalized_ready_flag:
            allowed = [spec for spec in allowed if spec.path not in {PagePaths.SEMANTICS, PagePaths.PREVIEW}]
        elif not tagging_ready_flag:
            allowed = [spec for spec in allowed if spec.path != PagePaths.SEMANTICS]
        elif not semantic_ready:
            allowed = [spec for spec in allowed if spec.path != PagePaths.PREVIEW]
        if allowed:
            groups[group] = allowed
    preview_visible = any(spec.path == PagePaths.PREVIEW for specs in groups.values() for spec in specs)
    if not preview_visible and last_preview is not False:
        try:
            _LOGGER.debug(
                "ui.gating.preview_hidden",
                extra={
                    "slug": slug or "",
                    "normalized_ready": normalized_ready_flag,
                    "tagging_ready": tagging_ready_flag,
                    "semantic_ready": semantic_ready,
                    "state": state_norm,
                },
            )
        except Exception:
            pass
    _LAST_PREVIEW_READY[slug_key] = preview_visible
    return groups
