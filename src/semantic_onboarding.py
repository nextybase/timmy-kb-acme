#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
import uuid
from pathlib import Path

from pipeline.context import ClientContext
from pipeline.exceptions import ConfigError, PipelineError, exit_code_for
from pipeline.logging_utils import get_structured_logger
from semantic.api import convert_markdown, enrich_frontmatter, get_paths, load_reviewed_vocab, write_summary_and_readme


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Semantic Onboarding CLI")
    p.add_argument("--slug", required=True, help="Slug cliente (es. acme)")
    p.add_argument("--no-preview", action="store_true", help="Non avviare/considerare la preview (flag nel contesto)")
    p.add_argument("--non-interactive", action="store_true", help="Esecuzione senza prompt")
    return p.parse_args()


def main() -> int:
    args = _parse_args()
    slug: str = args.slug
    run_id = uuid.uuid4().hex
    logger = get_structured_logger("semantic.onboarding", run_id=run_id)

    # Carica contesto locale (niente Drive / env obbligatori)
    ctx = ClientContext.load(slug=slug, interactive=not args.non_interactive, require_env=False, run_id=run_id)

    # Imposta flag UX nel contesto (se usati a valle)
    try:
        ctx.skip_preview = bool(args.no_preview)
        ctx.no_interactive = bool(args.non_interactive)
    except Exception:
        # Il contesto potrebbe non supportare questi attributi in alcune implementazioni.
        pass

    try:
        # 1) Converti i PDF in Markdown
        convert_markdown(ctx, logger, slug=slug)

        # 2) Arricchisci il frontmatter usando il vocabolario consolidato
        paths = get_paths(slug)
        base_dir: Path = ctx.base_dir or paths["base"]
        vocab = load_reviewed_vocab(base_dir, logger)
        touched = enrich_frontmatter(ctx, logger, vocab, slug=slug)

        # 3) Genera SUMMARY.md e README.md e valida la cartella book/
        write_summary_and_readme(ctx, logger, slug=slug)

    except (ConfigError, PipelineError) as exc:
        # Mappa verso exit code deterministici (no traceback non gestiti)
        logger.error("semantic_onboarding.failed", extra={"slug": slug, "error": str(exc)})
        # exit_code_for non è tipizzato: forza int per mypy
        code: int = int(exit_code_for(exc))
        return code

    # Riepilogo artefatti (best-effort, non influenza l'exit code)
    try:
        paths = get_paths(slug)
        book_dir: Path = getattr(ctx, "md_dir", None) or paths["book"]
        summary_path = book_dir / "SUMMARY.md"
        readme_path = book_dir / "README.md"
        print("\n== Semantic Onboarding ===")
        print(f"Slug: {slug}")
        print(f"Book dir: {book_dir}")
        print(f"Markdown generati: {len(list(book_dir.glob('*.md')))}")
        print(f"Frontmatter arricchiti: {len(touched)}")
        print(f"SUMMARY.md: {'OK' if summary_path.exists() else 'mancante'}")
        print(f"README.md: {'OK' if readme_path.exists() else 'mancante'}")
    except Exception:
        # Non bloccare l'exit code positivo per errori di stampa riepilogo
        pass

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130)
