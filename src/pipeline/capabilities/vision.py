# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from types import ModuleType
from typing import Any, Dict, Iterable, Optional, Protocol, Sequence, Type


class _ProvisionFromVisionFunc(Protocol):
    def __call__(self, *args: Any, **kwargs: Any) -> Dict[str, Any]: ...


class _ProvisionFromVisionYamlFunc(Protocol):
    def __call__(self, *args: Any, **kwargs: Any) -> Dict[str, Any]: ...


class _PreparePromptFunc(Protocol):
    def __call__(self, *args: Any, **kwargs: Any) -> str: ...


class _PreparePromptYamlFunc(Protocol):
    def __call__(self, *args: Any, **kwargs: Any) -> str: ...


@dataclass(frozen=True)
class VisionBindings:
    halt_error: Type[Exception]
    provision_with_config: _ProvisionFromVisionFunc
    prepare_with_config: _PreparePromptFunc
    provision_yaml_with_config: Optional[_ProvisionFromVisionYamlFunc]
    prepare_yaml_with_config: Optional[_PreparePromptYamlFunc]


VISION_PROVIDER_CANDIDATES: tuple[str, ...] = ("semantic.vision_provision",)


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
    """Carica le binding Vision dalla lista ufficiale."""

    module_candidates = candidates if candidates is not None else VISION_PROVIDER_CANDIDATES

    for module_name in module_candidates:
        module = _import_module(module_name)
        if module is None:
            continue

        halt_error = getattr(module, "HaltError", None)
        provision = getattr(module, "provision_from_vision_with_config", None)
        prepare = getattr(module, "prepare_assistant_input_with_config", None)
        provision_yaml = getattr(module, "provision_from_vision_yaml_with_config", None)
        prepare_yaml = getattr(module, "prepare_assistant_input_from_yaml_with_config", None)

        if isinstance(halt_error, type) and callable(provision) and callable(prepare):
            return VisionBindings(
                halt_error=halt_error,
                provision_with_config=provision,
                prepare_with_config=prepare,
                provision_yaml_with_config=provision_yaml if callable(provision_yaml) else None,
                prepare_yaml_with_config=prepare_yaml if callable(prepare_yaml) else None,
            )

    raise ImportError(
        "Unable to load Vision bindings: no module among " f"{', '.join(module_candidates)} exposes the required API."
    )
