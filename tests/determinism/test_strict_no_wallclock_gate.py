# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pipeline.workspace_layout import WorkspaceLayout
from storage import decision_ledger
from tests._helpers.workspace_paths import local_workspace_dir

PY = sys.executable
WALL_CLOCK_SKEW_SECONDS = 300


def _prepare_workspace(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "raw").mkdir()
    (root / "normalized").mkdir()
    (root / "book").mkdir()
    (root / "semantic").mkdir()
    (root / "logs").mkdir()
    (root / "config").mkdir()
    (root / "book" / "README.md").write_text("# README\n", encoding="utf-8")
    (root / "book" / "SUMMARY.md").write_text("# SUMMARY\n", encoding="utf-8")
    (root / "config" / "config.yaml").write_text(
        'meta:\n  client_name: "Acme"\nops:\n  log_level: "INFO"\n',
        encoding="utf-8",
    )
    (root / "raw" / "doc-a.pdf").write_bytes(b"%PDF-1.4\nA\n")
    (root / "raw" / "doc-b.pdf").write_bytes(b"%PDF-1.4\nB\n")
    return root


def _init_empty_ledger(*, workspace_root: Path, slug: str) -> Path:
    """Crea il ledger con solo schema, senza seed di run/decision."""
    layout = WorkspaceLayout.from_workspace(workspace_root, slug=slug)
    conn = decision_ledger.open_ledger(layout)
    try:
        pass
    finally:
        conn.close()
    return decision_ledger.ledger_path_from_layout(layout)


def _run_ledger_status(*, slug: str, workspace_root: Path, repo_root: Path) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["TIMMY_BETA_STRICT"] = "1"
    env["WORKSPACE_ROOT_DIR"] = str(workspace_root)
    env.pop("REPO_ROOT_DIR", None)
    src_path = str(repo_root / "src")
    existing_pythonpath = env.get("PYTHONPATH")
    env["PYTHONPATH"] = src_path if not existing_pythonpath else f"{src_path}{os.pathsep}{existing_pythonpath}"
    return subprocess.run(
        [PY, "-m", "timmy_kb.cli", "ledger-status", "--slug", slug, "--json"],
        cwd=repo_root,
        env=env,
        capture_output=True,
        text=True,
    )


def _to_epoch_seconds(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        numeric = float(value)
        if numeric > 1e12:  # epoch ms
            return numeric / 1000.0
        if 1e8 <= numeric <= 1e11:  # epoch s plausibile
            return numeric
        return None
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        if text.isdigit():
            return _to_epoch_seconds(int(text))
        if "T" in text and ("-" in text or "/" in text):
            iso = text.replace("Z", "+00:00")
            try:
                dt = datetime.fromisoformat(iso)
            except ValueError:
                return None
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.timestamp()
    return None


def _is_near_wall_clock(epoch_s: float, *, start_s: float, end_s: float) -> bool:
    lower = start_s - WALL_CLOCK_SKEW_SECONDS
    upper = end_s + WALL_CLOCK_SKEW_SECONDS
    return lower <= epoch_s <= upper


def _timestamp_like_column(name: str) -> bool:
    lowered = name.lower()
    tokens = ("time", "timestamp", "date", "created", "updated", "started", "ended", "decided")
    return any(token in lowered for token in tokens)


def _scan_ledger_for_wall_clock(
    ledger_path: Path,
    *,
    start_s: float,
    end_s: float,
) -> list[tuple[str, str, Any]]:
    findings: list[tuple[str, str, Any]] = []
    conn = sqlite3.connect(str(ledger_path))
    try:
        tables = {
            str(row[0])
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            ).fetchall()
        }
        static_queries = (
            ("runs", "started_at", "SELECT started_at FROM runs WHERE started_at IS NOT NULL"),
            ("decisions", "decided_at", "SELECT decided_at FROM decisions WHERE decided_at IS NOT NULL"),
            ("events", "occurred_at", "SELECT occurred_at FROM events WHERE occurred_at IS NOT NULL"),
        )
        for table, column, query in static_queries:
            if table not in tables or not _timestamp_like_column(column):
                continue
            rows = conn.execute(query).fetchall()
            for (value,) in rows:
                epoch = _to_epoch_seconds(value)
                if epoch is not None and _is_near_wall_clock(epoch, start_s=start_s, end_s=end_s):
                    findings.append((table, column, value))
    finally:
        conn.close()
    return findings


def _scan_json_for_wall_clock(
    payload: Any,
    *,
    start_s: float,
    end_s: float,
) -> list[tuple[str, Any]]:
    findings: list[tuple[str, Any]] = []

    def _walk(node: Any, path: str) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                next_path = f"{path}.{key}" if path else str(key)
                epoch = _to_epoch_seconds(value)
                if epoch is not None and _is_near_wall_clock(epoch, start_s=start_s, end_s=end_s):
                    findings.append((next_path, value))
                _walk(value, next_path)
            return
        if isinstance(node, list):
            for idx, value in enumerate(node):
                _walk(value, f"{path}[{idx}]")

    _walk(payload, "")
    return findings


def test_strict_runtime_no_wall_clock_leakage_in_core_artifacts(tmp_path: Path) -> None:
    slug = "acme"
    workspace_root = _prepare_workspace(local_workspace_dir(tmp_path, slug))
    ledger_path = _init_empty_ledger(workspace_root=workspace_root, slug=slug)

    repo_root = Path(__file__).resolve().parents[2]
    start_s = time.time()
    proc = _run_ledger_status(slug=slug, workspace_root=workspace_root, repo_root=repo_root)
    end_s = time.time()

    assert proc.returncode == 0
    assert proc.stderr == ""

    lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
    assert lines, "stdout vuoto: payload JSON non trovato"
    payload = json.loads(lines[-1])

    ledger_findings = _scan_ledger_for_wall_clock(ledger_path, start_s=start_s, end_s=end_s)
    json_findings = _scan_json_for_wall_clock(payload, start_s=start_s, end_s=end_s)

    assert ledger_findings == []
    assert json_findings == []
