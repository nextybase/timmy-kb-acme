# SPDX-License-Identifier: GPL-3.0-or-later
# src/pipeline/proc_utils.py
"""
Utility robuste e riutilizzabili per l'esecuzione di subprocess con timeout, retry e logging.
Pensato per sostituire le chiamate dirette a `subprocess.run` in moduli come:
- gitbook_preview.py (Docker build/run)
- github_utils.py (git add/commit/push)
- tools/cleanup_repo.py (facoltativo)

API principali:
- run_cmd(...): esegue un comando con timeout, retry con backoff e redazione sicura nei log
- wait_for_port(...): attende che una porta TCP risponda entro una finestra temporale
"""

from __future__ import annotations

from typing import Sequence, Mapping, Optional, Callable, Any, Tuple
import os
import time
import shlex
import socket
import subprocess
import logging

try:
    # Preferiamo gli helper esistenti per coerenza con la pipeline
    from .env_utils import get_int, redact_secrets  # type: ignore
except Exception:  # pragma: no cover
    # Fallback conservativo per ambienti minimi (test stand-alone)
    def get_int(key: str, default: Optional[int] = None, *, required: bool = False) -> Optional[int]:
        val = os.getenv(key, None)
        try:
            return int(str(val).strip()) if val not in (None, "") else default
        except Exception:
            return default

    def redact_secrets(text: str) -> str:
        return text

__all__ = ["CmdError", "run_cmd", "wait_for_port"]


# --------------------------------------- Error ---------------------------------------

class CmdError(RuntimeError):
    """Errore di comando con contesto ricco per diagnosi."""

    def __init__(
        self,
        msg: str,
        *,
        cmd: Sequence[str] | str,
        code: Optional[int] = None,
        stdout: Optional[str] = None,
        stderr: Optional[str] = None,
        timeout: bool = False,
        attempt: int = 1,
        attempts: int = 1,
        duration_ms: Optional[int] = None,
        op: Optional[str] = None,
    ) -> None:
        super().__init__(msg)
        self.cmd = cmd
        self.code = code
        self.stdout = stdout
        self.stderr = stderr
        self.timeout = timeout
        self.attempt = attempt
        self.attempts = attempts
        self.duration_ms = duration_ms
        self.op = op


# ------------------------------------- Helpers --------------------------------------

def _now_ms() -> int:
    return int(time.time() * 1000)


def _to_argv(cmd: Sequence[str] | str) -> Sequence[str]:
    if isinstance(cmd, str):
        # Nota: shlex.split è sufficiente nel nostro contesto; i call-site possono passare già la lista
        return shlex.split(cmd)
    return list(cmd)


def _render_cmd_for_log(argv: Sequence[str], redactor: Callable[[str], str]) -> str:
    # Rappresentiamo il comando come stringa shell-quoted, poi redigiamo eventuali segreti
    rendered = " ".join(shlex.quote(a) for a in argv)
    return redactor(rendered)


def _tail(text: Optional[str], *, limit: int = 2000) -> Optional[str]:
    if text is None:
        return None
    # Limite in caratteri (non byte) per semplicità; sufficiente per log diagnostici
    if len(text) <= limit:
        return text
    return text[-limit:]


def _merge_env(base: Mapping[str, str], extra: Optional[Mapping[str, str]]) -> Mapping[str, str]:
    if not extra:
        return dict(base)
    merged = dict(base)
    merged.update(extra)
    return merged


def _default_timeout_for(op: Optional[str]) -> int:
    """
    Ritorna un timeout di default (secondi) in base all'operazione.
    - Docker: DOCKER_CMD_TIMEOUT (default 90)
    - Git:    GIT_CMD_TIMEOUT    (default 120)
    - Altro:  PROC_CMD_TIMEOUT   (default 60)
    """
    if op and "docker" in op:
        return int(get_int("DOCKER_CMD_TIMEOUT", 90) or 90)
    if op and ("git" in op or op in {"push", "commit", "add"}):
        return int(get_int("GIT_CMD_TIMEOUT", 120) or 120)
    return int(get_int("PROC_CMD_TIMEOUT", 60) or 60)


# ------------------------------------- Public API -----------------------------------

