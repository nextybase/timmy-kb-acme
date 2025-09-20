from __future__ import annotations

import os
from pathlib import Path

from pipeline.env_utils import ensure_dotenv_loaded


def test_env_lazy_load(monkeypatch, tmp_path: Path):
    # Prepara una .env in una cartella isolata
    monkeypatch.chdir(tmp_path)
    env_file = tmp_path / ".env"
    env_file.write_text("FOO_BAR=hello\n", encoding="utf-8")

    # Assicurati che non sia presente prima
    if "FOO_BAR" in os.environ:
        del os.environ["FOO_BAR"]

    # Import e prima chiamata: deve caricare
    loaded1 = ensure_dotenv_loaded()
    assert loaded1 is True
    assert os.environ.get("FOO_BAR") == "hello"

    # Seconda chiamata: idempotente
    os.environ["FOO_BAR"] = "hello"  # stabilizza
    loaded2 = ensure_dotenv_loaded()
    assert loaded2 is False
