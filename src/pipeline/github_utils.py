# SPDX-License-Identifier: GPL-3.0-or-later
# src/pipeline/github_utils.py
"""Utility GitHub per la pipeline Timmy-KB.

Cosa fa
-------
- **Rileva o crea** il repository remoto del cliente (`timmy-kb-<slug>`).
- **Pubblica** i soli file Markdown presenti in `book/` (escludendo `.bak`), preservando lâ€™albero.
- **Gestisce branch di default** con SSoT di chiavi dâ€™ambiente (`DEFAULT_GIT_BRANCH_ENV_KEYS`).
- **Esegue push incrementale** con retry (pull --rebase â†’ nuovo push) oppure
  **force push governato** (`--force-with-lease`) con allow-list di branch e `force_ack`.
- **Sicurezza path**: STRONG guard con `ensure_within` per tutte le scritture/cancellezioni.
- **Credenziali via env**: header HTTP Basic in `GIT_HTTP_EXTRAHEADER` (il token non compare).
- **Working dir temporanea sicura** sotto la base cliente:
  il clone avviene in una sottocartella **non esistente** (no `git clone` in dir giÃ  presente).

API principale (stabile)
------------------------
push_output_to_github(
    context,
    *,
    github_token: str,
    do_push: bool = True,
    force_push: bool = False,
    force_ack: str | None = None,
    redact_logs: bool = False,
) -> None

Dove `context` espone almeno:
  - `slug: str`
  - `md_dir: Path`
  - `env: dict` (opzionale)
  - `base_dir: Path`
"""

from __future__ import annotations

import logging
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from pipeline.constants import DEFAULT_GIT_BRANCH_ENV_KEYS
from pipeline.env_utils import get_env_var
from pipeline.exceptions import ForcePushError, PipelineError, PushError
from pipeline.logging_utils import get_structured_logger, phase_scope, redact_secrets
from pipeline.path_utils import ensure_within, is_safe_subpath, iter_safe_paths, sorted_paths  # sicurezza path
from pipeline.proc_utils import CmdError  # âœ… timeout/retry wrapper

from .github_env_flags import get_force_allowed_branches, is_branch_allowed_for_force, should_push
from .github_lease import LEASE_DIRNAME, LeaseLock
from .github_push_flow import _force_push_with_lease as _force_push_with_lease_flow
from .github_push_flow import _prepare_repo
from .github_push_flow import _push_with_retry as _push_with_retry_flow
from .github_push_flow import _stage_and_commit
from .github_push_flow import _stage_changes as _stage_changes_flow
from .github_types import SupportsContext

# Logger di modulo (fallback); nei flussi reali useremo quello contestualizzato
logger: logging.Logger = get_structured_logger("pipeline.github_utils")


@dataclass
class _PushPlan:
    base_dir: Path
    book_dir: Path
    md_files: Sequence[Path]
    default_branch: str
    lock_config: dict[str, Any]


def _resolve_default_branch(context: SupportsContext) -> str:
    """Risoluzione branch di default con fallback a 'main'."""
    env_map = getattr(context, "env", None)
    if isinstance(env_map, Mapping):
        for key in DEFAULT_GIT_BRANCH_ENV_KEYS:
            value = env_map.get(key)
            if isinstance(value, str):
                candidate = value.strip()
                if candidate:
                    return candidate
            elif value is not None:
                candidate = str(value).strip()
                if candidate:
                    return candidate
    for key in DEFAULT_GIT_BRANCH_ENV_KEYS:
        value = get_env_var(key, default=None, required=False)
        if isinstance(value, str):
            candidate = value.strip()
            if candidate:
                return candidate
        elif value is not None:
            candidate = str(value).strip()
            if candidate:
                return candidate
    return "main"


