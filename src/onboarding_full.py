#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# src/onboarding_full.py
"""
Onboarding FULL (fase 2): Push GitHub.

Cosa fa
-------
- Presuppone che la fase di semantic onboarding sia già stata eseguita.
- Esegue **solo** il push su GitHub tramite `pipeline.github_utils.push_output_to_github`.
- Garantisce che in `book/` siano presenti file pubblicabili:
  * per default SOLO `.md`
  * i placeholder/artefatti con suffisso **`.md.fp` vengono IGNORATI di default**
- Masking centralizzato nel logger; `env_utils` resta “puro”.
- Path-safety STRONG per i log via `ensure_within`.
- Orchestratore gestisce I/O utente e codici di uscita; i moduli sottostanti non fanno prompt/exit.
"""
from __future__ import annotations

import argparse
import sys
import uuid
import logging
from pathlib import Path
from typing import Optional, List

from pipeline.logging_utils import get_structured_logger, tail_path
from pipeline.exceptions import (
    PipelineError,
    ConfigError,
    EXIT_CODES,
    PushError,
)
from pipeline.context import ClientContext
from pipeline.constants import (
    OUTPUT_DIR_NAME,
    LOGS_DIR_NAME,
    LOG_FILE_NAME,
    REPO_NAME_PREFIX,
)
from pipeline.path_utils import ensure_valid_slug, ensure_within  # SSoT guardia STRONG
from pipeline.env_utils import get_env_var  # env “puro”

# --- Adapter obbligatorio per i contenuti BOOK (README/SUMMARY) ------------------
try:
    from adapters.content_fallbacks import ensure_readme_summary as _ensure_readme_summary
except Exception as e:
    raise ConfigError(
        f"Adapter mancante o non importabile: adapters.content_fallbacks.ensure_readme_summary ({e})"
    )

# Push GitHub (wrapper repo) – obbligatorio, senza fallback
try:
    # (context, *, github_token:str, do_push=True, force_push=False, force_ack=None, redact_logs=False)
    from pipeline.github_utils import push_output_to_github
except Exception:
    push_output_to_github = None  # verrà gestito in _git_push


# ─────────────── Helpers UX ───────────────
def _prompt(msg: str) -> str:
    return input(msg).strip()


# ─────────────── Book scope checks ──────────
def _book_md_only_guard(
    base_dir: Path,
    logger: logging.Logger,
    *,
    allow_md_fp: bool = True,  # default: ignora .md.fp senza bisogno di flag
) -> List[Path]:
    """
    Verifica che `book/` contenga solo file ammessi.
    - Modalità default: SOLO .md; i file con suffisso `.md.fp` sono ignorati (placeholder).
    Ritorna la lista dei `.md` trovati.
    """
    book_dir = base_dir / "book"
    if not book_dir.exists():
        raise PushError(f"Directory book/ non trovata: {book_dir}")

    md_files = [p for p in book_dir.rglob("*.md") if p.is_file()]
    all_files = [p for p in book_dir.rglob("*") if p.is_file()]

    ignored: List[Path] = []
    non_md: List[Path] = []
    for p in all_files:
        if p.suffix.lower() == ".md":
            continue
        name = p.name.lower()
        if allow_md_fp and name.endswith(".md.fp"):
            ignored.append(p)
            continue
        # ignora file di sistema noti
        if name in (".ds_store", "thumbs.db"):
            ignored.append(p)
            continue
        non_md.append(p)

    logger.info(
        "Preflight book/",
        extra={
            "book": str(book_dir),
            "md_files": len(md_files),
            "ignored_files": len(ignored),
            "non_md_files": len(non_md),
        },
    )

    if non_md:
        examples = [tail_path(p) for p in non_md[:5]]
        raise PushError(
            "Violazione contratto: in book/ devono esserci solo file .md "
            "(i placeholder .md.fp sono tollerati). "
            f"Trovati {len(non_md)} non-md, es: {examples}. "
            "Sposta risorse non-md altrove (es. assets/) o convertile."
        )

    if not md_files:
        raise PushError("Nessun file .md in book/: niente da pubblicare.")

    # Path-safety preventiva
    for p in md_files:
        ensure_within(book_dir, p)

    if ignored:
        logger.warning(
            "File ignorati durante il preflight",
            extra={"samples": [tail_path(p) for p in ignored[:5]]},
        )

    return md_files


