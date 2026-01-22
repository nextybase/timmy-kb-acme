# SPDX-License-Identifier: GPL-3.0-or-later
# src/semantic_headless.py
# Regola CLI: dichiarare bootstrap_config esplicitamente (il default e' vietato).
from __future__ import annotations

import argparse
import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, TypeVar, cast

from pipeline.exceptions import ConfigError
from pipeline.logging_utils import get_structured_logger, log_workflow_summary
from pipeline.tracing import start_root_trace
from pipeline.workspace_layout import WorkspaceLayout, workspace_validation_policy
from semantic.api import require_reviewed_vocab
from semantic.convert_service import convert_markdown
from semantic.frontmatter_service import enrich_frontmatter, write_summary_and_readme
from timmy_kb.versioning import build_env_fingerprint

__all__ = [
    "build_markdown_headless",
    "run_semantic_headless",
    "main",
    "_parse_args",
    "_setup_logger",
    "get_structured_logger",
    "ConfigError",
]

_T = TypeVar("_T")


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

    # 2) Caricamento vocabolario canonico: usa ctx.repo_root_dir come root canonica.
    if getattr(ctx, "repo_root_dir", None) is None:
        raise ConfigError(
            "Contesto privo di repo_root_dir: impossibile risolvere il workspace in modo deterministico.",
            slug=slug,
        )
    with workspace_validation_policy(skip_validation=True):
        layout = WorkspaceLayout.from_context(cast(Any, ctx))
    base = layout.repo_root_dir
    vocab = require_reviewed_vocab(base, log, slug=slug)

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


def _default_parse_args() -> argparse.Namespace:
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
    p.add_argument(
        "--no-preview",
        action="store_true",
        help="Non avviare eventuali preview collegate (placeholder).",
    )
    p.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Livello di logging su stderr.",
    )
    return p.parse_args()


def _parse_args() -> argparse.Namespace:
    return _default_parse_args()


def _default_setup_logger(level: str, *, slug: str | None = None) -> logging.Logger:
    """Istanzia il logger strutturato con livello desiderato e contesto opzionale."""
    context = {"slug": slug} if slug else None
    logger = cast(logging.Logger, get_structured_logger("semantic.headless", context=context))
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    return logger


def _setup_logger(level: str, *, slug: str | None = None) -> logging.Logger:
    return _default_setup_logger(level, slug=slug)


def _safe_len_seq(obj: object) -> int:
    """Restituisce len(obj) solo se obj è una lista/tupla, altrimenti 0 (type-safe per Pylance)."""
    if isinstance(obj, (list, tuple)):
        return len(obj)
    return 0


def run_semantic_headless(
    slug: str,
    *,
    non_interactive: bool = False,
    log_level: str = "INFO",
) -> dict[str, object]:
    log = _setup_logger(log_level, slug=slug)
    env = os.getenv("TIMMY_ENV", "dev")
    fp = build_env_fingerprint()
    log.info("semantic.headless.started", extra={"slug": slug, "env_fingerprint": fp})

    with start_root_trace(
        "reindex",
        slug=slug,
        run_id=None,
        entry_point="cli",
        env=env,
        trace_kind="reindex",
    ):
        try:
            from pipeline.context import ClientContext

            ctx = ClientContext.load(
                slug=slug,
                require_env=False,
                run_id=None,
                bootstrap_config=False,
            )
        except ConfigError as exc:
            log.exception("semantic.headless.context_load_failed", extra={"error": str(exc)})
            return {
                "slug": slug,
                "env_fingerprint": fp,
                "status": "config_error",
                "stage": "context",
                "converted_count": 0,
                "enriched_count": 0,
                "summary_readme": False,
                "exit_code": 2,
            }
        except Exception as exc:  # pragma: no cover - defensive
            log.exception("semantic.headless.context_unexpected", extra={"error": str(exc)})
            return {
                "slug": slug,
                "env_fingerprint": fp,
                "status": "error",
                "stage": "context",
                "converted_count": 0,
                "enriched_count": 0,
                "summary_readme": False,
                "exit_code": 1,
            }

        try:
            res = build_markdown_headless(ctx, log, slug=slug)
            conv = _safe_len_seq(res.get("converted"))
            enr = _safe_len_seq(res.get("enriched"))
        except ConfigError as exc:
            log.exception("semantic.headless.run_config_error", extra={"error": str(exc)})
            return {
                "slug": slug,
                "env_fingerprint": fp,
                "status": "config_error",
                "stage": "run",
                "converted_count": 0,
                "enriched_count": 0,
                "summary_readme": False,
                "exit_code": 2,
            }
        except Exception as exc:  # pragma: no cover - defensive
            log.exception("semantic.headless.run_failed", extra={"error": str(exc)})
            return {
                "slug": slug,
                "env_fingerprint": fp,
                "status": "error",
                "stage": "run",
                "converted_count": 0,
                "enriched_count": 0,
                "summary_readme": False,
                "exit_code": 1,
            }

    log.info("semantic.headless.completed", extra={"converted_count": conv, "enriched_count": enr})
    log_workflow_summary(
        log,
        event="cli.semantic_headless.completed",
        slug=slug,
        artifacts=int(conv),
        extra={"enriched_count": int(enr), "env_fingerprint": fp},
    )
    return {
        "slug": slug,
        "env_fingerprint": fp,
        "status": "success",
        "stage": "run",
        "converted_count": conv,
        "enriched_count": enr,
        "summary_readme": bool(res.get("summary_readme")),
        "exit_code": 0,
    }


def main() -> int:
    args = _parse_args()
    result = run_semantic_headless(
        slug=args.slug,
        non_interactive=bool(args.non_interactive),
        log_level=str(args.log_level),
    )
    return int(result.get("exit_code", 1))


if __name__ == "__main__":
    raise SystemExit(main())

# Nota: genera prima il dummy ("py tools/gen_dummy_kb.py --slug dummy"), poi esegui
# "py tools/retriever_calibrate.py --slug dummy --scope book" e aggiungi
# "--queries tests/data/retriever_queries.jsonl --limits 500:3000:500" come da docs/test_suite.md.