def _build_push_plan(
    context: SupportsContext,
    *,
    github_token: str,
    do_push: bool,
    redact_logs: bool,
    logger: logging.Logger,
) -> _PushPlan | None:
    if not github_token:
        raise PipelineError(
            "GITHUB_TOKEN mancante o vuoto: impossibile eseguire push.",
            slug=getattr(context, "slug", None),
        )

    if not should_push(context):
        logger.info(
            "Push GitHub disabilitato da variabili d'ambiente (TIMMY_NO_GITHUB/SKIP_GITHUB_PUSH).",
            extra={"slug": context.slug},
        )
        return None

    book_dir = context.md_dir
    if not book_dir.exists():
        raise PipelineError(
            f"Cartella book non trovata: {book_dir}",
            slug=context.slug,
            file_path=book_dir,
        )

    base_dir = getattr(context, "base_dir", None)
    if not base_dir:
        raise PipelineError("Context.base_dir assente: impossibile determinare la working area.", slug=context.slug)
    try:
        ensure_within(base_dir, book_dir)
    except Exception:
        raise PipelineError(
            f"Percorso book non sicuro: {book_dir} (fuori da {base_dir})",
            slug=context.slug,
            file_path=book_dir,
        )

    md_files = _collect_md_files(book_dir)
    if not md_files:
        msg = "📄 Nessun file .md valido trovato nella cartella book. Push annullato."
        logger.warning(redact_secrets(msg) if redact_logs else msg, extra={"slug": context.slug})
        return None

    if not do_push:
        msg = "Push disattivato: do_push=False (dry run a carico dell'orchestratore)."
        logger.info(redact_secrets(msg) if redact_logs else msg, extra={"slug": context.slug})
        return None

    default_branch = _resolve_default_branch(context)
    lock_config = _resolve_lock_config(context)

    return _PushPlan(
        base_dir=base_dir,
        book_dir=book_dir,
        md_files=tuple(md_files),
        default_branch=default_branch,
        lock_config=lock_config,
    )


def _collect_md_files(book_dir: Path) -> list[Path]:
    """Seleziona file .md validi (no .bak), ricorsivamente, con ordinamento deterministico."""
    md_iter = sorted_paths(
        (
            f
            for f in iter_safe_paths(book_dir, include_dirs=False, include_files=True, suffixes=(".md",))
            if not f.name.endswith(".bak") and is_safe_subpath(f, book_dir)
        ),
        base=book_dir,
    )
    return list(md_iter)


def _coerce_positive_float(value: Any, *, default: float, minimum: float) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return default
    if numeric < minimum:
        return minimum
    return numeric


def _resolve_lock_config(context: SupportsContext) -> dict[str, Any]:
    env_map = getattr(context, "env", {}) or {}
    timeout_s = _coerce_positive_float(
        env_map.get("TIMMY_GITHUB_LOCK_TIMEOUT_S") or os.environ.get("TIMMY_GITHUB_LOCK_TIMEOUT_S"),
        default=10.0,
        minimum=0.1,
    )
    poll_interval_s = _coerce_positive_float(
        env_map.get("TIMMY_GITHUB_LOCK_POLL_S") or os.environ.get("TIMMY_GITHUB_LOCK_POLL_S"),
        default=0.25,
        minimum=0.05,
    )
    dirname = (
        str(
            env_map.get("TIMMY_GITHUB_LOCK_DIRNAME") or os.environ.get("TIMMY_GITHUB_LOCK_DIRNAME") or LEASE_DIRNAME
        ).strip()
        or LEASE_DIRNAME
    )
    return {"timeout_s": timeout_s, "poll_interval_s": poll_interval_s, "dirname": dirname}


def _cleanup_tmp_dir(tmp_dir: Path, base_dir: Path) -> None:
    """
    Cleanup working dir temporanea:
    - rimuove la dir di clone,
    - prova a rimuovere anche il genitore temporaneo se creato da `_prepare_tmp_dir`.
    """
    try:
        if isinstance(tmp_dir, Path):
            # rimuovi la dir di clone se esiste
            if tmp_dir.exists():
                ensure_within(base_dir, tmp_dir)
                shutil.rmtree(tmp_dir, ignore_errors=True)
            # prova a rimuovere anche il parent
            parent = tmp_dir.parent
            if parent and parent != base_dir and parent.exists():
                ensure_within(base_dir, parent)
                shutil.rmtree(parent, ignore_errors=True)
    except Exception:
        # Non bloccare l'esecuzione in caso di errore di cleanup
        pass


