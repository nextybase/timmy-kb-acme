# SPDX-License-Identifier: GPL-3.0-only
import importlib as _il
import os
from pathlib import Path

import pytest

import pipeline.env_utils as envu


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

    # Act: reload module to reset loader and load .env from CWD, then call getter
    _il.reload(envu)
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

    # Act: reload env_utils to reset lazy loader, then load context (no required env)
    _il.reload(envu)
    ClientContext.load(slug="dummy", require_env=False, run_id=None)

    # Assert: value is read from current CWD .env via env getter
    assert envu.get_env_var("ZZZ_DRIVE_ID", required=True) == "abc123"


def test_client_context_require_env_missing_raises_configerror(monkeypatch: pytest.MonkeyPatch) -> None:
    # Arrange: assicurati che le ENV richieste non siano presenti
    monkeypatch.delenv("SERVICE_ACCOUNT_FILE", raising=False)
    monkeypatch.delenv("DRIVE_ID", raising=False)

    from pipeline.context import ClientContext
    from pipeline.exceptions import ConfigError

    # Act & Assert: con require_env=True deve alzare ConfigError chiaro (no KeyError)
    with pytest.raises(ConfigError) as ei:
        ClientContext.load(slug="dummy", require_env=True, run_id=None)
    msg = str(ei.value)
    # Messaggio informativo: cita almeno una delle variabili mancanti
    assert "Variabili d'ambiente" in msg
    assert ("SERVICE_ACCOUNT_FILE" in msg) or ("DRIVE_ID" in msg)
