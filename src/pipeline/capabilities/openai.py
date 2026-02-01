# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, Type, cast

from pipeline.exceptions import CapabilityUnavailableError

if TYPE_CHECKING:  # pragma: no cover
    from openai import OpenAI


_openai_ctor: Type["OpenAI"] | None = None
try:
    module = import_module("openai")
    _openai_ctor = cast(Type["OpenAI"], getattr(module, "OpenAI"))
except ImportError:  # pragma: no cover
    _openai_ctor = None


def get_openai_ctor() -> Type["OpenAI"]:
    if not callable(_openai_ctor):
        raise CapabilityUnavailableError(
            "OpenAI capability not available. Install extra dependencies with: pip install .[openai]"
        )
    return cast(Type["OpenAI"], _openai_ctor)
