from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Mapping, MutableMapping

import logging

import pipeline.env_utils as _env_utils  # noqa: E402
import ui.gating as _ui_gating  # noqa: E402
from ui.gating import GateState, compute_gates, visible_page_specs  # noqa: E402

_logger = logging.getLogger("pipeline.env_utils.ci_dump")
_logger.addHandler(logging.NullHandler())
_logger.setLevel(logging.CRITICAL)
_logger.propagate = False
_env_utils._LOGGER = _logger  # type: ignore[attr-defined]


def _no_active_slug() -> None:
    return None


_ui_gating.get_active_slug = _no_active_slug  # type: ignore[assignment]


def _serialize_state(gates: GateState) -> dict[str, bool]:
    return gates.as_dict()


def _serialize_navigation(groups: Mapping[str, list]) -> dict[str, list]:
    payload: dict[str, list] = {}
    for group, specs in groups.items():
        payload[group] = [
            {
                "path": spec.path,
                "title": spec.title,
                "url_path": spec.url_path,
            }
            for spec in specs
        ]
    return payload


def visible_navigation(env: MutableMapping[str, str] | None = None) -> dict[str, object]:
    """
    Restituisce la mappa di navigazione filtrata in base ai gate correnti.
    """
    gates = compute_gates(env=env or os.environ)
    groups = visible_page_specs(gates)
    return {
        "gates": _serialize_state(gates),
        "navigation": _serialize_navigation(groups),
    }


if __name__ == "__main__":
    data = visible_navigation()
    print(json.dumps(data, indent=2, sort_keys=True))
