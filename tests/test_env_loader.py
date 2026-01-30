# SPDX-License-Identifier: GPL-3.0-only
import importlib as _il
import os
from pathlib import Path

import pytest

import pipeline.env_utils as envu

pytestmark = pytest.mark.unit


def test_get_env_var_loads_dotenv(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Arrange: create a temporary .env with a variable not present in process env
    env_text = "ZZZ_DRIVE_ID=drive-from-dotenv\nZZZ_SERVICE_ACCOUNT_FILE=C:/sa.json\n"
    (tmp_path / ".env").write_text(env_text, encoding="utf-8")
    # Ensure process env is clean for these keys
    monkeypatch.delenv("ZZZ_DRIVE_ID", raising=False)
    monkeypatch.delenv("ZZZ_SERVICE_ACCOUNT_FILE", raising=False)
    # Sanity: ensure process env is clean (and use `os` import)
    assert "ZZZ_DRIVE_ID" not in os.environ
    assert "ZZZ_SERVICE_ACCOUNT_FILE" not in os.environ
    # Change CWD to the tmp directory so loader finds .env
    monkeypatch.chdir(tmp_path)

    # Act: reload module to reset loader, load .env from CWD, then call getter
    _il.reload(envu)
    envu.ensure_dotenv_loaded()
    drive_id = envu.get_env_var("ZZZ_DRIVE_ID", required=True)
    sa_file = envu.get_env_var("ZZZ_SERVICE_ACCOUNT_FILE", required=True)

    # Assert
    assert drive_id == "drive-from-dotenv"
    assert sa_file == "C:/sa.json"


def test_client_context_load_reads_dotenv(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Arrange: repo root with only a .env file
    (tmp_path / ".env").write_text("ZZZ_DRIVE_ID=abc123\n", encoding="utf-8")
    monkeypatch.delenv("ZZZ_DRIVE_ID", raising=False)
    assert "ZZZ_DRIVE_ID" not in os.environ
    monkeypatch.chdir(tmp_path)

    from pipeline.context import ClientContext

    # Act: reload env_utils to reset lazy loader, explicitly load .env, then create context (no required env)
    _il.reload(envu)
    envu.ensure_dotenv_loaded()
    ClientContext.load(
        slug="dummy",
        require_drive_env=False,
        run_id=None,
        repo_root_dir=tmp_path,
        bootstrap_config=True,
    )

    # Assert: value is read from current CWD .env via env getter
    assert envu.get_env_var("ZZZ_DRIVE_ID", required=True) == "abc123"


def test_client_context_require_drive_env_missing_raises_configerror(monkeypatch: pytest.MonkeyPatch) -> None:
    # Arrange: assicurati che le ENV richieste non siano presenti
    monkeypatch.delenv("SERVICE_ACCOUNT_FILE", raising=False)
    monkeypatch.delenv("DRIVE_ID", raising=False)

    from pipeline.context import ClientContext
    from pipeline.exceptions import ConfigError

    # Act & Assert: con require_drive_env=True deve alzare ConfigError chiaro (no KeyError)
    with pytest.raises(ConfigError) as ei:
        ClientContext.load(slug="dummy", require_drive_env=True, run_id=None)
    msg = str(ei.value)
    # Messaggio informativo: cita almeno una delle variabili mancanti
    assert "Prerequisiti Drive mancanti" in msg
    assert ("SERVICE_ACCOUNT_FILE" in msg) or ("DRIVE_ID" in msg)
    assert getattr(ei.value, "code", None) == "drive.env.missing"
