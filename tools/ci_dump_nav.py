from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Mapping, MutableMapping


def _bootstrap_paths() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    src_dir = repo_root / "src"
    for candidate in (repo_root, src_dir):
        if str(candidate) not in sys.path:
            sys.path.insert(0, str(candidate))


_bootstrap_paths()


import logging

from ui.gating import GateState, compute_gates, visible_page_specs  # noqa: E402


import pipeline.env_utils as _env_utils  # noqa: E402

_logger = logging.getLogger("pipeline.env_utils.ci_dump")
_logger.addHandler(logging.NullHandler())
_logger.setLevel(logging.CRITICAL)
_logger.propagate = False
_env_utils._LOGGER = _logger  # type: ignore[attr-defined]


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
