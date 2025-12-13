# SPDX-License-Identifier: GPL-3.0-or-later
# src/ai/codex_runner.py
from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

_TRUNCATION_LIMIT = 200_000


def _truncate_output(value: str) -> str:
    if len(value) <= _TRUNCATION_LIMIT:
        return value
    return f"{value[:_TRUNCATION_LIMIT]}...[TRUNCATED]"


@dataclass(frozen=True)
class StructuredResult:
    ok: bool
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: int
    error: str | None = None


def run_codex_cli(
    prompt: str,
    *,
    cwd: Path,
    cmd: Sequence[str],
    timeout_s: int = 120,
    env: dict[str, str] | None = None,
) -> StructuredResult:
    """
    Esegue un comando CLI controllato e restituisce un risultato strutturato.

    Args:
        prompt: descrizione testuale del cambio previsto (deve essere non vuoto).
        cwd: directory da cui eseguire la CLI (deve esistere).
        cmd: sequenza di token del comando (non vuota, shell=False).
        timeout_s: timeout in secondi.
        env: mappa di variabili ambiente aggiunte (senza side-effect globali).
    """
    if not prompt.strip():
        raise ValueError("Il prompt non può essere vuoto.")
    if not cwd.is_dir():
        raise ValueError(f"cwd non esistente: {cwd}")
    if not cmd:
        raise ValueError("cmd non può essere vuoto.")

    start = time.perf_counter()
    try:
        result = subprocess.run(  # noqa: S603
            list(cmd),
            cwd=str(cwd),
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            shell=False,
        )
        duration = int((time.perf_counter() - start) * 1_000)
        stdout = _truncate_output(result.stdout or "")
        stderr = _truncate_output(result.stderr or "")
        ok = result.returncode == 0
        return StructuredResult(
            ok=ok,
            exit_code=result.returncode,
            stdout=stdout,
            stderr=stderr,
            duration_ms=duration,
        )
    except subprocess.TimeoutExpired as exc:
        duration = int((time.perf_counter() - start) * 1_000)
        stdout = _truncate_output(exc.stdout or "")
        stderr = _truncate_output(exc.stderr or "")
        return StructuredResult(
            ok=False,
            exit_code=-1,
            stdout=stdout,
            stderr=stderr,
            duration_ms=duration,
            error=f"timeout dopo {timeout_s}s",
        )
    except Exception as exc:
        duration = int((time.perf_counter() - start) * 1_000)
        return StructuredResult(
            ok=False,
            exit_code=-1,
            stdout="",
            stderr="",
            duration_ms=duration,
            error=str(exc),
        )
