from __future__ import annotations

from typing import Any, Dict, Optional


def build_hardcheck_health(
    name: str,
    message: str,
    *,
    mode: str = "deep",
    stop_code: str | None = None,
    latency_ms: int | None = None,
) -> Dict[str, Any]:
    code = stop_code or name
    details: dict[str, Any] = {"ok": False, "details": message}
    if latency_ms is not None:
        details["latency_ms"] = latency_ms
    return {
        "status": "failed",
        "mode": mode,
        "stop_code": code,
        "errors": [message],
        "checks": [code],
        "external_checks": {code: details},
    }
