#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Onboarding FULL (fase 2): push GitHub e preflight su 'book/'.

Questo orchestratore:
- Presuppone che la fase di semantic onboarding sia gia' stata eseguita.
- Esegue esclusivamente il push su GitHub tramite pipeline.github_utils.
- Esegue un preflight su 'book/': accetta solo .md (i placeholder .md.fp sono tollerati).
- Tollerati in 'book/': builder files (book.json/package.json/lockfile) e sottodirectory
  '_book/', 'node_modules/', '.cache/', '.tmp/', '.git' (ignorate).
- Adotta path-safety STRONG tramite ensure_within.
- Gestisce I/O utente e codici di uscita a livello orchestratore; i moduli sottostanti
  non fanno prompt/exit.
"""
from __future__ import annotations

import argparse
import logging
import sys
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Optional, cast

from pipeline.constants import LOG_FILE_NAME, LOGS_DIR_NAME, OUTPUT_DIR_NAME, REPO_NAME_PREFIX
from pipeline.context import ClientContext
from pipeline.env_utils import get_env_var  # env "puro"
from pipeline.exceptions import EXIT_CODES, ConfigError, PipelineError, PushError
from pipeline.logging_utils import get_structured_logger
from pipeline.path_utils import ensure_valid_slug, ensure_within  # SSoT guardia STRONG

# --- Adapter obbligatorio per i contenuti BOOK (README/SUMMARY) ------------------
try:
    from adapters.book_purity import ensure_book_purity as _ensure_book_purity
    from semantic.api import write_summary_and_readme as _write_summary_and_readme
except Exception as e:
    raise ConfigError(
        "Adapter mancante o non importabile: "
        f"semantic.api.write_summary_and_readme / adapters.book_purity.ensure_book_purity ({e})"
    )

# Push GitHub (wrapper repo) – obbligatorio, senza fallback
try:
    # firma: (context, *, github_token: str, do_push=True, force_push=False, force_ack=None,
    # redact_logs=False)
    from pipeline.github_utils import push_output_to_github as _push_output_to_github

    push_output_to_github: Optional[Callable[..., None]] = _push_output_to_github
except Exception:
    push_output_to_github = None  # verra' gestito in _git_push

# Solo per type-checking: Protocol del contesto richiesto da github_utils
if TYPE_CHECKING:  # pragma: no cover - solo analisi statica
    from pipeline.github_utils import _SupportsContext  # noqa: F401


# ---------- Helpers UX ----------
def _prompt(msg: str) -> str:
    """Raccoglie input da CLI (abilitato solo negli orchestratori)."""
    return input(msg).strip()


# ---------- Preflight book/ (delegato al nuovo adapter) ----------


# ---------- Push GitHub (util repo, no fallback) ----------
def _git_push(context: ClientContext, logger: logging.Logger) -> None:
    """Esegue il push su GitHub usando pipeline.github_utils.push_output_to_github."""
    if push_output_to_github is None:
        raise ConfigError("push_output_to_github non disponibile: verifica le dipendenze di pipeline.github_utils")

    token = get_env_var("GITHUB_TOKEN", required=True)
    if token is None or not str(token).strip():
        raise ConfigError("Variabile d'ambiente GITHUB_TOKEN mancante o vuota")

    # Validazioni esplicite (no assert per S101)
    if getattr(context, "md_dir", None) is None:
        raise ConfigError("context.md_dir non impostato")
    if getattr(context, "base_dir", None) is None:
        raise ConfigError("context.base_dir non impostato")

    try:
        # usa cast(Any, ...) per evitare import del Protocol a runtime
        push_output_to_github(
            cast(Any, context),
            github_token=token,
            do_push=True,
            force_push=False,
            force_ack=None,
            redact_logs=getattr(context, "redact_logs", False),
        )
        logger.info("Git push completato (github_utils)")
    except Exception as e:
        raise PushError(f"Git push fallito tramite github_utils: {e}") from e


# ---------- MAIN orchestrator (solo push) ----------
def onboarding_full_main(
    slug: str,
    *,
    non_interactive: bool = False,
    run_id: Optional[str] = None,
) -> None:
    """Orchestratore della fase Full: preflight book/ e push GitHub."""
    early_logger = get_structured_logger("onboarding_full", run_id=run_id)
    slug = ensure_valid_slug(slug, interactive=not non_interactive, prompt=_prompt, logger=early_logger)

    # Carica il contesto PRIMA di determinare i path, per rispettare override (es. REPO_ROOT_DIR)
    context: ClientContext = ClientContext.load(
        slug=slug,
        interactive=not non_interactive,
        require_env=False,
        run_id=run_id,
    )

    # Preferisci i path dal contesto; fallback deterministico solo se assenti
    ctx_base = getattr(context, "base_dir", None)
    base_dir: Path = (
        cast(Path, ctx_base) if ctx_base is not None else (Path(OUTPUT_DIR_NAME) / f"{REPO_NAME_PREFIX}{slug}")
    )
    log_dir = base_dir / LOGS_DIR_NAME
    log_file = log_dir / LOG_FILE_NAME
    ensure_within(base_dir, log_dir)
    ensure_within(log_dir, log_file)
    log_dir.mkdir(parents=True, exist_ok=True)

    logger = get_structured_logger("onboarding_full", log_file=log_file, context=context, run_id=run_id)
    logger.info("Avvio onboarding_full (PUSH GitHub)")

    # 1) README/SUMMARY in book/ (senza fallback)
    try:
        _write_summary_and_readme(context, logger, slug=slug)
    except Exception as e:
        raise ConfigError(f"Impossibile generare/validare README/SUMMARY in book/: {e}") from e

    # 2) Preflight book/ (solo .md; ignora .md.fp, builder files e sottodirectory di build)
    _ensure_book_purity(context, logger)

    # 3) Conferma in interattivo (nessun prompt in non-interactive)
    do_push = True
    if not non_interactive:
        ans = (_prompt("Eseguo push su GitHub? (Y/n): ") or "y").lower()
        if ans.startswith("n"):
            do_push = False

    if do_push:
        _git_push(context, logger)

    logger.info("Completato (fase push)")


# ---------- CLI ----------
def _parse_args() -> argparse.ArgumentParser:
    """Costruisce il parser CLI per onboarding_full (il parsing avviene nel main)."""
    p = argparse.ArgumentParser(description="Onboarding FULL (solo push GitHub)")
    p.add_argument("slug_pos", nargs="?", help="Slug cliente (posizionale)")
    p.add_argument("--slug", type=str, help="Slug cliente")
    p.add_argument("--non-interactive", action="store_true", help="Esecuzione senza prompt")
    return p


if __name__ == "__main__":
    """Entrypoint CLI dell'orchestratore onboarding_full."""
    args = _parse_args().parse_args()
    run_id = uuid.uuid4().hex
    early_logger = get_structured_logger("onboarding_full", run_id=run_id)

    unresolved_slug = args.slug_pos or args.slug
    if not unresolved_slug and args.non_interactive:
        early_logger.error("Errore: in modalita' non interattiva e' richiesto --slug (o slug posizionale).")
        sys.exit(EXIT_CODES.get("ConfigError", 2))
    try:
        slug = ensure_valid_slug(
            unresolved_slug,
            interactive=not args.non_interactive,
            prompt=_prompt,
            logger=early_logger,
        )
    except ConfigError:
        sys.exit(EXIT_CODES.get("ConfigError", 2))

    try:
        onboarding_full_main(
            slug=slug,
            non_interactive=args.non_interactive,
            run_id=run_id,
        )
        sys.exit(0)
    except KeyboardInterrupt:
        sys.exit(130)
    except ConfigError as e:
        early_logger.error("Uscita per ConfigError: " + str(e))
        sys.exit(EXIT_CODES.get("ConfigError", 2))
    except PipelineError as e:
        code = EXIT_CODES.get(e.__class__.__name__, EXIT_CODES.get("PipelineError", 1))
        early_logger.error("Uscita per PipelineError: " + str(e))
        sys.exit(code)
    except Exception as e:
        early_logger.error("Uscita per errore non gestito: " + str(e))
        sys.exit(EXIT_CODES.get("PipelineError", 1))