# ----------------------------
# API pubblica (invariata)
# ----------------------------


def push_output_to_github(
    context: SupportsContext,
    *,
    github_token: str,
    do_push: bool = True,
    force_push: bool = False,
    force_ack: str | None = None,
    redact_logs: bool = False,
) -> None:
    """Esegue il push dei file `.md` presenti nella cartella `book` del cliente su GitHub."""
    local_logger = get_structured_logger("pipeline.github_utils", context=context)

    global logger
    logger = local_logger

    plan = _build_push_plan(
        context,
        github_token=github_token,
        do_push=do_push,
        redact_logs=redact_logs,
        logger=local_logger,
    )
    if plan is None:
        return

    local_logger.info(
        "Preparazione push su GitHub",
        extra={"slug": context.slug, "branch": plan.default_branch},
    )
    lock = LeaseLock(plan.base_dir, slug=context.slug, logger=local_logger, **plan.lock_config)
    lock.acquire()

    repo = None
    tmp_dir: Path | None = None
    env: dict[str, Any] | None = None
    try:
        with phase_scope(local_logger, stage="prepare_repo", customer=context.slug) as prepare_phase:
            repo, tmp_dir, env = _prepare_repo(
                context,
                github_token=github_token,
                md_files=list(plan.md_files),
                default_branch=plan.default_branch,
                base_dir=plan.base_dir,
                book_dir=plan.book_dir,
                redact_logs=redact_logs,
                logger=local_logger,
            )
            try:
                prepare_phase.set_artifacts(len(plan.md_files))
            except Exception:
                prepare_phase.set_artifacts(None)

        with phase_scope(local_logger, stage="stage_changes", customer=context.slug) as stage_phase:
            committed = _stage_changes_flow(
                tmp_dir,
                env,
                slug=context.slug,
                force_ack=force_ack,
                logger=local_logger,
                stage_and_commit_fn=_stage_and_commit,
            )
            try:
                stage_phase.set_artifacts(1 if committed else 0)
            except Exception:
                stage_phase.set_artifacts(None)
        if not committed:
            return

        push_stage = "force_push" if force_push else "push_with_retry"
        with phase_scope(local_logger, stage=push_stage, customer=context.slug):
            if force_push:
                if not force_ack:
                    raise ForcePushError(
                        "Force push richiesto senza ACK. Serve force_ack valorizzato.",
                        slug=context.slug,
                    )
                if not is_branch_allowed_for_force(plan.default_branch, context, allow_if_unset=True):
                    patterns = get_force_allowed_branches(context)
                    patterns_str = ", ".join(patterns) if patterns else "(lista vuota)"
                    raise ForcePushError(
                        f"Force push NON consentito sul branch '{plan.default_branch}'. "
                        f"Branch ammessi (GIT_FORCE_ALLOWED_BRANCHES): {patterns_str}",
                        slug=context.slug,
                    )

                _force_push_with_lease_flow(
                    tmp_dir,
                    env,
                    plan.default_branch,
                    force_ack,
                    logger=local_logger,
                    redact_logs=redact_logs,
                )
            else:
                _push_with_retry_flow(
                    tmp_dir,
                    env,
                    plan.default_branch,
                    logger=local_logger,
                    redact_logs=redact_logs,
                )

        local_logger.info(
            "Push GitHub completato",
            extra={"slug": context.slug, "repo": repo.full_name, "branch": plan.default_branch},
        )
    except CmdError as e:
        tail = (e.stderr or e.stdout or "").strip()
        tail = tail[-2000:] if tail else ""
        raw = f"Errore Git: {e.op or 'git'} (tentativo {e.attempt}/{e.attempts}) -> {tail}"
        safe = redact_secrets(raw) if redact_logs else raw
        raise PushError(safe, slug=context.slug) from e
    finally:
        lock.release()
        if tmp_dir is not None:
            _cleanup_tmp_dir(tmp_dir, plan.base_dir)
