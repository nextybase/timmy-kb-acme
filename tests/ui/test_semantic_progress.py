# SPDX-License-Identifier: GPL-3.0-only
import json
import sys
import types
from pathlib import Path

import pytest


def _install_yaml_stub() -> None:
    """Installa un placeholder minimale di `yaml` per l'ambiente di test."""

    if "yaml" in sys.modules:
        return

    def _safe_load(text: str | bytes | None = None, **_: object):
        if text is None:
            return {}
        try:
            return json.loads(text)
        except Exception:
            return {}

    def _safe_dump(data: object, **_: object) -> str:
        try:
            return json.dumps(data)
        except Exception:
            return "{}"

    yaml_stub = types.SimpleNamespace(safe_load=_safe_load, safe_dump=_safe_dump)
    sys.modules["yaml"] = yaml_stub


_install_yaml_stub()

from ui import semantic_progress


@pytest.fixture()
def temp_repo_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Imposta un repository temporaneo per isolare le scritture."""

    monkeypatch.setattr(semantic_progress, "REPO_ROOT", tmp_path)
    return tmp_path


def test_get_semantic_progress_defaults(temp_repo_root: Path) -> None:
    result = semantic_progress.get_semantic_progress("Acme")

    assert result == {step: False for step in semantic_progress.SEMANTIC_STEP_IDS}
    storage_dir = temp_repo_root / "clients_db" / "semantic_progress"
    assert storage_dir.exists()
    assert not any(storage_dir.iterdir())


def test_mark_semantic_step_done_roundtrip(temp_repo_root: Path) -> None:
    semantic_progress.mark_semantic_step_done(" dummy ", semantic_progress.STEP_ENRICH)

    storage_dir = temp_repo_root / "clients_db" / "semantic_progress"
    progress_file = storage_dir / "dummy.json"

    with progress_file.open("r", encoding="utf-8") as fp:
        persisted = json.load(fp)

    assert persisted == {semantic_progress.STEP_ENRICH: True}
    result = semantic_progress.get_semantic_progress("dummy")
    assert result[semantic_progress.STEP_ENRICH] is True
    assert all(
        not result[step] for step in semantic_progress.SEMANTIC_STEP_IDS if step != semantic_progress.STEP_ENRICH
    )
