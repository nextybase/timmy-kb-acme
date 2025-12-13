# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from types import ModuleType
from typing import Any, Callable, Dict, Iterable, Optional, Sequence, Tuple, Type


class _ProvisionFromVisionFunc(Callable[..., Dict[str, Any]]):
    pass


class _ProvisionFromVisionYamlFunc(Callable[..., Dict[str, Any]]):
    pass


class _PreparePromptFunc(Callable[..., str]):
    pass


class _PreparePromptYamlFunc(Callable[..., str]):
    pass


@dataclass(frozen=True)
class VisionBindings:
    halt_error: Type[Exception]
    provision: _ProvisionFromVisionFunc
    prepare: _PreparePromptFunc
    provision_yaml: Optional[_ProvisionFromVisionYamlFunc]
    prepare_yaml: Optional[_PreparePromptYamlFunc]
    diagnostics: Tuple[str, ...] = tuple()


VISION_PROVIDER_CANDIDATES: tuple[str, ...] = (
    "src.semantic.vision_provision",
    "semantic.vision_provision",
)


def _import_module(name: str) -> Optional[ModuleType]:
    try:
        return import_module(name)
    except ImportError:
        return None


def iter_available_vision_providers(
    candidates: Sequence[str] | None = None,
) -> Iterable[ModuleType]:
    """Itera i moduli Vision disponibili secondo l'elenco SSoT."""

    if candidates is None:
        candidates = VISION_PROVIDER_CANDIDATES

    for module_name in candidates:
        module = _import_module(module_name)
        if module is not None:
            yield module


def load_vision_bindings(
    candidates: Sequence[str] | None = None,
) -> VisionBindings:
    """Carica le binding Vision da semantic con fallback il modulo root."""

    diagnostics: list[str] = []

    module_candidates = candidates if candidates is not None else VISION_PROVIDER_CANDIDATES
    for module_name in module_candidates:
        module = _import_module(module_name)
        if module is None:
            diagnostics.append(f"Import fallito: {module_name}")
            continue

        halt_error = getattr(module, "HaltError", None)
        provision = getattr(module, "provision_from_vision", None)
        prepare = getattr(module, "prepare_assistant_input", None)
        provision_yaml = getattr(module, "provision_from_vision_yaml", None)
        prepare_yaml = getattr(module, "prepare_assistant_input_from_yaml", None)

        if isinstance(halt_error, type) and callable(provision) and callable(prepare):
            return VisionBindings(
                halt_error=halt_error,
                provision=provision,
                prepare=prepare,
                provision_yaml=provision_yaml if callable(provision_yaml) else None,
                prepare_yaml=prepare_yaml if callable(prepare_yaml) else None,
                diagnostics=tuple(diagnostics),
            )

        diagnostics.append(f"Modulo {module_name} incompleto")

    from semantic.vision_provision import HaltError as fallback_error
    from semantic.vision_provision import prepare_assistant_input as fallback_prepare
    from semantic.vision_provision import provision_from_vision as fallback_provision
    from semantic.vision_provision import provision_from_vision_yaml as fallback_provision_yaml

    try:
        from semantic.vision_provision import prepare_assistant_input_from_yaml as fallback_prepare_yaml
    except Exception:
        fallback_prepare_yaml = None

    return VisionBindings(
        halt_error=fallback_error,
        provision=fallback_provision,
        prepare=fallback_prepare,
        provision_yaml=fallback_provision_yaml if callable(fallback_provision_yaml) else None,
        prepare_yaml=fallback_prepare_yaml if callable(fallback_prepare_yaml) else None,
        diagnostics=tuple(diagnostics),
    )
