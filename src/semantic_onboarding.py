#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-3.0-only

from __future__ import annotations

import argparse
import os
import uuid
from pathlib import Path

from pipeline.context import ClientContext
from pipeline.exceptions import ConfigError, PipelineError, exit_code_for
from pipeline.logging_utils import get_structured_logger, phase_scope
from pipeline.observability_config import load_observability_settings
from pipeline.path_utils import iter_safe_paths
from pipeline.tracing import start_root_trace
from semantic.api import list_content_markdown  # <-- PR2: import dell'helper
from semantic.api import (
    convert_markdown,
    enrich_frontmatter,
    get_paths,
    require_reviewed_vocab,
    write_summary_and_readme,
)


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
    settings = load_observability_settings()
    logger = get_structured_logger(
        "semantic.onboarding",
        run_id=run_id,
        level=settings.log_level,
        redact_logs=settings.redact_logs,
        enable_tracing=settings.tracing_enabled,
    )

    # Inizializza per sicurezza (evita UnboundLocalError nel riepilogo)
    touched: list[Path] = []

    # Carica contesto locale (niente Drive / env obbligatori)
    ctx = ClientContext.load(slug=slug, interactive=not args.non_interactive, require_env=False, run_id=run_id)

    # Imposta flag UX nel contesto (se usati a valle)
    try:
        ctx.skip_preview = bool(args.no_preview)
        ctx.no_interactive = bool(args.non_interactive)
    except Exception:
        # Il contesto potrebbe non supportare questi attributi in alcune implementazioni.
        pass

    env = os.getenv("TIMMY_ENV", "dev")
    overall_slug = slug
    logger.info("cli.semantic_onboarding.started", extra={"slug": slug})
    with start_root_trace(
        "onboarding",
        slug=overall_slug,
        run_id=run_id,
        entry_point="cli",
        env=env,
        trace_kind="onboarding",
    ):
        try:
            # 1) Converti i PDF in Markdown
            with phase_scope(logger, stage="cli.convert_markdown", customer=slug):
                convert_markdown(ctx, logger, slug=slug)

            # 2) Arricchisci il frontmatter usando il vocabolario consolidato
            paths = get_paths(slug)
            base_dir: Path = ctx.base_dir or paths["base"]
            vocab = require_reviewed_vocab(base_dir, logger, slug=slug)
            with phase_scope(logger, stage="cli.enrich_frontmatter", customer=slug) as m:
                touched = enrich_frontmatter(ctx, logger, vocab, slug=slug)
                try:
                    m.set_artifacts(len(touched))
                except Exception:
                    m.set_artifacts(None)

            # 3) Genera SUMMARY.md e README.md e valida la cartella book/
            with phase_scope(logger, stage="cli.write_summary_and_readme", customer=slug):
                write_summary_and_readme(ctx, logger, slug=slug)
        except (ConfigError, PipelineError) as exc:
            # Mappa verso exit code deterministici (no traceback non gestiti)
            logger.exception("cli.semantic_onboarding.failed", extra={"slug": slug, "error": str(exc)})
            code: int = int(exit_code_for(exc))  # exit_code_for non è tipizzato: forza int per mypy
            return code
        except Exception as exc:
            # Fallback deterministico per errori inattesi non mappati
            logger.exception("cli.semantic_onboarding.unexpected_error", extra={"slug": slug, "error": str(exc)})
            return 99

    # Riepilogo artefatti (best-effort, non influenza l'exit code)
    summary_extra: dict[str, object] = {}
    try:
        paths = get_paths(slug)
        book_dir: Path = getattr(ctx, "md_dir", None) or paths["book"]
        summary_path = book_dir / "SUMMARY.md"
        readme_path = book_dir / "README.md"

        try:
            # Preferisci l'helper (esclude README/SUMMARY dai conteggi)
            content_mds = list_content_markdown(book_dir)
        except Exception:
            # Fallback robusto nel caso l'helper non sia disponibile/rompa
            content_mds = [
                p
                for p in iter_safe_paths(book_dir, include_dirs=False, include_files=True, suffixes=(".md",))
                if p.name not in {"README.md", "SUMMARY.md"}
            ]

        summary_extra = {
            "book_dir": str(book_dir),
            "markdown": len(content_mds),
            "frontmatter": len(touched),
            "summary_exists": summary_path.exists(),
            "readme_exists": readme_path.exists(),
        }
        logger.info("cli.semantic_onboarding.summary", extra={"slug": slug, **summary_extra})
    except Exception as exc:
        logger.warning(
            "cli.semantic_onboarding.summary_failed",
            extra={"slug": slug, "error": str(exc)},
        )

    logger.info(
        "cli.semantic_onboarding.completed",
        extra={"slug": slug, "artifacts": int(len(touched)), **summary_extra},
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130)
