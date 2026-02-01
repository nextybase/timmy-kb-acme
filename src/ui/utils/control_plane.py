# SPDX-License-Identifier: GPL-3.0-or-later
'"""Helper per orchestrare i tool control-plane dal runtime UI."""'

from __future__ import annotations

import json
import os
import subprocess
import sys
from typing import Any, Iterable

import streamlit as st

from pipeline.beta_flags import is_beta_strict

CONTROL_PLANE_SCHEMA_KEYS = (
    "status",
    "mode",
    "slug",
    "action",
    "errors",
    "warnings",
    "artifacts",
    "returncode",
    "timmy_beta_strict",
)


def ensure_runtime_strict() -> None:
    """Blocca tutte le pagine runtime quando TIMMY_BETA_STRICT esplicitamente disabilita strict."""
    if is_beta_strict():
        return

    st.error("Strict disabilitato: TIMMY_BETA_STRICT è impostato su un valore non-strict.")
    st.stop()


def _normalize_payload(payload: dict[str, Any], *, slug: str, action: str) -> dict[str, Any]:
    normalized = {key: payload.get(key) for key in CONTROL_PLANE_SCHEMA_KEYS}
    normalized["slug"] = normalized.get("slug") or slug
    normalized["action"] = action
    normalized["mode"] = normalized.get("mode") or "control_plane"
    normalized["errors"] = normalized.get("errors") or []
    normalized["warnings"] = normalized.get("warnings") or []
    normalized["artifacts"] = normalized.get("artifacts") or []
    normalized["returncode"] = normalized.get("returncode", 1)
    normalized["timmy_beta_strict"] = normalized.get("timmy_beta_strict") or "0"
    if normalized["status"] not in {"ok", "error"}:
        normalized["status"] = "error"
    return normalized


def run_control_plane_tool(
    *,
    tool_module: str,
    slug: str,
    action: str,
    args: Iterable[str] | None = None,
) -> dict[str, Any]:
    command = [sys.executable, "-m", tool_module]
    if slug:
        command += ["--slug", slug]
    if args:
        command += list(args)
    env = dict(os.environ)
    env["TIMMY_BETA_STRICT"] = "0"
    try:
        completed = subprocess.run(  # noqa: S603 - comando derivato da tool interni e non accetta shell
            command,
            capture_output=True,
            text=True,
            env=env,
        )
    except FileNotFoundError as exc:
        payload = {
            "status": "error",
            "errors": [f"Impossibile eseguire il comando: {exc}"],
            "warnings": [],
            "artifacts": [],
            "returncode": 1,
            "timmy_beta_strict": "0",
        }
        normalized = _normalize_payload(payload, slug=slug, action=action)
        normalized["errors"].append(str(exc))
        return {"payload": normalized, "command": command, "completed": None}

    output = completed.stdout.strip()
    payload: dict[str, Any]
    if output:
        try:
            payload = json.loads(output.splitlines()[-1])
        except json.JSONDecodeError as exc:
            payload = {
                "status": "error",
                "errors": [f"JSON invalido dal tool: {exc}", output],
                "warnings": [],
                "artifacts": [],
                "returncode": completed.returncode,
                "timmy_beta_strict": "0",
            }
    else:
        payload = {
            "status": "error",
            "errors": ["Nessun payload restituito dal tool."],
            "warnings": [],
            "artifacts": [],
            "returncode": completed.returncode,
            "timmy_beta_strict": "0",
        }
    normalized = _normalize_payload(payload, slug=slug, action=action)
    normalized["returncode"] = completed.returncode
    if completed.stderr:
        normalized["warnings"].append(completed.stderr.strip())
    return {"payload": normalized, "command": command, "completed": completed}


def display_control_plane_result(
    st_module: Any, payload: dict[str, Any], *, success_message: str | None = None
) -> None:
    """Mostra il payload control plane nella UI con stato/warnings/errors."""
    status = payload.get("status")
    if status == "ok":
        if success_message:
            st_module.success(success_message)
        else:
            st_module.success(f"Tool {payload.get('action')} completato con successo.")
    else:
        st_module.error(f"Tool {payload.get('action')} fallito: verifica i messaggi.")
    for warning in payload.get("warnings", []):
        st_module.warning(warning)
    for error in payload.get("errors", []):
        st_module.error(error)
    # TODO(Beta1.0): remove fallback once Streamlit json() availability is enforced.
    json_renderer = getattr(st_module, "json", None)
    if callable(json_renderer):
        json_renderer(payload)
    else:
        st_module.markdown(f"```json\n{payload}\n```")
