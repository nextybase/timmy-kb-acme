# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from pathlib import Path

import pytest

from pipeline.exceptions import ConfigError
from pipeline import observability_config as oc


def test_load_observability_settings_missing_file_raises(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg_path = tmp_path / "missing_observability.yaml"
    monkeypatch.setenv("TIMMY_OBSERVABILITY_CONFIG", str(cfg_path))

    with pytest.raises(ConfigError, match="Configurazione osservabilita' mancante"):
        oc.load_observability_settings()


def test_load_observability_settings_invalid_yaml_raises(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg_path = tmp_path / "observability.yaml"
    cfg_path.write_text("stack_enabled: [\n", encoding="utf-8")
    monkeypatch.setenv("TIMMY_OBSERVABILITY_CONFIG", str(cfg_path))

    with pytest.raises(ConfigError, match="error_type="):
        oc.load_observability_settings()


def test_update_observability_settings_path_escape_raises(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg_path = tmp_path / "observability.yaml"
    cfg_path.write_text("stack_enabled: false\n", encoding="utf-8")
    monkeypatch.setenv("TIMMY_OBSERVABILITY_CONFIG", str(cfg_path))

    def _raise_path_error(parent: Path, candidate: Path) -> Path:
        raise ConfigError(
            f"Percorso osservabilita' non valido: {candidate}",
            file_path=str(candidate),
        )

    monkeypatch.setattr(oc, "_ensure_within_and_resolve", _raise_path_error)

    with pytest.raises(ConfigError, match="Percorso osservabilita' non valido"):
        oc.update_observability_settings(stack_enabled=True)
