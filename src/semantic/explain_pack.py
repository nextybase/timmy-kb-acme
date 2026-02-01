# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any, Mapping, Sequence

from semantic.contracts import AssertionContract, RelationContract


def _norm_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=False).encode("utf-8")


def _checksum(value: Any) -> str:
    digest = hashlib.sha256(_norm_json(value)).hexdigest()
    return digest


def build_explain_pack(
    *,
    assertions: Sequence[AssertionContract],
    relations: Sequence[RelationContract],
    explanations: Sequence[Mapping[str, Any]],
    run_id: str | None = None,
    trace_id: str | None = None,
    version: str = "0.x",
) -> dict[str, Any]:
    kg_payload = {"assertions": list(assertions), "relations": list(relations)}
    explanations_payload = list(explanations)
    manifest = {
        "version": version,
        "run_id": run_id,
        "trace_id": trace_id,
        "created_at": datetime.utcnow().isoformat(),
    }
    payload = {
        "manifest": manifest,
        "kg": kg_payload,
        "explanations": explanations_payload,
        "checksums": {
            "kg": _checksum(kg_payload),
            "explanations": _checksum(explanations_payload),
        },
    }
    return payload


__all__ = ["build_explain_pack"]
