# SPDX-License-Identifier: GPL-3.0-or-later
"""Lease lock filesystem per orchestrare il push GitHub."""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

from pipeline.exceptions import ConfigError, PushError
from pipeline.file_utils import create_lock_file, remove_lock_file
from pipeline.logging_utils import get_structured_logger
from pipeline.path_utils import ensure_within_and_resolve

LEASE_DIRNAME = ".github_push.lockdir"

__all__ = ["LeaseLock", "LEASE_DIRNAME"]


class LeaseLock:
    """Lock file-based per evitare push concorrenti sullo stesso workspace."""

    def __init__(
        self,
        base_dir: Path,
        *,
        slug: str,
        logger: Any | None = None,
        timeout_s: float = 10.0,
        poll_interval_s: float = 0.25,
        dirname: str = LEASE_DIRNAME,
    ) -> None:
        self._logger = logger or get_structured_logger("pipeline.github_utils.lock")
        self._slug = slug
        self._timeout_s = max(timeout_s, 0.1)
        self._poll_interval_s = max(poll_interval_s, 0.05)
        self._lock_path = ensure_within_and_resolve(base_dir, base_dir / dirname)
        self._acquired = False

    def __enter__(self) -> "LeaseLock":
        self.acquire()
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.release()

    def acquire(self) -> None:
        deadline = time.monotonic() + self._timeout_s
        while True:
            try:
                create_lock_file(Path(self._lock_path), payload=f"{os.getpid()}:{time.time():.3f}\n")
                self._acquired = True
                self._logger.debug(
                    "github_utils.lock.acquire",
                    extra={"slug": self._slug, "lock_path": str(self._lock_path)},
                )
                return
            except FileExistsError:
                if time.monotonic() >= deadline:
                    raise PushError("Push GitHub bloccato: lock non disponibile entro il timeout.", slug=self._slug)
                self._logger.debug(
                    "github_utils.lock.waiting",
                    extra={"slug": self._slug, "lock_path": str(self._lock_path)},
                )
                time.sleep(self._poll_interval_s)

    def release(self) -> None:
        if not self._acquired:
            return
        try:
            remove_lock_file(Path(self._lock_path))
            self._logger.debug(
                "github_utils.lock.release",
                extra={"slug": self._slug, "lock_path": str(self._lock_path)},
            )
        except ConfigError as exc:
            self._logger.debug(
                "github_utils.lock.release_failed",
                extra={"slug": self._slug, "lock_path": str(self._lock_path), "error": str(exc)},
            )
        finally:
            self._acquired = False
