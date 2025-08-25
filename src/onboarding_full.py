#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Onboarding FULL (fase 2): Push GitHub.
- Presuppone che la fase di semantic onboarding sia già stata eseguita.
- Esegue esclusivamente il push su GitHub tramite pipeline.github_utils.
- Masking centralizzato nel logger; env_utils resta “puro”.
- Path-safety STRONG per le scritture (log) via ensure_within.
- Orchestratore gestisce I/O utente e codici di uscita; moduli sottostanti non fanno prompt/exit.
"""
from __future__ import annotations

import argparse
import sys
import uuid
from pathlib import Path
from typing import Optional

from pipeline.logging_utils import get_structured_logger
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
from pipeline.env_utils import get_env_var, compute_redact_flag   # env “puro”; flag redazione canonico

# --- Adapter obbligatorio per i contenuti BOOK (README/SUMMARY) ------------------
try:
    from adapters.content_fallbacks import ensure_readme_summary as _ensure_readme_summary
except Exception as e:
    # Niente fallback locale: l'adapter è richiesto esplicitamente
    raise ConfigError(f"Adapter mancante o non importabile: adapters.content_fallbacks.ensure_readme_summary ({e})")

# Push GitHub (wrapper repo) – obbligatorio, senza fallback
try:
    # (context, *, github_token:str, do_push=True, force_push=False, force_ack=None, redact_logs=False)
    from pipeline.github_utils import push_output_to_github
except Exception:
    push_output_to_github = None  # verrà gestito in _git_push


# ─────────────── Helpers UX ───────────────
def _prompt(msg: str) -> str:
    return input(msg).strip()


# ─────────────── Push GitHub (util repo, no fallback) ──────────
def _git_push(context: ClientContext, logger) -> None:
    if push_output_to_github is None:
        raise ConfigError("push_output_to_github non disponibile: verifica le dipendenze del modulo pipeline.github_utils")

    # Token letto da env (nessun masking qui; la redazione è gestita dal logger)
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
        # Errore corretto e mappato su EXIT_CODES["PushError"]=40
        raise PushError(f"Git push fallito tramite github_utils: {e}")


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
    # Propagazione uniforme del flag di redazione se mancante (safety-belt)
    if not hasattr(context, "redact_logs"):
        context.redact_logs = compute_redact_flag(getattr(context, "env", {}), getattr(context, "log_level", "INFO"))

    logger = get_structured_logger("onboarding_full", log_file=log_file, context=context, run_id=run_id)
    logger.info("🚀 Avvio onboarding_full (PUSH GitHub)")

    # 1) Garantire README.md/SUMMARY.md minimi in book/ (idempotente, nessuna semantica)
    try:
        _ensure_readme_summary(context, logger)
    except Exception as e:
        raise ConfigError(f"Impossibile assicurare README/SUMMARY in book/: {e}")

    # Conferma in interattivo (nessun prompt in non-interactive)
    do_push = True
    if not non_interactive:
        ans = (_prompt("Eseguo push su GitHub? (Y/n): ") or "y").lower()
        if ans.startswith("n"):
            do_push = False

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
