# SPDX-License-Identifier: GPL-3.0-or-later
"""Helper isolati per l'esecuzione Vision con timeout."""

from __future__ import annotations

import logging
import multiprocessing as mp
from pathlib import Path
from typing import Any, Callable, Optional

from pipeline.logging_utils import get_structured_logger
from pipeline.settings import Settings


class _Ctx:
    """Contesto minimo compatibile con run_vision (serve .base_dir)."""

    def __init__(self, base_dir: Path, *, slug: str) -> None:
        self.base_dir = base_dir
        self.slug = slug
        try:
            self.settings = Settings.load(base_dir)
        except Exception:
            self.settings = {}


def _vision_worker(queue: mp.Queue, slug: str, base_dir: str, pdf_path: str, run_vision: Callable[..., Any]) -> None:
    """Esegue run_vision in un sottoprocesso e restituisce esito tramite queue."""
    ctx = _Ctx(Path(base_dir), slug=slug)
    logger = get_structured_logger("tools.gen_dummy_kb.vision", context={"slug": slug})
    try:
        run_vision(ctx, slug=slug, pdf_path=Path(pdf_path), logger=logger)
        queue.put({"status": "ok"})
    except Exception as exc:  # noqa: BLE001
        payload: dict[str, Any] = {
            "status": "error",
            "error": str(exc),
            "exc_type": exc.__class__.__name__,
        }
        file_path = getattr(exc, "file_path", None)
        if file_path:
            payload["file_path"] = str(file_path)
        queue.put(payload)


def run_vision_with_timeout(
    *,
    base_dir: Path,
    slug: str,
    pdf_path: Path,
    timeout_s: float,
    logger: logging.Logger,
    run_vision: Callable[..., Any],
) -> tuple[bool, Optional[dict[str, Any]]]:
    ctx = mp.get_context("spawn")
    queue: mp.Queue = ctx.Queue()
    proc = ctx.Process(target=_vision_worker, args=(queue, slug, str(base_dir), str(pdf_path), run_vision))
    proc.daemon = False
    try:
        proc.start()
    except Exception as exc:  # noqa: BLE001
        try:
            logger.error(
                "tools.gen_dummy_kb.vision_spawn_failed",
                extra={"slug": slug, "error": str(exc)},
            )
        except Exception:
            pass
        queue.close()
        queue.join_thread()
        return False, {"status": "error", "error": str(exc), "reason": "spawn-failed"}
    proc.join(timeout_s)
    if proc.is_alive():
        logger.warning(
            "tools.gen_dummy_kb.vision_timeout",
            extra={"slug": slug, "timeout_s": timeout_s},
        )
        proc.terminate()
        proc.join(5)
        queue.close()
        queue.join_thread()
        return False, {"reason": "timeout"}
    try:
        result = queue.get_nowait()
    except Exception:
        result = {"status": "error", "reason": "no-result"}
    finally:
        queue.close()
        queue.join_thread()
    exit_code = proc.exitcode
    if exit_code not in (0, None) and result.get("status") == "ok":
        result = {"status": "error", "exit_code": exit_code}
    if result.get("status") == "ok":
        return True, None
    return False, result  # type: ignore[return-value]


__all__ = ["run_vision_with_timeout"]
