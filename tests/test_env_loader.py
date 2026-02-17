# SPDX-License-Identifier: GPL-3.0-or-later
from pathlib import Path

import pytest

from pipeline.context import ClientContext
from tests.support.dotenv_helpers import prepare_dotenv_env

pytestmark = pytest.mark.unit


def test_get_env_var_loads_dotenv(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    envu = prepare_dotenv_env(
        monkeypatch=monkeypatch,
        tmp_path=tmp_path,
        env_text="ZZZ_DRIVE_ID=drive-from-dotenv\nZZZ_SERVICE_ACCOUNT_FILE=C:/sa.json\n",
        clear_keys=("ZZZ_DRIVE_ID", "ZZZ_SERVICE_ACCOUNT_FILE"),
    )
    drive_id = envu.get_env_var("ZZZ_DRIVE_ID", required=True)
    sa_file = envu.get_env_var("ZZZ_SERVICE_ACCOUNT_FILE", required=True)

    # Assert
    assert drive_id == "drive-from-dotenv"
    assert sa_file == "C:/sa.json"


def test_client_context_load_reads_dotenv(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    envu = prepare_dotenv_env(
        monkeypatch=monkeypatch,
        tmp_path=tmp_path,
        env_text="ZZZ_DRIVE_ID=abc123\n",
        clear_keys=("ZZZ_DRIVE_ID",),
    )
    monkeypatch.setenv("TIMMY_ALLOW_WORKSPACE_OVERRIDE", "1")
    monkeypatch.setenv("TIMMY_ALLOW_BOOTSTRAP", "1")
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

    from pipeline.exceptions import ConfigError

    # Act & Assert: con require_drive_env=True deve alzare ConfigError chiaro (no KeyError)
    with pytest.raises(ConfigError) as ei:
        ClientContext.load(slug="dummy", require_drive_env=True, run_id=None)
    msg = str(ei.value)
    # Messaggio informativo: cita almeno una delle variabili mancanti
    assert "Prerequisiti Drive mancanti" in msg
    assert ("SERVICE_ACCOUNT_FILE" in msg) or ("DRIVE_ID" in msg)
    assert getattr(ei.value, "code", None) == "drive.env.missing"
