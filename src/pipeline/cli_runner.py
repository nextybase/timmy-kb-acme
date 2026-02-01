# SPDX-License-Identifier: GPL-3.0-or-later
# src/pipeline/cli_runner.py
from __future__ import annotations

import argparse
import sys
from typing import Callable, NoReturn

from pipeline.exceptions import ConfigError, PipelineError, exit_code_for

CliMainFn = Callable[[argparse.Namespace], int | None]
ParseArgsFn = Callable[[], argparse.Namespace]


def run_cli_orchestrator(entry_name: str, parse_args: ParseArgsFn, main_fn: CliMainFn) -> NoReturn:
    """Wrapper condiviso per orchestratori CLI basati su argparse.

    - Esegue il parsing degli argomenti tramite `parse_args`.
    - Passa il namespace a `main_fn`.
    - Accetta un return value opzionale `int` da `main_fn` per exit code custom.
    - Converte le eccezioni note in exit code coerenti tramite `exit_code_for`.
    - Gestisce `KeyboardInterrupt` restituendo 130 (Ctrl+C).
    """

    args = parse_args()
    setattr(args, "_entry_name", entry_name)

    try:
        result = main_fn(args)
    except KeyboardInterrupt:
        sys.exit(130)
    except (ConfigError, PipelineError) as exc:
        sys.exit(exit_code_for(exc))
    except Exception as exc:  # noqa: BLE001 - ultima linea di difesa
        sys.exit(exit_code_for(exc))

    if isinstance(result, int):
        sys.exit(result)

    sys.exit(0)


__all__ = ["run_cli_orchestrator", "CliMainFn", "ParseArgsFn"]
