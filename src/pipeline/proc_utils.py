# SPDX-License-Identifier: GPL-3.0-or-later
# src/pipeline/proc_utils.py
"""Utility robuste e riutilizzabili per eseguire comandi di sistema con timeout, retry, backoff ed
eventi di logging strutturato. Sostituisce l'uso diretto di `subprocess.run` nei moduli della
pipeline (es. preview HonKit via Docker, comandi SCM, ecc.).

Funzionalità principali
-----------------------
- run_cmd(...): wrapper con timeout (derivabile per tipo operazione), retry con backoff,
  cattura di stdout/stderr, redazione sicura dei log e contesto ricco in caso di errore.
- wait_for_port(...): attende la raggiungibilità di una porta TCP con polling e timebox.
- docker_available(...): rileva se Docker è disponibile ed eseguibile.
- run_docker_preview(...): esegue build + serve HonKit in un container Docker in modalità
  detached e attende la readiness (porta up); gestisce cleanup best-effort su failure.
- stop_docker_preview(...): prova a fermare/rimuovere il container di preview (best-effort).

Note:
- Nessuna retro-compatibilità con vecchie funzioni legacy.
- Il redattore di default per i log è `pipeline.logging_utils.redact_secrets`.
"""

from __future__ import annotations

import logging
import os
import shlex
import socket
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Optional, Sequence

from .env_utils import get_int
from .logging_utils import redact_secrets

__all__ = [
    "CmdError",
    "run_cmd",
    "wait_for_port",
    "docker_available",
    "run_docker_preview",
    "stop_docker_preview",
    "CmdContext",
    "cmd_attempt",
    "retry_loop",
]


# --------------------------------------- Error ---------------------------------------


class CmdError(RuntimeError):
    """Errore di comando con contesto ricco per diagnosi (stdout/stderr tail, durata, tentativi)."""

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
        # i call-site possono passare già una lista; altrimenti shlex.split è sufficiente
        return shlex.split(cmd)
    return list(cmd)


def _render_cmd_for_log(argv: Sequence[str], redactor: Callable[[str], str]) -> str:
    rendered = " ".join(shlex.quote(a) for a in argv)
    return redactor(rendered)


def _tail(text: Optional[str], *, limit: int = 2000) -> Optional[str]:
    if text is None:
        return None
    return text if len(text) <= limit else text[-limit:]


def _merge_env(base: Mapping[str, str], extra: Optional[Mapping[str, str]]) -> Mapping[str, str]:
    """Merge di env, garantendo sempre chiavi/valori `str` come richiesto da subprocess."""
    merged: dict[str, str] = {str(k): str(v) for k, v in dict(base).items()}
    if extra:
        for k, v in extra.items():
            if v is None:
                continue
            merged[str(k)] = str(v)
    return merged


def _default_timeout_for(op: Optional[str]) -> int:
    """Timeout di default (secondi) basato sull'operazione.

    - Docker: DOCKER_CMD_TIMEOUT (default 90)
    - Git:    GIT_CMD_TIMEOUT    (default 120)
    - Altro:  PROC_CMD_TIMEOUT   (default 60)
    """
    if op and "docker" in op:
        return int(get_int("DOCKER_CMD_TIMEOUT", 90) or 90)
    if op and ("git" in op or op in {"commit", "add"}):
        return int(get_int("GIT_CMD_TIMEOUT", 120) or 120)
    return int(get_int("PROC_CMD_TIMEOUT", 60) or 60)


# ----------------------------------- Command core -----------------------------------


@dataclass(frozen=True)
class CmdContext:
    argv: Sequence[str]
    op: str
    attempts: int
    timeout_s: float
    cwd: Optional[str]
    cwd_log: str
    env: Mapping[str, str]
    capture: bool
    redactor: Callable[[str], str]
    logger: Optional[logging.Logger]
    backoff: float

    def command_for_log(self) -> str:
        return _render_cmd_for_log(self.argv, self.redactor)


