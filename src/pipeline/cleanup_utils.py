# SPDX-License-Identifier: GPL-3.0-or-later
# src/pipeline/cleanup_utils.py
"""Utility di pulizia per la pipeline Timmy-KB.

Ruolo:
- Fornire funzioni *pure* di cleanup senza interazione utente né terminazioni del processo.
- Limitarsi a rimuovere in sicurezza eventuali derivatives locali legacy
  (es. una `.git` annidata in `book/`) o run precedenti.

⚠️ Niente input()/print()/sys.exit(): i prompt stanno negli orchestratori.
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Any, Dict

from pipeline.logging_utils import get_structured_logger
from pipeline.path_utils import ensure_within  # SSoT guardia STRONG
from pipeline.workspace_layout import WorkspaceLayout
from semantic.context_paths import resolve_context_paths
from semantic.types import ClientContextProtocol as _Ctx  # SSoT: protocollo condiviso

# Logger di modulo (fallback).
logger = get_structured_logger("pipeline.cleanup_utils")


def _rmtree_safe(target: Path, *, log: logging.Logger) -> bool:
    """Rimozione directory con log e senza eccezioni verso l'alto. Ritorna True se la directory è
    stata rimossa o non esisteva.

    Nota: usa il logger passato (contestualizzato) così i log portano slug/run_id.
    """
    try:
        if target.exists():
            shutil.rmtree(target, ignore_errors=False)
            log.info("pipeline.cleanup.dir_removed", extra={"file_path": str(target)})
        else:
            log.info("pipeline.cleanup.dir_absent", extra={"file_path": str(target)})
        return True
    except Exception as e:
        log.warning(
            "pipeline.cleanup.dir_remove_failed",
            extra={"file_path": str(target), "error": str(e)},
        )
        return False


def clean_legacy_artifacts(
    context: _Ctx,
    *,
    logger_name: str = "pipeline.cleanup_utils",
) -> Dict[str, Any]:
    """Rimuove in modo *idempotente* e *sicuro* eventuali derivatives locali legacy.

    Attualmente:
    - elimina `.git` eventualmente presente sotto `context.md_dir` (book/),
      tipico di run legacy che inizializzavano un repo lì.

    Non elimina `book/` né altri file `.md` generati dalla pipeline.

    Restituisce:
        Report con esito per ciascun target pulito.
    """
    _logger = get_structured_logger(logger_name, context=context)

    layout = WorkspaceLayout.from_context(context)  # type: ignore[arg-type]
    paths = resolve_context_paths(layout)
    book_dir: Path = paths.md_dir
    base_dir: Path = paths.base_dir

    # Guard-rail STRONG: non operare fuori dalla base cliente
    try:
        ensure_within(base_dir, book_dir)
    except Exception as e:
        _logger.warning(
            "pipeline.cleanup.unsafe_book_path",
            extra={"file_path": str(book_dir), "error": str(e)},
        )
        return {"ok": False, "reason": "unsafe_path", "targets": []}

    targets = []
    # Derivative principale noto: repo Git locale legacy
    git_dir = book_dir / ".git"
    if git_dir.exists():
        # Validazione STRONG anche del target specifico prima della rimozione
        try:
            ensure_within(book_dir, git_dir)
            targets.append(git_dir)
        except Exception as e:
            _logger.warning(
                "pipeline.cleanup.git_dir_unsafe",
                extra={"file_path": str(git_dir), "error": str(e)},
            )

    results: Dict[str, bool] = {}
    for t in targets:
        results[str(t)] = _rmtree_safe(t, log=_logger)

    summary = {
        "ok": all(results.values()) if results else True,
        "targets": list(results.keys()),
    }
    _logger.info("pipeline.cleanup.completed", extra=summary)
    return summary
