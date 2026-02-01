# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DASHBOARD_DIR = REPO_ROOT / "observability" / "grafana-dashboards"


def _load_dashboard(name: str) -> dict[str, object]:
    path = DASHBOARD_DIR / name
    text = path.read_text(encoding="utf-8")
    return json.loads(text)


def _find_variable(dashboard: dict[str, object], key: str) -> dict[str, object]:
    templating = dashboard.get("templating", {})
    variables = templating.get("list", [])
    for var in variables:
        if var.get("name") == key:
            return var
    raise AssertionError(f"Variabile '{key}' non trovata nel dashboard {dashboard.get('uid')}")


def _assert_loki_variable(var: dict[str, object], query: str | None = None) -> None:
    assert var["datasource"]["uid"] == "Loki"
    assert var["includeAll"] is True
    assert var["allValue"] == ".+"
    if query is not None:
        assert var["query"] == query


def test_logs_dashboard_variables() -> None:
    dashboard = _load_dashboard("logs-dashboard.json")
    assert dashboard["uid"] == "timmy-logs"

    slug_var = _find_variable(dashboard, "slug")
    _assert_loki_variable(slug_var, query="label_values(slug)")

    run_var = _find_variable(dashboard, "run_id")
    _assert_loki_variable(run_var, query='label_values({slug="$slug"}, run_id)')

    panels = dashboard.get("panels", [])
    assert panels, "Dashboard logs privo di pannelli"
    logs_panel = panels[0]
    assert logs_panel["type"] == "logs"
    targets = logs_panel.get("targets") or []
    assert targets, "Pannello log senza target"
    expr = targets[0].get("expr", "")
    assert "slug=~" in expr
    assert "run_id=~" in expr


def test_errors_dashboard_variables() -> None:
    dashboard = _load_dashboard("errors-dashboard.json")
    assert dashboard["uid"] == "timmy-errors"

    slug_var = _find_variable(dashboard, "slug")
    _assert_loki_variable(slug_var, query="label_values(slug)")

    phase_var = _find_variable(dashboard, "phase")
    _assert_loki_variable(phase_var, query='label_values({slug="$slug"}, phase)')

    panels = dashboard.get("panels", [])
    assert len(panels) >= 2, "Dashboard errori deve avere due pannelli"

    timeseries = panels[0]
    assert timeseries["type"] == "timeseries"
    targets = timeseries.get("targets") or []
    assert targets, "Pannello time series senza target"
    assert 'level="ERROR"' in targets[0].get("expr", "")
    assert "phase=~" in targets[0].get("expr", "")

    logs_panel = panels[1]
    assert logs_panel["type"] == "logs"
    targets = logs_panel.get("targets") or []
    assert targets, "Pannello log errori senza target"
    assert 'level="ERROR"' in targets[0].get("expr", "")
    assert "phase=~" in targets[0].get("expr", "")
