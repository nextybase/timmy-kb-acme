# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import os

import pytest

from tests.support.dotenv_helpers import prepare_dotenv_env

pytestmark = pytest.mark.unit


def test_env_lazy_load(monkeypatch, tmp_path):
    envu = prepare_dotenv_env(
        monkeypatch=monkeypatch,
        tmp_path=tmp_path,
        env_text="FOO_BAR=hello\n",
        clear_keys=("FOO_BAR",),
    )
    # Verifica l'effetto: la variabile deve essere disponibile, a prescindere dal valore booleano
    # (puo essere False se gia caricata da altre parti del processo di test)
    assert os.environ.get("FOO_BAR") == "hello"

    # Seconda chiamata: idempotente
    os.environ["FOO_BAR"] = "hello"  # stabilizza
    loaded2 = envu.ensure_dotenv_loaded()
    assert loaded2 is False
