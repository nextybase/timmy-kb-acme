#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Onboarding FULL (fase 2): push GitHub e preflight su `book/`.

Questo orchestratore:
- Presuppone che la fase di semantic onboarding sia già stata eseguita.
- Esegue **esclusivamente** il push su GitHub tramite `pipeline.github_utils`.
- Esegue un preflight su `book/`: accetta solo `.md` (i placeholder `.md.fp` sono tollerati).
- Tollerati in `book/`: builder files (book.json/package.json/lockfile) e sottodirectory
  `_book/`, `node_modules/`, `.cache/`, `.tmp/`, `.git` (ignorate).
- Adotta path-safety STRONG tramite `ensure_within`.
- Gestisce I/O utente e codici di uscita a livello orchestratore; i moduli sottostanti
  non fanno prompt/exit.
"""
from __future__ import annotations

import argparse
import logging
import sys
import uuid
from pathlib import Path
from typing import Optional, List, TYPE_CHECKING, cast, Callable

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
    from pipeline.github_utils import push_output_to_github as _push_output_to_github

    push_output_to_github: Callable[..., None] | None = _push_output_to_github
except Exception:
    push_output_to_github = None  # verrà gestito in _git_push

# Solo per type-checking: Protocol del contesto richiesto da github_utils
if TYPE_CHECKING:  # pragma: no cover - solo analisi statica
    from pipeline.github_utils import _SupportsContext  # noqa: F401


# ─────────────── Helpers UX ───────────────
def _prompt(msg: str) -> str:
    """Raccoglie input da CLI (abilitato **solo** negli orchestratori).

    Args:
        msg: Messaggio mostrato all’utente.

    Returns:
        La risposta dell’utente, normalizzata con ``strip()``.
    """
    return input(msg).strip()


# ─────────────── Preflight book/ (senza cancellazioni) ───────────────
_ALLOWED_SPECIAL = {".ds_store"}  # piccoli artefatti innocui

# File di builder che tolleriamo in book/ per supportare la preview (non vengono rimossi)
_ALLOWED_BUILDER_FILES = {
    "book.json",
    "package.json",
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
}

# Sottodirectory SOTTO book/ da ignorare completamente (preview/build cache)
_IGNORED_SUBDIRS_UNDER_BOOK = {"_book", "node_modules", ".cache", ".tmp", ".git"}


def _is_under_ignored_subdir(book_dir: Path, p: Path) -> bool:
    """Ritorna True se `p` si trova sotto una delle sottodirectory ignorate di `book/`.

    Args:
        book_dir: Cartella `book/` di riferimento.
        p: Percorso da verificare.

    Returns:
        True se `p` è sotto `_book/`, `node_modules/`, `.cache/`, `.tmp/` o `.git`, altrimenti False.
    """
    try:
        rel = p.relative_to(book_dir)
    except ValueError:
        return False
    parts = rel.parts
    return bool(parts) and parts[0].lower() in _IGNORED_SUBDIRS_UNDER_BOOK


def _violations_in_book(book_dir: Path) -> List[Path]:
    """Individua i file **non consentiti** presenti in `book/`.

    Regole:
      - Consentiti: `.md`, `.md.fp`, `_ALLOWED_SPECIAL`, `_ALLOWED_BUILDER_FILES`.
      - Ignorate: sottodirectory elencate in `_IGNORED_SUBDIRS_UNDER_BOOK`.

    Args:
        book_dir: Cartella `book/` da ispezionare.

    Returns:
        Lista di percorsi che violano le regole (vuota se nessuna violazione).
    """
    bad: List[Path] = []
    for p in book_dir.rglob("*"):
        if not p.is_file():
            continue
        # ignora build/preview cache sotto book/
        if _is_under_ignored_subdir(book_dir, p):
            continue

        name = p.name.lower()
        # consenti markdown e placeholder
        if name.endswith(".md") or name.endswith(".md.fp"):
            continue
        # consenti file speciali innocui e builder artifacts
        if name in _ALLOWED_SPECIAL or name in _ALLOWED_BUILDER_FILES:
            continue

        bad.append(p)
    return bad


def _preflight_book_dir(base_dir: Path, logger: logging.Logger) -> None:
    """Esegue il preflight della cartella `book/` per garantire il contratto “solo .md”.

    Controlli:
      - Esistenza della cartella `book/`.
      - Assenza di file non Markdown (tollerati `.md.fp`, builder files e cache di build).
      - Log informativo per eventuali directory ignorate presenti.

    Args:
        base_dir: Base della sandbox cliente (es. `output/timmy-kb-<slug>`).
        logger: Logger strutturato per audit.

    Raises:
        PipelineError: se vengono trovate violazioni (file non consentiti).
    """
    book_dir = base_dir / "book"
    ensure_within(base_dir, book_dir)
    if not book_dir.exists():
        raise PipelineError(f"Cartella book/ non trovata: {book_dir}")

    logger.info("Preflight book/", extra={"book": str(book_dir)})

    bad = _violations_in_book(book_dir)
    if bad:
        examples = []
        for p in bad[:5]:
            try:
                rel = p.relative_to(base_dir).as_posix()
            except Exception:
                rel = str(p)
            examples.append(rel)
        raise PipelineError(
            "Violazione contratto: in book/ devono esserci solo file .md (i placeholder .md.fp sono tollerati). "
            f"Trovati {len(bad)} non-md, es: {examples}. "
            "Sposta risorse non-md altrove (es. assets/) o convertile."
        )

    # log informativo se esistono directory ignorate
    for sub in sorted(_IGNORED_SUBDIRS_UNDER_BOOK):
        d = book_dir / sub
        if d.exists():
            logger.info(
                f"Directory {sub}/ presente in book/: ignorata nel preflight/push.",
                extra={"dir_tail": tail_path(d)},
            )


# ─────────────── Push GitHub (util repo, no fallback) ───────────────
def _git_push(context: ClientContext, logger: logging.Logger) -> None:
    """Esegue il push su GitHub usando `pipeline.github_utils.push_output_to_github`.

    Precondizioni:
        - Modulo `pipeline.github_utils` disponibile.
        - Variabile d'ambiente `GITHUB_TOKEN` impostata.

    Args:
        context: Contesto cliente (con metadati, percorsi e logger).
        logger: Logger strutturato per tracking.

    Raises:
        ConfigError: se la funzione di push non è disponibile o manca il token.
        PushError: se il push fallisce.
    """
    if push_output_to_github is None:
        raise ConfigError(
            "push_output_to_github non disponibile: verifica le dipendenze del modulo pipeline.github_utils"
        )

    token = get_env_var("GITHUB_TOKEN", required=True)
    # Assicurazioni formali per Pylance (nessun cambio di logica):
    assert token is not None
    assert context.md_dir is not None
    assert context.base_dir is not None

    try:
        push_output_to_github(
            cast("_SupportsContext", context),
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
    """Orchestratore della fase **Full**: preflight `book/` e push GitHub.

    Args:
        slug: Identificatore cliente (slug) della sandbox `output/`.
        non_interactive: Se `True`, esecuzione batch senza prompt (push non confermato).
        run_id: ID di correlazione per i log.

    Raises:
        ConfigError: per problemi di configurazione/adapter.
        PipelineError: per violazioni del preflight o altri errori di pipeline.
    """
    early_logger = get_structured_logger("onboarding_full", run_id=run_id)
    slug = ensure_valid_slug(
        slug, interactive=not non_interactive, prompt=_prompt, logger=early_logger
    )

    base_dir = Path(OUTPUT_DIR_NAME) / f"{REPO_NAME_PREFIX}{slug}"
    log_dir = base_dir / LOGS_DIR_NAME
    log_file = log_dir / LOG_FILE_NAME
    ensure_within(base_dir, log_dir)
    ensure_within(log_dir, log_file)
    log_dir.mkdir(parents=True, exist_ok=True)

    context: ClientContext = ClientContext.load(
        slug=slug,
        interactive=not non_interactive,
        require_env=False,
        run_id=run_id,
    )

    logger = get_structured_logger(
        "onboarding_full", log_file=log_file, context=context, run_id=run_id
    )
    logger.info("🚀 Avvio onboarding_full (PUSH GitHub)")

    # 1) README/SUMMARY minimi in book/ (idempotente)
    try:
        _ensure_readme_summary(context, logger)
    except Exception as e:
        raise ConfigError(f"Impossibile assicurare README/SUMMARY in book/: {e}") from e

    # 2) Preflight book/ (solo .md; ignora .md.fp, builder files e sottodirectory di build)
    _preflight_book_dir(base_dir, logger)

    # 3) Conferma in interattivo (nessun prompt in non-interactive)
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
    """Costruisce il parser CLI per `onboarding_full`.

    Opzioni:
        slug_pos: Argomento posizionale per lo slug cliente.
        --slug: Slug cliente (alternativa al posizionale).
        --non-interactive: Esecuzione senza prompt.

    Returns:
        argparse.ArgumentParser già configurato (il parsing avviene più avanti).
    """
    p = argparse.ArgumentParser(description="Onboarding FULL (solo push GitHub)")
    p.add_argument("slug_pos", nargs="?", help="Slug cliente (posizionale)")
    p.add_argument("--slug", type=str, help="Slug cliente")
    p.add_argument("--non-interactive", action="store_true", help="Esecuzione senza prompt")
    return p


if __name__ == "__main__":
    """Entrypoint CLI dell’orchestratore `onboarding_full`.

    Flusso:
      - Parsing degli argomenti con `_parse_args()`.
      - Generazione `run_id` per i log strutturati.
      - Validazione iniziale dello `slug`.
      - Invocazione di `onboarding_full_main` con le opzioni selezionate.
      - Gestione degli exit code coerente con `EXIT_CODES`.
    """
    args = _parse_args().parse_args()
    run_id = uuid.uuid4().hex
    early_logger = get_structured_logger("onboarding_full", run_id=run_id)

    unresolved_slug = args.slug_pos or args.slug
    if not unresolved_slug and args.non_interactive:
        early_logger.error(
            "Errore: in modalità non interattiva è richiesto --slug (o slug posizionale)."
        )
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
