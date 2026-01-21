# SPDX-License-Identifier: GPL-3.0-only
# tests/test_cli_gen_vision_yaml.py
from __future__ import annotations

import builtins
import importlib
import sys
from pathlib import Path

import pytest

import tools.gen_vision_yaml as cli
from pipeline.exceptions import ConfigError
from semantic.vision_provision import HaltError


def _make_pdf(tmp_path: Path, name: str = "vision.pdf") -> Path:
    base_dir = tmp_path / "output" / "timmy-kb-dummy-srl"
    base_dir.mkdir(parents=True, exist_ok=True)
    p = base_dir / name
    # Non serve un PDF valido: il CLI verifica solo l'esistenza del file,
    # la business logic è mockata in questi test.
    p.write_bytes(b"%PDF-FAKE%")
    return p


def test_import_cli_does_not_require_streamlit(monkeypatch: pytest.MonkeyPatch):
    """
    Importare il tool non deve tentare di caricare streamlit (headless-safe).
    """
    sys.modules.pop("tools.gen_vision_yaml", None)

    real_import = builtins.__import__

    def guard(name, *args, **kwargs):
        if name == "streamlit":
            raise ImportError("streamlit not available in headless mode")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guard)
    importlib.import_module("tools.gen_vision_yaml")


def test_cli_success_returns_zero(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys):
    """
    Caso OK: provision_from_vision restituisce i path degli YAML → exit code 0.
    """
    monkeypatch.chdir(tmp_path)
    pdf = _make_pdf(tmp_path)

    def _fake_provision(ctx, logger, *, slug: str, pdf_path: Path, **kwargs):
        # Non scriviamo davvero file: al CLI basta il dict di ritorno
        return {
            "mapping": str(tmp_path / "semantic_mapping.yaml"),
        }

    monkeypatch.setattr(cli, "run_vision_with_gating", _fake_provision)

    argv_bak = sys.argv[:]
    try:
        sys.argv = ["gen_vision_yaml.py", "--slug", "dummy-srl", "--pdf", str(pdf)]
        rc = cli.main()
        assert rc == 0
        out, err = capsys.readouterr()
        # Sanity check rispettando sia log strutturato che console fallback
        assert (
            "vision_yaml_generated" in out
            or "vision_yaml_generated" in err
            or "YAML generati" in out
            or "YAML generati" in err
        )
    finally:
        sys.argv = argv_bak


def test_cli_halt_returns_two(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys):
    """
    Caso HALT: l'assistente segnala Vision insufficiente → exit code 2.
    """
    monkeypatch.chdir(tmp_path)
    pdf = _make_pdf(tmp_path)

    def _raise_halt(ctx, logger, *, slug: str, pdf_path: Path, **kwargs):
        raise HaltError("Integra Mission e Framework etico e riprova.", {"sections": ["Mission", "Framework etico"]})

    monkeypatch.setattr(cli, "run_vision_with_gating", _raise_halt)

    argv_bak = sys.argv[:]
    try:
        sys.argv = ["gen_vision_yaml.py", "--slug", "dummy-srl", "--pdf", str(pdf)]
        rc = cli.main()
        assert rc == 2
        out, err = capsys.readouterr()
        assert (
            "vision_yaml_halt" in out
            or "vision_yaml_halt" in err
            or "HALT Vision" in out
            or "HALT Vision" in err
            or "HaltError" in err
            or "Integra Mission" in err
            or "Integra Mission" in out
        )
    finally:
        sys.argv = argv_bak


def test_cli_config_error_returns_one(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys):
    """
    Caso errore di configurazione (es. assistant_id mancante) → exit code 1.
    """
    monkeypatch.chdir(tmp_path)
    pdf = _make_pdf(tmp_path)

    def _raise_cfg(ctx, logger, *, slug: str, pdf_path: Path, **kwargs):
        raise ConfigError("Assistant ID non configurato")

    monkeypatch.setattr(cli, "run_vision_with_gating", _raise_cfg)

    argv_bak = sys.argv[:]
    try:
        sys.argv = ["gen_vision_yaml.py", "--slug", "dummy-srl", "--pdf", str(pdf)]
        rc = cli.main()
        assert rc == 1
        out, err = capsys.readouterr()
        # Accetta evento strutturato o messaggio testuale/trace
        assert (
            "vision_yaml_config_error" in out
            or "vision_yaml_config_error" in err
            or "Errore configurazione" in out
            or "Errore configurazione" in err
            or "ConfigError" in err
            or "Assistant ID non configurato" in err
            or "Assistant ID non configurato" in out
        )
    finally:
        sys.argv = argv_bak


def test_cli_missing_pdf_returns_one(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys):
    """
    PDF non esistente → exit code 1 (il CLI fa il controllo prima di chiamare provision).
    """
    monkeypatch.chdir(tmp_path)
    missing = tmp_path / "output" / "timmy-kb-dummy-srl" / "missing.pdf"

    # Anche se patchiamo provision, NON deve essere chiamato quando il file manca
    called = {"value": False}

    def _should_not_be_called(*a, **k):
        called["value"] = True
        return {}

    monkeypatch.setattr(cli, "run_vision_with_gating", _should_not_be_called)

    argv_bak = sys.argv[:]
    try:
        sys.argv = ["gen_vision_yaml.py", "--slug", "dummy-srl", "--pdf", str(missing)]
        rc = cli.main()
        assert rc == 1
        assert called["value"] is False
        out, err = capsys.readouterr()
        combined = out + err
        assert "vision_yaml.pdf_not_found" in combined
    finally:
        sys.argv = argv_bak
