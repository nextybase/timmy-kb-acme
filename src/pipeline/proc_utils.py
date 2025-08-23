# SPDX-License-Identifier: GPL-3.0-or-later
# src/pipeline/proc_utils.py
"""
Utility robuste e riutilizzabili per l'esecuzione di subprocess con timeout, retry e logging.
Pensato per sostituire chiamate dirette a `subprocess.run` in moduli come:
- gitbook_preview.py (Docker build/run)
- github_utils.py (git add/commit/push)
- tools/cleanup_repo.py (facoltativo)

API principali:
- run_cmd(...): esecuzione con timeout, retry/backoff e redazione sicura nei log
- wait_for_port(...): attende che una porta TCP risponda
- docker_available(...): verifica disponibilità di Docker
- run_docker_preview(...): build + serve HonKit in container (detached) con readiness check
- stop_docker_preview(...): stop/cleanup container di preview

Note:
- Nessuna retro-compatibilità: rimosse le fallback function legacy.
"""

from __future__ import annotations

from typing import Sequence, Mapping, Optional, Callable
import os
import time
import shlex
import socket
import subprocess
import logging
from pathlib import Path

from .env_utils import get_int, redact_secrets  # coerenza con la pipeline

__all__ = [
    "CmdError",
    "run_cmd",
    "wait_for_port",
    "docker_available",
    "run_docker_preview",
    "stop_docker_preview",
]


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
        # shlex.split è sufficiente nel nostro contesto; i call-site possono passare già la lista
        return shlex.split(cmd)
    return list(cmd)


def _render_cmd_for_log(argv: Sequence[str], redactor: Callable[[str], str]) -> str:
    # Rappresentiamo il comando come stringa shell-quoted, poi redigiamo eventuali segreti
    rendered = " ".join(shlex.quote(a) for a in argv)
    return redactor(rendered)


def _tail(text: Optional[str], *, limit: int = 2000) -> Optional[str]:
    if text is None:
        return None
    return text if len(text) <= limit else text[-limit:]


def _merge_env(base: Mapping[str, str], extra: Optional[Mapping[str, str]]) -> Mapping[str, str]:
    if not extra:
        return dict(base)
    merged = dict(base)
    merged.update(extra)
    return merged


def _default_timeout_for(op: Optional[str]) -> int:
    """
    Timeout di default (secondi) basato sull'operazione.
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

    # cwd normalizzato per i log (se fornito)
    cwd_log = ""
    if cwd:
        try:
            cwd_log = str(Path(cwd).resolve())
        except Exception:
            cwd_log = str(cwd)

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
                        "cwd": cwd_log,
                        "timeout_s": eff_timeout,
                        "cmd": _render_cmd_for_log(argv, redactor),
                    },
                )

            cp = subprocess.run(
                argv,
                cwd=cwd,
                env=merged_env,
                capture_output=capture,
                text=capture,
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
                        "stdout_tail": redactor(_tail(cp.stdout) or ""),
                    },
                )

        except subprocess.TimeoutExpired:
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
                        "cwd": cwd_log,
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
            logger.warning("docker.unavailable")
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
    redact_logs: bool = False,  # mantenuto per firma coerente con call-site; non logghiamo segreti qui
) -> None:
    """
    Build + serve HonKit in container Docker in modalità detached, con retry e readiness check.
    - Usa l'immagine `honkit/honkit`.
    - Monta `md_dir` in /app.
    - Espone :4000 dalla container su `port` host.
    - Attende che la porta sia pronta (localhost:port) entro PREVIEW_READY_TIMEOUT.

    Raises:
        CmdError in caso di fallimento non recuperabile.
    """
    md_path = Path(md_dir).resolve()
    if logger:
        logger.info("preview.start", extra={"md_dir": str(md_path), "container": container_name, "port": port})

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
        logger.info("preview.container.started", extra={"container": container_name, "cid_prefix": cid[:12] if cid else ""})

    # Readiness: attendiamo che la porta risponda
    try:
        wait_for_port("127.0.0.1", int(port), timeout=_preview_ready_timeout(), logger=logger)
        if logger:
            logger.info("preview.ready", extra={"container": container_name, "port": port})
    except TimeoutError as e:
        running = _docker_inspect_running(container_name, logger=logger)
        if logger:
            logger.error("preview.ready.timeout", extra={"container": container_name, "port": port, "running": running})
        # best-effort cleanup
        _docker_rm_force(container_name, logger=logger)
        raise CmdError(str(e), cmd=["docker", "run", "..."], op="docker honkit serve")


def stop_docker_preview(container_name: str = "honkit_preview", *, logger: Optional[logging.Logger] = None) -> None:
    """
    Tenta lo stop + remove del container di preview. Best-effort (non solleva).
    """
    try:
        run_cmd(["docker", "stop", container_name], retries=0, capture=True, logger=logger, op="docker stop")
    except CmdError:
        pass
    finally:
        _docker_rm_force(container_name, logger=logger)
        if logger:
            logger.info("preview.container.cleaned", extra={"container": container_name})
