# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

from typing import TYPE_CHECKING, Type

from pipeline.exceptions import ConfigError

if TYPE_CHECKING:  # pragma: no cover
    from openai import OpenAI  # type: ignore[import]


def get_openai_ctor() -> Type["OpenAI"]:
    try:
        from openai import OpenAI  # type: ignore[import]
    except ImportError as exc:  # pragma: no cover
        raise ConfigError("OpenAI SDK non disponibile: installa il pacchetto 'openai'.") from exc

    return OpenAI