def run_cmd(
    cmd: Sequence[str] | str,
    *,
    timeout: Optional[float] = None,
    retries: int = 0,
    backoff: float = 1.5,
    cwd: Optional[str] = None,
    env: Optional[Mapping[str, str]] = None,
    capture: bool = True,
    redactor: Optional[Callable[[str], str]] = None,
    logger: Optional[logging.Logger] = None,
    op: Optional[str] = None,
) -> subprocess.CompletedProcess:
    """
    Esegue un comando di sistema con timeout, retry con backoff e redazione sicura.

    Args:
        cmd: comando (lista argv o stringa shell-like).
        timeout: timeout in secondi; se None, deriva da variabili d'ambiente in base a `op`.
        retries: numero di retry su errore/timeout (totale tentativi = retries + 1).
        backoff: moltiplicatore del delay tra i tentativi (es. 1.5).
        cwd: working directory.
        env: variabili di ambiente addizionali da unire a `os.environ`.
        capture: se True, cattura stdout/stderr (text mode).
        redactor: funzione per redigere segreti nei log (default: env_utils.redact_secrets).
        logger: logger strutturato per log diagnostici (opzionale).
        op: etichetta operativa (es. "docker build", "git push") per log e default timeout.

    Returns:
        subprocess.CompletedProcess in caso di successo (returncode == 0).

    Raises:
        CmdError: in caso di timeout o returncode != 0 al termine dei tentativi.
    """
    argv = _to_argv(cmd)
    redactor = redactor or redact_secrets
    attempts = max(1, int(retries) + 1)
    op_label = op or (argv[0] if argv else "cmd")
    eff_timeout = float(timeout if timeout is not None else _default_timeout_for(op_label))
    merged_env = _merge_env(os.environ, env)

    delay_s: float = 0.0
    last_err: Optional[CmdError] = None

    for attempt in range(1, attempts + 1):
        if delay_s > 0:
            time.sleep(delay_s)

        start = _now_ms()
        try:
            if logger:
                logger.debug(
                    "run_cmd.start",
                    extra={
                        "op": op_label,
                        "attempt": attempt,
                        "attempts": attempts,
                        "cwd": cwd or "",
                        "timeout_s": eff_timeout,
                        "cmd": _render_cmd_for_log(argv, redactor),
                    },
                )

            cp = subprocess.run(
                argv,
                cwd=cwd,
                env=merged_env,
                capture_output=capture,
                text=True,
                timeout=eff_timeout,
                check=False,
            )
            duration = _now_ms() - start

            if cp.returncode == 0:
                if logger:
                    logger.info(
                        "run_cmd.ok",
                        extra={
                            "op": op_label,
                            "attempt": attempt,
                            "attempts": attempts,
                            "duration_ms": duration,
                            "returncode": 0,
                        },
                    )
                return cp

            # Non-zero exit
            err = CmdError(
                f"Comando fallito (exit {cp.returncode}): {op_label}",
                cmd=argv,
                code=cp.returncode,
                stdout=_tail(cp.stdout),
                stderr=_tail(cp.stderr),
                timeout=False,
                attempt=attempt,
                attempts=attempts,
                duration_ms=duration,
                op=op_label,
            )
            last_err = err

            if logger:
                logger.warning(
                    "run_cmd.fail",
                    extra={
                        "op": op_label,
                        "attempt": attempt,
                        "attempts": attempts,
                        "duration_ms": duration,
                        "returncode": cp.returncode,
                        "stderr_tail": redactor(_tail(cp.stderr) or ""),
                    },
                )

        except subprocess.TimeoutExpired as te:
            duration = _now_ms() - start
            err = CmdError(
                f"Timeout esecuzione: {op_label} ({eff_timeout:.1f}s)",
                cmd=argv,
                code=None,
                stdout=None,
                stderr=None,
                timeout=True,
                attempt=attempt,
                attempts=attempts,
                duration_ms=duration,
                op=op_label,
            )
            last_err = err

            if logger:
                logger.error(
                    "run_cmd.timeout",
                    extra={
                        "op": op_label,
                        "attempt": attempt,
                        "attempts": attempts,
                        "duration_ms": duration,
                        "timeout_s": eff_timeout,
                        "cmd": _render_cmd_for_log(argv, redactor),
                    },
                )

        # Retry?
        if attempt < attempts:
            delay_s = delay_s * backoff if delay_s > 0 else 1.0  # 1s → 1.5s → 2.25s …
            continue

        # Fine tentativi → solleva l'ultimo errore
        assert last_err is not None
        raise last_err


def wait_for_port(host: str, port: int, timeout: float = 30.0, interval: float = 0.5, logger: Optional[logging.Logger] = None) -> None:
    """
    Attende che una porta TCP sia raggiungibile entro `timeout` secondi.
    Solleva `TimeoutError` se la porta non risponde in tempo.
    """
    deadline = time.time() + float(timeout)
    last_exc: Optional[Exception] = None

    while time.time() < deadline:
        try:
            with socket.create_connection((host, int(port)), timeout=interval):
                if logger:
                    logger.info("wait_for_port.ok", extra={"host": host, "port": port})
                return
        except Exception as e:
            last_exc = e
            time.sleep(interval)

    # timeout
    if logger:
        logger.error("wait_for_port.timeout", extra={"host": host, "port": port, "timeout_s": timeout})
    raise TimeoutError(f"Porta non raggiungibile: {host}:{port} entro {timeout}s")
