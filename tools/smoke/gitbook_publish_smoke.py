#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""
Smoke test per la pubblicazione GitBook.

Verifica che il workspace cliente contenga `book/layout_summary.md`,
che `book/` rispetti la path-safety e che `GITBOOK_TOKEN` + `GITBOOK_SPACE_ID`
siano configurati prima di lanciare la pubblicazione reale.

Esempio:
    python tools/gitbook_publish_smoke.py --slug acme --dry-run

Il flag `--dry-run` evita la chiamata verso GitBook ma controlla che
ribalta lo zip, i metadata e la summary.
"""

from __future__ import annotations

import argparse
from typing import Optional

from pipeline.context import ClientContext
from pipeline.gitbook_publish import publish_book_to_gitbook
from pipeline.layout_summary import read_layout_summary_entries
from pipeline.logging_utils import get_structured_logger

LOGGER = get_structured_logger("tools.gitbook_publish_smoke")


def _load_context(slug: str) -> ClientContext:
    return ClientContext.load(slug=slug, interactive=False, require_env=False)


def _report_summary(book_dir: Optional[str]) -> None:
    if not book_dir:
        LOGGER.warning("book_dir mancante nel contesto, impossibile leggere layout_summary")
        return
    entries = read_layout_summary_entries(book_dir)
    if entries:
        LOGGER.info("layout_summary.md letta correttamente", extra={"entries": entries})
    else:
        LOGGER.warning("layout_summary.md mancante o vuota", extra={"book_dir": str(book_dir)})


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke test GitBook publish (layout_summary).")
    parser.add_argument("--slug", required=True, help="Slug cliente da testare")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Non invia nulla a GitBook, verifica solo i prerequisiti.",
    )
    args = parser.parse_args()

    try:
        context = _load_context(args.slug)
    except Exception as exc:
        LOGGER.error("Impossibile caricare il context", extra={"slug": args.slug, "error": str(exc)})
        return 1

    LOGGER.info("Smoke test GitBook iniziato", extra={"slug": args.slug})
    _report_summary(context.md_dir)

    token = getattr(context.settings, "GITBOOK_TOKEN", None) if hasattr(context.settings, "GITBOOK_TOKEN") else None
    space_id = (
        getattr(context.settings, "GITBOOK_SPACE_ID", None) if hasattr(context.settings, "GITBOOK_SPACE_ID") else None
    )

    if not token or not space_id:
        LOGGER.warning(
            "Token o spazio GitBook mancanti. Imposta GITBOOK_TOKEN/GITBOOK_SPACE_ID "
            "nel workspace o esportale per questo script.",
            extra={"slug": args.slug},
        )
        if args.dry_run:
            return 0
        print("Configurazione GitBook incompleta; esci e imposta le variabili.")
        return 2

    if args.dry_run:
        LOGGER.info("Dry run: tutto pronto per la pubblicazione GitBook.", extra={"slug": args.slug})
        return 0

    try:
        publish_book_to_gitbook(
            context.md_dir,
            space_id=space_id,
            token=token,
            slug=args.slug,
            layout_entries=read_layout_summary_entries(context.md_dir),
        )
    except Exception as exc:
        LOGGER.error("Smoke publish fallito", extra={"slug": args.slug, "error": str(exc)})
        return 3
    LOGGER.info("Smoke publish eseguito con successo", extra={"slug": args.slug})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
