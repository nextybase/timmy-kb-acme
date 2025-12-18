# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, Type, cast

from pipeline.exceptions import ConfigError

if TYPE_CHECKING:  # pragma: no cover
    from openai import OpenAI


def get_openai_ctor() -> Type["OpenAI"]:
    try:
        module = import_module("openai")
        OpenAIType = getattr(module, "OpenAI")
    except ImportError as exc:  # pragma: no cover
        raise ConfigError("OpenAI SDK non disponibile: installa il pacchetto 'openai'.") from exc

    return cast(Type["OpenAI"], OpenAIType)
