# SPDX-License-Identifier: GPL-3.0-or-later
# src/semantic_headless.py
from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Dict, List, cast

from pipeline.exceptions import ConfigError
from pipeline.logging_utils import get_structured_logger
from semantic.api import convert_markdown, enrich_frontmatter, get_paths, load_reviewed_vocab, write_summary_and_readme

__all__ = ["build_markdown_headless"]

# Tipi compatibili con semantic.api:
# - in fase di type checking usiamo la classe concreta
# - a runtime usiamo il Protocol per evitare dipendenze hard
if TYPE_CHECKING:
    from pipeline.context import ClientContext as _ClientContext
else:
    from semantic.types import ClientContextProtocol as _ClientContext


def build_markdown_headless(
    ctx: _ClientContext,
    log: logging.Logger,
    *,
    slug: str,
) -> Dict[str, object]:
    """Esegue la pipeline semantica in modalità headless (senza prompt/UI):

    1) convert_markdown -> genera .md in book/ 2) load_reviewed_vocab -> carica vocabolario canonico
    da base/semantic 3) enrich_frontmatter -> arricchisce i frontmatter con titoli e tag 4)
    write_summary_and_readme -> genera SUMMARY.md e README.md e valida
    """
    # 1) Conversione PDF -> Markdown
    converted: List[Path] = convert_markdown(ctx, log, slug=slug)

    # 2) Caricamento vocabolario canonico: usa ctx.base_dir se presente, altrimenti get_paths(...)
    ctx_base = getattr(ctx, "base_dir", None)
    base = ctx_base if isinstance(ctx_base, Path) else get_paths(slug)["base"]
    vocab = load_reviewed_vocab(base, log) or {}

    # 3) Arricchimento frontmatter: esegui SEMPRE anche con vocab vuoto
    #    (titoli normalizzati devono essere impostati comunque)
    enriched: List[Path] = enrich_frontmatter(ctx, log, vocab, slug=slug, allow_empty_vocab=True)

    # 4) SUMMARY.md + README.md + validazione directory MD
    write_summary_and_readme(ctx, log, slug=slug)

    return {
        "converted": converted,
        "enriched": enriched,
        "summary_readme": True,
    }


# ---------------------------
# CLI minimale per i test e l'uso da shell
# ---------------------------


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="semantic_headless",
        description="Esegue la build semantica (RAW -> BOOK) in modalità headless.",
    )
    p.add_argument("--slug", required=True, help="Identificativo cliente (slug).")
    p.add_argument(
        "--non-interactive",
        action="store_true",
        help="Disabilita prompt interattivi (modalità batch/CI).",
    )
    # Opzione legacy/ignorable per compatibilità con i test
    p.add_argument(
        "--no-preview",
        action="store_true",
        help="Compatibilità: non avvia alcuna preview (opzione ignorata).",
    )
    p.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Livello di logging su stderr.",
    )
    return p.parse_args()


def _setup_logger(level: str, *, slug: str | None = None) -> logging.Logger:
    """Istanzia il logger strutturato con livello desiderato e contesto opzionale."""
    context = {"slug": slug} if slug else None
    logger = cast(logging.Logger, get_structured_logger("semantic.headless", context=context))
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    return logger


def _safe_len_seq(obj: object) -> int:
    """Restituisce len(obj) solo se obj è una lista/tupla, altrimenti 0 (type-safe per Pylance)."""
    if isinstance(obj, (list, tuple)):
        return len(obj)
    return 0


def main() -> int:
    args = _parse_args()
    log = _setup_logger(args.log_level, slug=args.slug)

    try:
        # Carichiamo il contesto concreto quando disponibile a runtime
        from pipeline.context import ClientContext

        ctx = ClientContext.load(
            slug=args.slug,
            interactive=not bool(args.non_interactive),
            require_env=False,
            run_id=None,
        )
    except ConfigError as exc:
        log.exception("semantic.headless.context_load_failed", extra={"error": str(exc)})
        return 2
    except Exception as exc:
        log.exception("semantic.headless.context_unexpected", extra={"error": str(exc)})
        return 1

    try:
        res = build_markdown_headless(ctx, log, slug=args.slug)
        conv = _safe_len_seq(res.get("converted"))
        enr = _safe_len_seq(res.get("enriched"))
    except ConfigError as exc:
        log.exception("semantic.headless.run_config_error", extra={"error": str(exc)})
        return 2
    except Exception as exc:
        log.exception("semantic.headless.run_failed", extra={"error": str(exc)})
        return 1

    log.info("semantic.headless.completed", extra={"converted_count": conv, "enriched_count": enr})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
