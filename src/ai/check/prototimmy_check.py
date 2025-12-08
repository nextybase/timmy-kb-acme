# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from typing import Any, Dict, Optional

from ai.prototimmy import ProtoTimmyChainResult, run_prototimmy_chain, run_prototimmy_ping


def run_prototimmy_dummy_check(
    *,
    workspace_slug: Optional[str] = None,
    base_dir: Optional[str] = None,
    verbose: bool = False,
) -> Dict[str, Any]:
    """
    Esegue ping + catena protoTimmy -> Planner -> OCP usando il layer ai.prototimmy.
    """
    ping_result = run_prototimmy_ping(base_dir=base_dir)
    chain_result: ProtoTimmyChainResult = run_prototimmy_chain(base_dir=base_dir, workspace_slug=workspace_slug)

    return {
        "ok": chain_result.ok,
        "error": chain_result.error,
        "ping_model": ping_result.model,
        "steps": [
            {
                "role": step.role,
                "model": step.model,
                "prompt": step.prompt if verbose else "",
                "output": step.output if verbose else "",
            }
            for step in chain_result.steps
        ],
    }
