import os
from pathlib import Path

import pytest


def test_get_env_var_loads_dotenv(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Arrange: create a temporary .env with a variable not present in process env
    env_text = "DRIVE_ID=drive-from-dotenv\nSERVICE_ACCOUNT_FILE=C:/sa.json\n"
    (tmp_path / ".env").write_text(env_text, encoding="utf-8")
    # Ensure process env is clean for these keys
    monkeypatch.delenv("DRIVE_ID", raising=False)
    monkeypatch.delenv("SERVICE_ACCOUNT_FILE", raising=False)
    # Change CWD to the tmp directory so loader finds .env
    monkeypatch.chdir(tmp_path)

    from pipeline.env_utils import get_env_var

    # Act: call getter (should lazily load .env)
    drive_id = get_env_var("DRIVE_ID", required=True)
    sa_file = get_env_var("SERVICE_ACCOUNT_FILE", required=True)

    # Assert
    assert drive_id == "drive-from-dotenv"
    assert sa_file == "C:/sa.json"


def test_client_context_load_reads_dotenv(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Arrange: repo root with only a .env file
    (tmp_path / ".env").write_text("DRIVE_ID=abc123\n", encoding="utf-8")
    monkeypatch.delenv("DRIVE_ID", raising=False)
    monkeypatch.chdir(tmp_path)

    from pipeline.context import ClientContext

    # Act: load context (should pick up .env lazily via env getters)
    ctx = ClientContext.load(slug="dummy", interactive=False, require_env=True, run_id=None)

    # Assert: DRIVE_ID available via ctx.env (or process env)
    assert (ctx.env.get("DRIVE_ID") or os.environ.get("DRIVE_ID")) == "abc123"
