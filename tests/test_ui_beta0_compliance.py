# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

import subprocess
import sys
import types
from pathlib import Path

import pytest


def test_ui_beta0_compliance() -> None:
    """Richiama lo script di compliance e fallisce se vengono rilevate violazioni."""
    repo_root = Path(__file__).resolve().parents[1]
    script = repo_root / "tools" / "smoke" / "check_ui_beta0_compliance.py"
    result = subprocess.run(
        [sys.executable, str(script)],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        stdout = result.stdout.strip()
        stderr = result.stderr.strip()
        message = "\n".join(part for part in (stdout, stderr) if part) or "check_ui_beta0_compliance.py failed"
        raise AssertionError(message)


def test_onboarding_ui_hydrate_defaults_handles_missing_route_state(monkeypatch) -> None:
    """
    `_hydrate_query_defaults` deve degradare in modo sicuro se `ui.utils.route_state`
    non è disponibile (es. ambienti headless/test).
    """
    import streamlit as st

    def _parse_version(raw: str) -> tuple[int, ...]:
        parts: list[int] = []
        for chunk in raw.split("."):
            try:
                parts.append(int(chunk))
            except ValueError:
                break
        return tuple(parts)

    version_tuple = _parse_version(getattr(st, "__version__", "0"))
    if version_tuple < (1, 50, 0) or not hasattr(st, "Page") or not hasattr(st, "navigation"):
        pytest.skip("Streamlit navigation API non disponibile nel runtime corrente")

    import onboarding_ui as module

    original_route_state = sys.modules.get("ui.utils.route_state")
    stub = types.ModuleType("ui.utils.route_state")
    monkeypatch.setitem(sys.modules, "ui.utils.route_state", stub)

    try:
        module._hydrate_query_defaults()
    finally:
        if original_route_state is None:
            sys.modules.pop("ui.utils.route_state", None)
        else:
            sys.modules["ui.utils.route_state"] = original_route_state
