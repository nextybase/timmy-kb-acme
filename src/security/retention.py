# src/security/retention.py
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

from pipeline.logging_utils import get_structured_logger
from pipeline.path_utils import ensure_within_and_resolve

LOGGER = get_structured_logger("security.retention")

_DEFAULT_PATTERNS: tuple[str, ...] = ("semantic/*.snapshot.txt",)


def purge_old_artifacts(base_dir: Path, days: int, *, patterns: Iterable[str] | None = None) -> int:
    """
    Rimuove file temporanei più vecchi di `days` giorni all'interno di `base_dir`.

    Args:
        base_dir: radice del workspace cliente (es. output/timmy-kb-<slug>).
        days: soglia massima di retention in giorni (deve essere > 0).
        patterns: glob relative a `base_dir` da scandire (default: snapshot Vision).

    Returns:
        Numero di file rimossi con successo.
    """
    if days <= 0:
        LOGGER.debug("retention.skip.invalid_days", extra={"base_dir": str(base_dir), "days": days})
        return 0

    base_path = Path(base_dir)
    if not base_path.exists():
        LOGGER.debug("retention.skip.missing_base", extra={"base_dir": str(base_path)})
        return 0

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    total_removed = 0
    used_patterns = tuple(patterns or _DEFAULT_PATTERNS)

    for pattern in used_patterns:
        for candidate in base_path.glob(pattern):
            try:
                safe_path = ensure_within_and_resolve(base_path, candidate)
            except Exception:
                LOGGER.warning(
                    "retention.skip.outside_base",
                    extra={"base_dir": str(base_path), "candidate": str(candidate)},
                )
                continue

            try:
                stat = safe_path.stat()
            except OSError:
                continue

            mtime = datetime.fromtimestamp(stat.st_mtime, timezone.utc)
            if mtime >= cutoff:
                continue

            try:
                os.remove(safe_path)
                total_removed += 1
            except OSError as exc:
                LOGGER.warning(
                    "retention.remove.failed",
                    extra={"path": str(safe_path), "error": str(exc)},
                )

    if total_removed:
        LOGGER.info(
            "retention.remove.completed",
            extra={"base_dir": str(base_path), "removed": total_removed, "days": days},
        )
    else:
        LOGGER.debug(
            "retention.remove.nothing",
            extra={"base_dir": str(base_path), "days": days},
        )

    return total_removed
