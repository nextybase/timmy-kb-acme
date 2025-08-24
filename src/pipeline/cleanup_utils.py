# src/pipeline/cleanup_utils.py
"""
Utility di pulizia per la pipeline Timmy-KB.

Ruolo:
- Fornire funzioni *pure* di cleanup senza interazione utente né terminazioni del processo.
- Limitarsi a rimuovere in sicurezza eventuali artefatti locali creati dai flussi di push
  legacy (es. una `.git` annidata in `book/`) o run precedenti.

⚠️ Niente input()/print()/sys.exit(): i prompt stanno negli orchestratori.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Optional, Dict, Any

from pipeline.logging_utils import get_structured_logger
from pipeline.path_utils import ensure_within  # SSoT guardia STRONG
from pipeline.context import ClientContext

logger = get_structured_logger("pipeline.cleanup_utils")


def _rmtree_safe(target: Path) -> bool:
    """
    Rimozione directory con log e senza eccezioni verso l'alto.
    Ritorna True se la directory è stata rimossa o non esisteva.
    """
    try:
        if target.exists():
            shutil.rmtree(target, ignore_errors=False)
            logger.info("🧹 Rimossa directory", extra={"file_path": str(target)})
        else:
            logger.info("ℹ️  Nessuna directory da rimuovere (assente)", extra={"file_path": str(target)})
        return True
    except Exception as e:
        logger.warning(
            "⚠️  Impossibile rimuovere directory",
            extra={"file_path": str(target), "error": str(e)},
        )
        return False


def clean_push_leftovers(
    context: ClientContext,
    *,
    logger_name: str = "pipeline.cleanup_utils",
) -> Dict[str, Any]:
    """
    Rimuove in modo *idempotente* e *sicuro* eventuali artefatti locali di push.

    Attualmente:
    - elimina `.git` eventualmente presente sotto `context.md_dir` (book/),
      tipico di run legacy che inizializzavano un repo lì.

    Non elimina `book/` né altri file `.md` generati dalla pipeline.

    Returns:
        Report con esito per ciascun target pulito.
    """
    _logger = get_structured_logger(logger_name, context=context)

    book_dir: Path = context.md_dir
    base_dir: Path = context.base_dir

    # Guard-rail STRONG: non operare fuori dalla base cliente
    try:
        ensure_within(base_dir, book_dir)
    except Exception as e:
        _logger.warning(
            "Path book non sicuro: skip cleanup",
            extra={"file_path": str(book_dir), "error": str(e)},
        )
        return {"ok": False, "reason": "unsafe_path", "targets": []}

    targets = []
    # Artefatto principale noto: repo Git locale legacy
    git_dir = book_dir / ".git"
    if git_dir.exists():
        # Validazione STRONG anche del target specifico prima della rimozione
        try:
            ensure_within(book_dir, git_dir)
            targets.append(git_dir)
        except Exception as e:
            _logger.warning(
                "Target .git non sicuro: skip",
                extra={"file_path": str(git_dir), "error": str(e)},
            )

    results: Dict[str, bool] = {}
    for t in targets:
        results[str(t)] = _rmtree_safe(t)

    summary = {
        "ok": all(results.values()) if results else True,
        "targets": list(results.keys()),
    }
    _logger.info("✅ Cleanup completato", extra=summary)
    return summary
