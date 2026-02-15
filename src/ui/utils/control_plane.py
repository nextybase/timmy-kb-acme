# SPDX-License-Identifier: GPL-3.0-or-later
"""Helper per orchestrare i tool control-plane dal runtime UI."""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import uuid
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Iterable, Mapping

import streamlit as st

from pipeline.beta_flags import is_beta_strict
from pipeline.logging_utils import get_structured_logger
from pipeline.workspace_layout import WorkspaceLayout
from storage import decision_ledger
from ui.utils.streamlit_baseline import require_streamlit_feature

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

LOGGER = get_structured_logger("ui.control_plane")
_ALLOWED_NON_STRICT_STEPS = {"vision_enrichment"}


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


def _run_command(command: list[str], *, env: dict[str, str]) -> subprocess.CompletedProcess:
    return subprocess.run(  # noqa: S603
        command,
        capture_output=True,
        text=True,
        env=env,
    )


def _parse_payload_stdout(output: str) -> tuple[dict[str, Any] | None, str | None]:
    """Estrae il payload JSON dall'output del tool.

    Alcuni tool possono emettere log su stdout prima/dopo il JSON finale.
    Strategia:
    - prova da ultima riga verso l'alto (line-oriented JSON payload),
    - fallback al parse dell'intero output.
    """
    if not output:
        return None, None
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    for line in reversed(lines):
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed, None
    try:
        parsed_full = json.loads(output)
    except json.JSONDecodeError as exc:
        return None, str(exc)
    if isinstance(parsed_full, dict):
        return parsed_full, None
    return None, "Payload JSON non oggetto."


def _open_layout(slug: str) -> WorkspaceLayout:
    return WorkspaceLayout.from_slug(slug=slug, require_drive_env=False)


def _audit_non_strict_step(*, slug: str, step_name: str, status: str, reason_code: str, strict_output: bool) -> None:
    layout = _open_layout(slug)
    conn = decision_ledger.open_ledger(layout)
    try:
        decision_ledger.record_event(
            conn,
            event_id=uuid.uuid4().hex,
            slug=slug,
            event_name="non_strict_step",
            actor="ui_control_plane",
            occurred_at=datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
            payload={
                "step": step_name,
                "reason_code": reason_code,
                "strict_output": strict_output,
                "status": status,
            },
        )
    finally:
        conn.close()


@contextmanager
def _non_strict_step(step_name: str, *, slug: str, logger: logging.Logger) -> Iterable[None]:
    if step_name not in _ALLOWED_NON_STRICT_STEPS:
        raise RuntimeError(f"step non-strict non autorizzato: {step_name}")
    reason_code = step_name
    logger.info(
        "ui.control_plane.non_strict_step.start",
        extra={
            "slug": slug,
            "step": step_name,
            "reason_code": reason_code,
            "strict_output": False,
        },
    )
    status = "pass"
    try:
        yield
    except Exception:
        status = "error"
        raise
    finally:
        logger.info(
            "ui.control_plane.non_strict_step.complete",
            extra={
                "slug": slug,
                "step": step_name,
                "reason_code": reason_code,
                "strict_output": False,
                "status": status,
            },
        )
        _audit_non_strict_step(
            slug=slug,
            step_name=step_name,
            status=status,
            reason_code=reason_code,
            strict_output=False,
        )


def run_control_plane_tool(
    *,
    tool_module: str,
    slug: str,
    action: str,
    args: Iterable[str] | None = None,
    non_strict_step: str | None = None,
    env_overrides: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    command = [sys.executable, "-m", tool_module]
    if slug:
        command += ["--slug", slug]
    if args:
        command += list(args)
    env = dict(os.environ)
    if env_overrides:
        for key, value in env_overrides.items():
            env[str(key)] = str(value)

    try:
        if non_strict_step:
            with _non_strict_step(non_strict_step, slug=slug, logger=LOGGER):
                completed = _run_command(command, env=env)
        else:
            completed = _run_command(command, env=env)
    except FileNotFoundError as exc:
        payload = {
            "status": "error",
            "errors": [f"Impossibile eseguire il comando: {exc}"],
            "warnings": [],
            "artifacts": [],
            "returncode": 1,
            "timmy_beta_strict": env.get("TIMMY_BETA_STRICT", "0"),
        }
        normalized = _normalize_payload(payload, slug=slug, action=action)
        normalized["errors"].append(str(exc))
        return {"payload": normalized, "command": command, "completed": None}

    output = completed.stdout.strip()
    payload: dict[str, Any]
    if output:
        parsed_payload, parse_error = _parse_payload_stdout(output)
        if parsed_payload is None:
            payload = {
                "status": "error",
                "errors": [f"JSON invalido dal tool: {parse_error or 'parse_failed'}", output],
                "warnings": [],
                "artifacts": [],
                "returncode": completed.returncode,
                "timmy_beta_strict": env.get("TIMMY_BETA_STRICT", "0"),
            }
        else:
            payload = parsed_payload
    else:
        payload = {
            "status": "error",
            "errors": ["Nessun payload restituito dal tool."],
            "warnings": [],
            "artifacts": [],
            "returncode": completed.returncode,
            "timmy_beta_strict": env.get("TIMMY_BETA_STRICT", "0"),
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
    json_renderer = require_streamlit_feature(st_module, "json")
    json_renderer(payload)
