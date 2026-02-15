# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import os
from collections.abc import Mapping

from pipeline.beta_flags import is_beta_strict
from pipeline.env_constants import WORKSPACE_ROOT_ENV
from pipeline.exceptions import ConfigError
from pipeline.logging_utils import get_structured_logger

LOGGER = get_structured_logger("pipeline.runtime_guard")


def ensure_strict_runtime(
    *,
    env: Mapping[str, str] | None = None,
    context: str = "",
    require_workspace_root: bool = False,
) -> None:
    """Verifica prerequisiti strict runtime al boundary dell'entrypoint."""
    source: Mapping[str, str] = env if env is not None else os.environ
    if not is_beta_strict(source):
        LOGGER.error(
            "pipeline.strict_runtime.precondition_failed",
            extra={"context": context, "strict_env": source.get("TIMMY_BETA_STRICT")},
        )
        raise ConfigError(
            "Strict disabilitato: TIMMY_BETA_STRICT e' impostato su un valore non-strict.",
            code="runtime.strict_missing",
            component="pipeline.runtime_guard",
        )

    if not require_workspace_root:
        return

    workspace_root = source.get(WORKSPACE_ROOT_ENV)
    if workspace_root and str(workspace_root).strip():
        return

    LOGGER.error(
        "pipeline.workspace_root.precondition_failed",
        extra={"context": context, WORKSPACE_ROOT_ENV: workspace_root},
    )
    raise ConfigError(
        f"{WORKSPACE_ROOT_ENV} obbligatorio per questo entrypoint runtime.",
        code="runtime.workspace_root_missing",
        component="pipeline.runtime_guard",
    )
