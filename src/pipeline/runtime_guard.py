# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import os
from collections.abc import Mapping

from pipeline.beta_flags import is_beta_strict
from pipeline.exceptions import ConfigError
from pipeline.logging_utils import get_structured_logger

LOGGER = get_structured_logger("pipeline.runtime_guard")


def ensure_strict_runtime(*, env: Mapping[str, str] | None = None, context: str = "") -> None:
    """Verifica che il runtime sia in modalità strict-only prima di avanzare stato."""
    source: Mapping[str, str] = env if env is not None else os.environ
    if is_beta_strict(source):
        return

    LOGGER.error(
        "pipeline.strict_runtime.precondition_failed",
        extra={"context": context, "strict_env": source.get("TIMMY_BETA_STRICT")},
    )
    raise ConfigError(
        "Strict disabilitato: TIMMY_BETA_STRICT è impostato su un valore non-strict.",
        code="runtime.strict_missing",
        component="pipeline.runtime_guard",
    )
