#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
# tools/observability_stack.py
"""
Helpers per avviare e fermare lo stack Grafana/Loki quando Docker Ã¨ disponibile.
"""

from __future__ import annotations

import argparse
import os
import subprocess
from pathlib import Path
from typing import Sequence, Tuple

_DEFAULT_COMPOSE = Path("observability/docker-compose.yaml")
_DEFAULT_ENV = Path(".env")


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _resolve_path(path: Path | str) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = _repo_root() / candidate
    return candidate


def _run_docker_compose(action: Sequence[str]) -> Tuple[bool, str]:
    env_file = os.getenv("TIMMY_OBSERVABILITY_ENV_FILE", str(_DEFAULT_ENV))
    compose_file = os.getenv("TIMMY_OBSERVABILITY_COMPOSE_FILE", str(_DEFAULT_COMPOSE))
    cmd = ["docker", "compose", "--env-file", env_file, "-f", compose_file, *action]
    try:
        proc = subprocess.run(
            cmd,
            cwd=_repo_root(),
            capture_output=True,
            text=True,
            check=False,
        )
    except Exception as exc:
        return False, str(exc)
    if proc.returncode == 0:
        payload = proc.stdout.strip() or "OK"
        return True, payload
    msg = proc.stderr.strip() or proc.stdout.strip() or f"exit {proc.returncode}"
    return False, msg


def start_observability_stack() -> Tuple[bool, str]:
    """Avvia Grafana/Loki/Tempo tramite docker compose."""
    return _run_docker_compose(["up", "-d"])


def stop_observability_stack() -> Tuple[bool, str]:
    """Ferma lo stack (docker compose down)."""
    return _run_docker_compose(["down"])


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Avvia o ferma lo stack Grafana/Loki configurato in observability/docker-compose.yaml."
    )
    parser.add_argument("action", choices=["start", "stop"], help="Azione da eseguire.")
    parser.add_argument(
        "--env-file",
        default=os.getenv("TIMMY_OBSERVABILITY_ENV_FILE") or str(_DEFAULT_ENV),
        help="File .env passato a docker compose (default TIMMY_OBSERVABILITY_ENV_FILE o .env).",
    )
    parser.add_argument(
        "--compose-file",
        default=os.getenv("TIMMY_OBSERVABILITY_COMPOSE_FILE") or str(_DEFAULT_COMPOSE),
        help=(
            "Docker compose file da usare "
            "(default TIMMY_OBSERVABILITY_COMPOSE_FILE o observability/docker-compose.yaml)."
        ),
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    os.environ.setdefault("TIMMY_OBSERVABILITY_ENV_FILE", args.env_file)
    os.environ.setdefault("TIMMY_OBSERVABILITY_COMPOSE_FILE", args.compose_file)
    runner = start_observability_stack if args.action == "start" else stop_observability_stack
    ok, msg = runner()
    print(msg)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
