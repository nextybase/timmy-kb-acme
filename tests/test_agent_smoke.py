# SPDX-License-Identifier: GPL-3.0-only
# tests/test_agent_smoke.py

from __future__ import annotations

import importlib.util
import re
from pathlib import Path
from types import SimpleNamespace
from typing import List

import pytest

ROOT = Path(__file__).resolve().parents[1]

QA_SAFE_PATH = ROOT / "tools" / "dev" / "qa_safe.py"
spec = importlib.util.spec_from_file_location("qa_safe", QA_SAFE_PATH)
if spec is None or spec.loader is None:
    raise ImportError(f"Impossibile caricare qa_safe da {QA_SAFE_PATH}")
qa_safe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(qa_safe)  # type: ignore[arg-type]


def test_qa_safe_executes_toolchain_in_order(monkeypatch: pytest.MonkeyPatch) -> None:
    executed: List[List[str]] = []

    def fake_run(cmd: List[str], stdout=None, stderr=None) -> SimpleNamespace:
        # Copia difensiva: i comandi possono essere mutati da chi li riceve.
        executed.append(list(cmd))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(importlib.util, "find_spec", lambda module: object())
    monkeypatch.setattr(qa_safe, "_existing_targets", lambda candidates: list(candidates))
    monkeypatch.setattr(qa_safe.subprocess, "run", fake_run)

    monkeypatch.delenv("QA_SAFE_RUN_TESTS", raising=False)
    rc = qa_safe.main([])
    assert rc == 0

    # Sequenza default: isort -> black -> ruff -> mypy (pytest OFF)
    modules = [cmd[2] for cmd in executed]
    assert modules == ["isort", "black", "ruff", "mypy"]

    # mypy deve rispettare la configurazione condivisa
    assert "--config-file" in executed[3]
    assert "mypy.ini" in executed[3]

    executed.clear()
    monkeypatch.setenv("QA_SAFE_RUN_TESTS", "1")
    rc = qa_safe.main([])
    assert rc == 0

    # Sequenza con pytest abilitato
    modules = [cmd[2] for cmd in executed]
    assert modules == ["isort", "black", "ruff", "mypy", "pytest"]

    # pytest deve essere eseguito in modalita smoke (-q) sui target documentati
    assert "-q" in executed[4]
    assert any(part.startswith("tests/ui") for part in executed[4])


def test_agent_perimeter_matches_codex_doc() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    doc_path = repo_root / ".codex" / "AGENTS.md"
    doc = doc_path.read_text(encoding="utf-8")
    try:
        path_line = next(line for line in doc.splitlines() if "Path-safety" in line and "scrivo solo in" in line)
    except StopIteration:  # pragma: no cover - documentazione non conforme
        pytest.fail("Impossibile trovare la regola Path-safety in .codex/AGENTS.md")

    allowed = {seg.rstrip("/\\") for seg in re.findall(r"`([^`]+)`", path_line)}
    lint_paths = {seg.rstrip("/\\") for seg in qa_safe.LINT_PATHS}

    assert lint_paths.issubset(allowed), f"LINT_PATHS {lint_paths} non allineati con il perimetro documentato {allowed}"
