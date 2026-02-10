from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path
from typing import Iterable

from pipeline.context import ClientContext
from pipeline.exceptions import ConfigError


def _strict_env() -> None:
    """Attiva strict runtime e rimuove i trigger di override/bootstrap."""
    os.environ["TIMMY_BETA_STRICT"] = "1"
    for key in ("TIMMY_ALLOW_WORKSPACE_OVERRIDE", "TIMMY_ALLOW_BOOTSTRAP"):
        os.environ.pop(key, None)


def _result(name: str, exc: Exception) -> str:
    return f"{name}: gate trappola attivata ({exc.__class__.__name__})"


def _run_bootstrap_gate() -> tuple[bool, str]:
    with tempfile.TemporaryDirectory(prefix="timmy-gate-") as base:
        workspace = Path(base) / "workspace"
        workspace.mkdir(parents=True, exist_ok=True)
        os.environ["WORKSPACE_ROOT_DIR"] = str(workspace)
        os.environ.pop("REPO_ROOT_DIR", None)
        try:
            ClientContext.load(
            slug="gate-bootstrap",
            require_drive_env=False,
            bootstrap_config=True,
        )
        except ConfigError as exc:
            return True, _result("bootstrap", exc)
        except Exception as exc:
            return False, f"bootstrap: unexpected failure {exc!r}"
        return False, "bootstrap: gate non ha scattato"


def _run_override_gate() -> tuple[bool, str]:
    with tempfile.TemporaryDirectory(prefix="timmy-gate-") as base:
        override_root = Path(base) / "override"
        override_root.mkdir(parents=True, exist_ok=True)
        try:
            ClientContext.load(
            slug="gate-override",
            repo_root_dir=override_root,
            require_drive_env=False,
            bootstrap_config=False,
        )
        except ConfigError as exc:
            allowed = "workspace.override.forbidden" in getattr(exc, "code", "")
            name = "override" if allowed else "override (unexpected guard)"
            return allowed, _result(name, exc)
        except Exception as exc:
            return False, f"override: unexpected failure {exc!r}"
        return False, "override: gate non ha scattato"


def main() -> None:
    """
    Smoke test rapido delle guardie strict.

    1. Bootstrap deve fallire senza TIMMY_ALLOW_BOOTSTRAP.
    2. Override repo_root_dir deve fallire senza TIMMY_ALLOW_WORKSPACE_OVERRIDE.
    """
    _strict_env()
    runners = [_run_bootstrap_gate, _run_override_gate]
    ok = True
    for runner in runners:
        passed, message = runner()
        print(message)
        ok = ok and passed
    if not ok:
        raise SystemExit("Strict workspace gate smoke test fallito.")
    print("OK: strict workspace gate smoke test completato.")


if __name__ == "__main__":
    raise SystemExit(main())