def cmd_attempt(context: CmdContext, attempt: int) -> subprocess.CompletedProcess[Any]:
    """Esegue un singolo tentativo di comando e gestisce logging/risposte."""
    start = _now_ms()
    if context.logger:
        context.logger.debug(
            "run_cmd.start",
            extra={
                "op": context.op,
                "attempt": attempt,
                "attempts": context.attempts,
                "cwd": context.cwd_log,
                "timeout_s": context.timeout_s,
                "cmd": context.command_for_log(),
            },
        )

    try:
        cp = subprocess.run(
            context.argv,
            cwd=context.cwd,
            env=context.env,
            capture_output=context.capture,
            text=context.capture,
            timeout=context.timeout_s,
            check=False,
        )
    except subprocess.TimeoutExpired:
        duration = _now_ms() - start
        err = CmdError(
            f"Timeout esecuzione: {context.op} ({context.timeout_s:.1f}s)",
            cmd=context.argv,
            code=None,
            stdout=None,
            stderr=None,
            timeout=True,
            attempt=attempt,
            attempts=context.attempts,
            duration_ms=duration,
            op=context.op,
        )
        if context.logger:
            context.logger.error(
                "run_cmd.timeout",
                extra={
                    "op": context.op,
                    "attempt": attempt,
                    "attempts": context.attempts,
                    "duration_ms": duration,
                    "timeout_s": context.timeout_s,
                    "cmd": context.command_for_log(),
                    "cwd": context.cwd_log,
                },
            )
        raise err

    duration = _now_ms() - start

    if cp.returncode == 0:
        if context.logger:
            context.logger.info(
                "run_cmd.ok",
                extra={
                    "op": context.op,
                    "attempt": attempt,
                    "attempts": context.attempts,
                    "duration_ms": duration,
                    "returncode": 0,
                },
            )
        return cp

    err = CmdError(
        f"Comando fallito (exit {cp.returncode}): {context.op}",
        cmd=context.argv,
        code=cp.returncode,
        stdout=_tail(cp.stdout),
        stderr=_tail(cp.stderr),
        timeout=False,
        attempt=attempt,
        attempts=context.attempts,
        duration_ms=duration,
        op=context.op,
    )

    if context.logger:
        context.logger.warning(
            "run_cmd.fail",
            extra={
                "op": context.op,
                "attempt": attempt,
                "attempts": context.attempts,
                "duration_ms": duration,
                "returncode": cp.returncode,
                "stderr_tail": context.redactor(_tail(cp.stderr) or ""),
                "stdout_tail": context.redactor(_tail(cp.stdout) or ""),
            },
        )
    raise err


def retry_loop(context: CmdContext) -> subprocess.CompletedProcess[Any]:
    """Gestisce il ciclo di retry/backoff utilizzando cmd_attempt."""
    delay_s: float = 0.0
    last_error: Optional[CmdError] = None

    for attempt in range(1, context.attempts + 1):
        if delay_s > 0:
            time.sleep(delay_s)
        try:
            return cmd_attempt(context, attempt)
        except CmdError as exc:
            last_error = exc
            if attempt >= context.attempts:
                raise
            delay_s = delay_s * context.backoff if delay_s > 0 else 1.0
            continue

    if last_error is not None:
        raise last_error
    raise CmdError("Unexpected state: no result from retry_loop", cmd=context.argv, op=context.op)


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
) -> subprocess.CompletedProcess[Any]:
    """Esegue un comando di sistema con timeout, retry con backoff e redazione sicura.

    Args:
        cmd: comando (lista argv o stringa shell-like).
        timeout: timeout in secondi; se None, deriva da variabili d'ambiente in base a `op`.
        retries: numero di retry su errore/timeout (totale tentativi = retries + 1).
        backoff: moltiplicatore del delay tra i tentativi (es. 1.5).
        cwd: working directory.
        env: variabili di ambiente addizionali (unite a `os.environ`, casting a str garantito).
        capture: se True, cattura stdout/stderr (text mode).
        redactor: funzione per redigere segreti nei log (default: `logging_utils.redact_secrets`).
        logger: logger strutturato per log diagnostici (opzionale).
        op: etichetta operativa (es. "docker build", "git status") per log e default timeout.

    Restituisce:
        subprocess.CompletedProcess in caso di successo (returncode == 0).

    Raises:
        CmdError: in caso di timeout o returncode != 0 al termine dei tentativi.
    """
    argv = list(_to_argv(cmd))
    redactor = redactor or redact_secrets
    attempts = max(1, int(retries) + 1)
    op_label = op or (argv[0] if argv else "cmd")
    eff_timeout = float(timeout if timeout is not None else _default_timeout_for(op_label))
    merged_env = _merge_env(os.environ, env)

    cwd_log = ""
    if cwd:
        try:
            cwd_log = str(Path(cwd).resolve())
        except Exception:
            cwd_log = str(cwd)

    context = CmdContext(
        argv=tuple(argv),
        op=op_label,
        attempts=attempts,
        timeout_s=eff_timeout,
        cwd=cwd,
        cwd_log=cwd_log,
        env=merged_env,
        capture=bool(capture),
        redactor=redactor,
        logger=logger,
        backoff=float(backoff),
    )

    return retry_loop(context)