# ─────────────── Push GitHub (util repo, no fallback) ──────────
def _git_push(context: ClientContext, logger: logging.Logger) -> None:
    if push_output_to_github is None:
        raise ConfigError(
            "push_output_to_github non disponibile: verifica le dipendenze del modulo pipeline.github_utils"
        )

    token = get_env_var("GITHUB_TOKEN", required=True)

    try:
        push_output_to_github(
            context,
            github_token=token,
            do_push=True,
            force_push=False,
            force_ack=None,
            redact_logs=getattr(context, "redact_logs", False),
        )
        logger.info("Git push completato (github_utils)")
    except Exception as e:
        raise PushError(f"Git push fallito tramite github_utils: {e}") from e


# ─────────────── MAIN orchestrator (solo push) ───────────────
def onboarding_full_main(
    slug: str,
    *,
    non_interactive: bool = False,
    run_id: Optional[str] = None,
) -> None:
    early_logger = get_structured_logger("onboarding_full", run_id=run_id)
    slug = ensure_valid_slug(slug, interactive=not non_interactive, prompt=_prompt, logger=early_logger)

    # Path log sotto la sandbox cliente con guardia STRONG
    base_dir = Path(OUTPUT_DIR_NAME) / f"{REPO_NAME_PREFIX}{slug}"
    log_dir = base_dir / LOGS_DIR_NAME
    log_file = log_dir / LOG_FILE_NAME
    ensure_within(base_dir, log_dir)
    ensure_within(log_dir, log_file)
    log_dir.mkdir(parents=True, exist_ok=True)

    # Context + logger coerenti con orchestratori
    context: ClientContext = ClientContext.load(
        slug=slug,
        interactive=not non_interactive,
        require_env=False,
        run_id=run_id,
    )

    logger = get_structured_logger("onboarding_full", log_file=log_file, context=context, run_id=run_id)
    logger.info("🚀 Avvio onboarding_full (PUSH GitHub)")

    # 1) Garantire README.md/SUMMARY.md minimi in book/ (idempotente, nessuna semantica)
    try:
        _ensure_readme_summary(context, logger)
    except Exception as e:
        raise ConfigError(f"Impossibile assicurare README/SUMMARY in book/: {e}") from e

    # 2) Contratto di pubblicazione: .md (+ .md.fp ignorati di default)
    md_files = _book_md_only_guard(base_dir, logger, allow_md_fp=True)
    logger.info("Contratto book/ OK", extra={"samples": [tail_path(p) for p in md_files[:5]]})

    # 3) Conferma in interattivo (nessun prompt in non-interactive)
    do_push = True
    if not non_interactive:
        ans = (_prompt("Eseguo push su GitHub? (Y/n): ") or "y").lower()
        if ans.startswith("n"):
            do_push = False

    # 4) Push
    if do_push:
        _git_push(context, logger)

    logger.info("✅ Completato (fase push)")


# ─────────────── CLI ───────────────
def _parse_args() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Onboarding FULL (solo push GitHub)")
    p.add_argument("slug_pos", nargs="?", help="Slug cliente (posizionale)")
    p.add_argument("--slug", type=str, help="Slug cliente")
    p.add_argument("--non-interactive", action="store_true", help="Esecuzione senza prompt")
    return p


if __name__ == "__main__":
    args = _parse_args().parse_args()
    run_id = uuid.uuid4().hex
    early_logger = get_structured_logger("onboarding_full", run_id=run_id)

    unresolved_slug = args.slug_pos or args.slug
    if not unresolved_slug and args.non_interactive:
        early_logger.error("Errore: in modalità non interattiva è richiesto --slug (o slug posizionale).")
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
        early_logger.error(f"Uscita per PipelineError: {e}")
        sys.exit(code)
    except Exception as e:
        early_logger.error(f"Uscita per errore non gestito: {e}")
        sys.exit(EXIT_CODES.get("PipelineError", 1))
