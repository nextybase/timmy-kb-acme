# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import os
from pathlib import Path

import pytest

import pipeline.env_utils as envu

pytestmark = pytest.mark.unit


def test_env_lazy_load(monkeypatch, tmp_path: Path):
    # Prepara una .env in una cartella isolata
    monkeypatch.chdir(tmp_path)
    env_file = tmp_path / ".env"
    env_file.write_text("FOO_BAR=hello\n", encoding="utf-8")

    # Assicurati che non sia presente prima
    if "FOO_BAR" in os.environ:
        del os.environ["FOO_BAR"]

    # Import e prima chiamata: deve caricare
    loaded = envu.ensure_dotenv_loaded()
    if not loaded:
        import importlib as _il

        _il.reload(envu)
        envu.ensure_dotenv_loaded()
    # Verifica l'effetto: la variabile deve essere disponibile, a prescindere dal valore booleano
    # (può essere False se già caricata da altre parti del processo di test)
    assert os.environ.get("FOO_BAR") == "hello"

    # Seconda chiamata: idempotente
    os.environ["FOO_BAR"] = "hello"  # stabilizza
    loaded2 = envu.ensure_dotenv_loaded()
    assert loaded2 is False