def wait_for_port(
    host: str,
    port: int,
    timeout: float = 30.0,
    interval: float = 0.5,
    logger: Optional[logging.Logger] = None,
) -> None:
    """Attende che una porta TCP sia raggiungibile entro `timeout` secondi.

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
    raise TimeoutError(f"Porta non raggiungibile: {host}:{port} entro {timeout}s; last={last_exc!r}")


# ----------------------------- Docker helpers --------------------------------------


def docker_available(*, logger: Optional[logging.Logger] = None, timeout_s: Optional[float] = None) -> bool:
    """Ritorna True se `docker` è invocabile e risponde a `docker --version`."""
    try:
        run_cmd(
            ["docker", "--version"],
            timeout=timeout_s or float(get_int("PROC_CMD_TIMEOUT", 10) or 10),
            retries=0,
            capture=True,
            logger=logger,
            op="docker version",
        )
        return True
    except CmdError:
        if logger:
            logger.warning("docker.unavailable", extra={"host": "local"})
        return False


def _docker_rm_force(name: str, *, logger: Optional[logging.Logger] = None) -> None:
    try:
        run_cmd(["docker", "rm", "-f", name], retries=0, capture=True, logger=logger, op="docker rm -f")
    except CmdError:
        # Best-effort
        if logger:
            logger.debug("docker.rm_force.fail", extra={"container": name})


def _docker_inspect_running(name: str, *, logger: Optional[logging.Logger] = None) -> bool:
    try:
        cp = run_cmd(
            ["docker", "inspect", "-f", "{{.State.Running}}", name],
            retries=0,
            capture=True,
            logger=logger,
            op="docker inspect",
        )
        out = (cp.stdout or "").strip().lower()
        return out == "true"
    except CmdError:
        return False


def _preview_ready_timeout() -> float:
    # Timeout readiness in secondi (default 30)
    return float(get_int("PREVIEW_READY_TIMEOUT", 30) or 30)


def run_docker_preview(
    md_dir: Path | str,
    *,
    port: int = 4000,
    container_name: str = "honkit_preview",
    retries: int = 1,
    logger: Optional[logging.Logger] = None,
    redact_logs: bool = False,  # mantenuto per firma coerente con i call-site;
) -> None:
    """Build + serve HonKit in container Docker in modalità detached, con retry e readiness check.

    - Usa l'immagine `honkit/honkit`.
    - Monta `md_dir` in /app.
    - Espone :4000 dalla container su `port` host.
    - Attende che la porta sia pronta (localhost:port) entro PREVIEW_READY_TIMEOUT.

    Raises:
        CmdError: in caso di fallimento non recuperabile.
    """
    md_path = Path(md_dir).resolve()
    if logger:
        logger.info(
            "preview.start",
            extra={"md_dir": str(md_path), "container": container_name, "port": port},
        )

    if not docker_available(logger=logger):
        raise CmdError("Docker non disponibile", cmd=["docker", "--version"], op="docker version")

    # Build statica (idempotente lato contenuti)
    run_cmd(
        [
            "docker",
            "run",
            "--rm",
            "--workdir",
            "/app",
            "-v",
            f"{md_path}:/app",
            "honkit/honkit",
            "npm",
            "run",
            "build",
        ],
        retries=retries,
        logger=logger,
        op="docker honkit build",
    )

    # Se esiste un container con lo stesso nome, proviamo a rimuoverlo prima
    _docker_rm_force(container_name, logger=logger)

    # Serve detached
    cp = run_cmd(
        [
            "docker",
            "run",
            "-d",
            "--name",
            container_name,
            "-p",
            f"{int(port)}:4000",
            "--workdir",
            "/app",
            "-v",
            f"{md_path}:/app",
            "honkit/honkit",
            "npm",
            "run",
            "serve",
        ],
        retries=retries,
        logger=logger,
        op="docker honkit serve",
    )

    # container id nel stdout (non logghiamo intero per pulizia)
    if logger:
        cid = (cp.stdout or "").strip()
        logger.info(
            "preview.container.started",
            extra={"container": container_name, "cid_prefix": cid[:12] if cid else ""},
        )

    # Readiness: attendiamo che la porta risponda
    try:
        wait_for_port("127.0.0.1", int(port), timeout=_preview_ready_timeout(), logger=logger)
        if logger:
            logger.info("preview.ready", extra={"container": container_name, "port": port})
    except TimeoutError as e:
        running = _docker_inspect_running(container_name, logger=logger)
        if logger:
            logger.error(
                "preview.ready.timeout",
                extra={"container": container_name, "port": port, "running": running},
            )
        # best-effort cleanup
        _docker_rm_force(container_name, logger=logger)
        raise CmdError(str(e), cmd=["docker", "run", "..."], op="docker honkit serve")


def stop_docker_preview(container_name: str = "honkit_preview", *, logger: Optional[logging.Logger] = None) -> None:
    """Tenta lo stop + remove del container di preview.

    Best-effort (non solleva).
    """
    try:
        run_cmd(
            ["docker", "stop", container_name],
            retries=0,
            capture=True,
            logger=logger,
            op="docker stop",
        )
    except CmdError:
        pass
    finally:
        _docker_rm_force(container_name, logger=logger)
        if logger:
            logger.info("preview.container.cleaned", extra={"container": container_name})
