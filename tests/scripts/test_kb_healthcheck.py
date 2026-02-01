# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
TOOLS_DIR = ROOT / "tools" / "smoke"

_KB_PATH = TOOLS_DIR / "kb_healthcheck.py"
_spec = importlib.util.spec_from_file_location("kb_healthcheck", _KB_PATH)
if _spec is None or _spec.loader is None:
    raise ImportError(f"Impossibile caricare kb_healthcheck da {_KB_PATH}")
kb = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(kb)  # type: ignore[arg-type]


def test_kb_healthcheck_sets_used_file_search_and_excerpt(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pdf = tmp_path / "VisionStatement.pdf"
    pdf.write_bytes(b"pdf")

    mapping = tmp_path / "semantic_mapping.yaml"
    mapping.write_text("foo: bar\n", encoding="utf-8")

    # Stubs per evitare I/O reali e chiamate OpenAI.
    monkeypatch.setattr(kb, "_repo_pdf_path", lambda: pdf)
    monkeypatch.setattr(kb, "_sync_workspace_pdf", lambda base_dir, source_pdf: pdf)
    monkeypatch.setattr(kb, "_client_base", lambda slug: tmp_path / f"ws-{slug}")

    def _fake_run_vision(*args: Any, **kwargs: Any) -> dict[str, str]:
        return {"mapping": str(mapping)}

    monkeypatch.setattr(kb, "run_vision", _fake_run_vision)

    result = kb.run_healthcheck(slug="dummy", force=False, model="gpt-test", include_prompt=False)

    assert result["used_file_search"] is True
    assert result["assistant_text_excerpt"]


def test_kb_healthcheck_offline_ok(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo_pdf = tmp_path / "repo" / "VisionStatement.pdf"
    repo_pdf.parent.mkdir(parents=True, exist_ok=True)
    repo_pdf.write_bytes(b"pdf")

    base_dir = tmp_path / "ws-dummy"
    semantic_dir = base_dir / "semantic"
    config_dir = base_dir / "config"
    semantic_dir.mkdir(parents=True, exist_ok=True)
    config_dir.mkdir(parents=True, exist_ok=True)

    (semantic_dir / "semantic_mapping.yaml").write_text("foo: bar\n", encoding="utf-8")
    (config_dir / "VisionStatement.pdf").write_bytes(b"pdf")

    monkeypatch.setattr(kb, "_repo_pdf_path", lambda: repo_pdf)
    monkeypatch.setattr(kb, "_client_base", lambda slug: base_dir)
    monkeypatch.setattr(kb, "run_vision", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError))

    result = kb.run_healthcheck(slug="dummy", force=False, model="gpt-test", include_prompt=False, offline=True)

    assert result["status"] == "ok_offline"
