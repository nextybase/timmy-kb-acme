# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

import shutil
import subprocess
from typing import Tuple

from pipeline.logging_utils import get_structured_logger

LOGGER = get_structured_logger("pipeline.docker_utils")


def check_docker_status(timeout: float = 5.0) -> Tuple[bool, str]:
    """Verifica se Docker è disponibile e risponde entro il timeout dato."""
    docker_exe = shutil.which("docker")
    if docker_exe is None:
        return False, "Docker CLI non trovato (installa Docker Desktop/Engine)"
    try:
        subprocess.run(  # noqa: S603,S607 - docker_exe viene da shutil.which ed è un percorso assoluto controllato
            [docker_exe, "info"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True,
            timeout=timeout,
        )
        return True, ""
    except subprocess.TimeoutExpired as exc:
        LOGGER.warning("docker.check.timeout", exc_info=exc)
        return False, f"Docker non risponde (timeout {int(timeout)}s)"
    except Exception as exc:  # pragma: no cover - branches difficile da riprodurre
        LOGGER.warning("docker.check.failed", exc_info=exc)
        return False, "Docker non in esecuzione (avvialo e riprova)"
