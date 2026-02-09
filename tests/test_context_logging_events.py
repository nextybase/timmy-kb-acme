# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import logging
from pathlib import Path

import pytest

from pipeline.context import ClientContext
from pipeline.exceptions import ConfigError
from pipeline.logging_utils import get_structured_logger
from tests._helpers.workspace_paths import local_workspace_dir
from tests.conftest import DUMMY_SLUG


class _Mem(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:  # pragma: no cover - banale
        self.records.append(record)


def test_bootstrap_logging_events(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    # Forza REPO_ROOT_DIR verso una repo root temporanea con sentinel
    repo_root = tmp_path / "repo-root"
    (repo_root / ".git").mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("REPO_ROOT_DIR", str(repo_root))
    monkeypatch.setenv("TIMMY_ALLOW_BOOTSTRAP", "1")
    ws = local_workspace_dir(repo_root / "output", DUMMY_SLUG)
    ws.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("WORKSPACE_ROOT_DIR", str(ws))

    # Logger strutturato con handler in memoria
    lg = get_structured_logger("test.context")
    mem = _Mem()
    mem.setLevel(logging.INFO)
    lg.addHandler(mem)

    # require_drive_env=False per non dipendere da variabili esterne
    ctx = ClientContext.load(DUMMY_SLUG, logger=lg, require_drive_env=False, bootstrap_config=True)
    expected_root = local_workspace_dir(repo_root / "output", DUMMY_SLUG)
    assert ctx.repo_root_dir == expected_root.resolve()

    # Verifica eventi
    events = {r.msg for r in mem.records}
    assert "context.config.bootstrap" in events  # config creato perché assente
    assert "context.config.loaded" in events


def test_repo_root_dir_invalid_includes_slug(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    # Env impostato ma Path.resolve forza un errore
    monkeypatch.setenv("REPO_ROOT_DIR", str(tmp_path / "bad"))
    ws = tmp_path / "ws"
    ws.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("WORKSPACE_ROOT_DIR", str(ws))

    import pipeline.context as ctxmod

    def _boom(self):  # type: ignore[no-redef]
        raise OSError("bad path")

    monkeypatch.setattr(ctxmod.Path, "resolve", _boom, raising=True)

    with pytest.raises(ConfigError) as ei:
        ClientContext.load("oops", logger=get_structured_logger("t"), require_drive_env=False)
    err = ei.value
    assert getattr(err, "slug", None) == "oops"
    msg = str(err)
    assert msg.startswith("REPO_ROOT_DIR non valido:") or msg.startswith("WORKSPACE_ROOT_DIR non valido:")
