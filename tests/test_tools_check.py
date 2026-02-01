# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import pytest

from pipeline.exceptions import ConfigError

# Casi che DEVONO essere riconosciuti dal gate:
CASES_TRUE = [
    "Vision già eseguita per questo slug",  # accento + 'eseguita'
    "Errore vision gia eseguita, file=vision_hash",  # senza accento + marker
    "VISION GIA ESEGUITA",  # maiuscole
    "Vision già eseguito",  # maschile 'eseguito'
    "Qualcosa... VISION GIÀ ESEGUITA! altro",  # rumore attorno
    "file=vision_hash",  # solo marker
]

# Casi che NON devono attivare il gate:
CASES_FALSE = [
    "Altro errore Vision",  # generico
    "Vision completata",  # semantica diversa
    "Vision gia eseguire",  # 'eseguire' non 'eseguit*'
    "gia eseguita senza parola",  # manca 'vision'
]


@pytest.mark.parametrize(
    "message",
    CASES_TRUE,
    ids=[
        "accento_eseguita",
        "no_accento_con_marker",
        "upper_case",
        "maschile_eseguito",
        "rumore_attorno",
        "solo_marker",
    ],
)
def test_is_gate_error_true_with_runtime_error(message: str) -> None:
    module = pytest.importorskip("ui.pages.tools_check")
    err = RuntimeError(message)
    assert module._is_gate_error(err)


def test_is_gate_error_true_with_config_error() -> None:
    module = pytest.importorskip("ui.pages.tools_check")
    # il codice reale intercetta ConfigError: verifichiamo che il tipo non cambi l'esito
    err = ConfigError("Vision già eseguita")
    assert module._is_gate_error(err)


@pytest.mark.parametrize(
    "message",
    CASES_FALSE,
    ids=[
        "generico",
        "completata",
        "forma_verbo_diversa",
        "manca_parola_vision",
    ],
)
def test_is_gate_error_false(message: str) -> None:
    module = pytest.importorskip("ui.pages.tools_check")
    err = RuntimeError(message)
    assert not module._is_gate_error(err)


def test_is_gate_error_true_with_sentinel_file_path(tmp_path) -> None:
    """Se l'eccezione porta file_path che punta al sentinel .vision_hash,
    deve essere riconosciuta come gate a prescindere dal messaggio."""
    module = pytest.importorskip("ui.pages.tools_check")
    e = ConfigError("Qualsiasi messaggio")
    sentinel = tmp_path / ".vision_hash"
    sentinel.write_text("")  # non strettamente necessario, ma rende il path concreto
    setattr(e, "file_path", str(sentinel))
    assert module._is_gate_error(e)
