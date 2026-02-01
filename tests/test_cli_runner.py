# SPDX-License-Identifier: GPL-3.0-or-later
# tests/test_cli_runner.py
from __future__ import annotations

import argparse
import sys

import pytest

from pipeline.cli_runner import run_cli_orchestrator
from pipeline.exceptions import ConfigError, exit_code_for


def _capture_sys_exit(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    codes: list[int] = []

    def _fake_exit(code: int = 0) -> None:
        codes.append(code)
        raise SystemExit(code)

    monkeypatch.setattr(sys, "exit", _fake_exit)
    return codes


def test_run_cli_orchestrator_success(monkeypatch: pytest.MonkeyPatch) -> None:
    codes = _capture_sys_exit(monkeypatch)

    def _parse() -> argparse.Namespace:
        return argparse.Namespace()

    def _main(args: argparse.Namespace) -> None:
        assert isinstance(args, argparse.Namespace)

    with pytest.raises(SystemExit):
        run_cli_orchestrator("dummy", _parse, _main)

    assert codes == [0]


def test_run_cli_orchestrator_respects_return_code(monkeypatch: pytest.MonkeyPatch) -> None:
    codes = _capture_sys_exit(monkeypatch)

    def _parse() -> argparse.Namespace:
        return argparse.Namespace()

    def _main(_: argparse.Namespace) -> int:
        return 5

    with pytest.raises(SystemExit):
        run_cli_orchestrator("dummy", _parse, _main)

    assert codes == [5]


def test_run_cli_orchestrator_maps_config_error(monkeypatch: pytest.MonkeyPatch) -> None:
    codes = _capture_sys_exit(monkeypatch)

    def _parse() -> argparse.Namespace:
        return argparse.Namespace()

    def _main(_: argparse.Namespace) -> None:
        raise ConfigError("boom")

    with pytest.raises(SystemExit):
        run_cli_orchestrator("dummy", _parse, _main)

    assert codes == [exit_code_for(ConfigError("boom"))]


def test_run_cli_orchestrator_maps_generic_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    codes = _capture_sys_exit(monkeypatch)

    class CustomError(Exception):
        pass

    def _parse() -> argparse.Namespace:
        return argparse.Namespace()

    def _main(_: argparse.Namespace) -> None:
        raise CustomError("boom")

    with pytest.raises(SystemExit):
        run_cli_orchestrator("dummy", _parse, _main)

    assert codes == [exit_code_for(CustomError("boom"))]


def test_run_cli_orchestrator_keyboard_interrupt(monkeypatch: pytest.MonkeyPatch) -> None:
    codes = _capture_sys_exit(monkeypatch)

    def _parse() -> argparse.Namespace:
        return argparse.Namespace()

    def _main(_: argparse.Namespace) -> None:
        raise KeyboardInterrupt()

    with pytest.raises(SystemExit):
        run_cli_orchestrator("dummy", _parse, _main)

    assert codes == [130]
