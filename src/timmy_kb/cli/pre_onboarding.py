#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# src/pre_onboarding.py
"""
Orchestratore della fase di pre-onboarding per Timmy-KB.

Responsabilita:
- Preparare il contesto locale del cliente (`output/timmy-kb-<slug>/...`).
- Validare/minimizzare la configurazione e generare/aggiornare `config.yaml`.
- Creare struttura locale e la struttura remota su Google Drive.
- Caricare `config.yaml` su Drive e aggiornare il config locale con gli ID remoti.

Note architetturali:
- Gli orchestratori gestiscono I/O utente e terminazione del processo
  (mappano eccezioni con `exit_code_for`). I moduli non chiamano `sys.exit()` o `input()`.
- Redazione centralizzata via `logging_utils`.
- Path-safety STRONG: `ensure_within()` prima di ogni write/copy/delete.
- Non stampare segreti nei log (mascheratura parziale per ID e percorsi).
"""

# Regola CLI: dichiarare bootstrap_config esplicitamente (il default e' vietato).

# Fase pre-Vision (MINIMAL): nessun output semantico.
# 1) LOCALE: crea raw/, book/, config/ e scrive config/config.yaml
# 2) DRIVE: crea cartella cliente + raw/ + contrattualistica/ e carica config.yaml

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import logging
import uuid
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from pipeline.artifact_policy import enforce_core_artifacts
from pipeline.beta_flags import is_beta_strict
from pipeline.cli_runner import run_cli_orchestrator
from pipeline.config_utils import (
    get_client_config,
    merge_client_config_from_template,
)
from pipeline.context import ClientContext
from pipeline.drive_bootstrap_service import create_local_structure as _service_create_local_structure
from pipeline.drive_bootstrap_service import drive_phase as _service_drive_phase
from pipeline.drive_bootstrap_service import prepare_context_and_logger as _service_prepare_context_and_logger
from pipeline.env_utils import ensure_dotenv_loaded, get_env_var
from pipeline.exceptions import ArtifactPolicyViolation, ConfigError, PipelineError
from pipeline.logging_utils import (
    get_structured_logger,
)
from pipeline.metrics import start_metrics_server_once
from pipeline.path_utils import (  # STRONG guard SSoT
    ensure_valid_slug,
    ensure_within_and_resolve,
)
from pipeline.runtime_guard import ensure_strict_runtime
from pipeline.tracing import start_root_trace
from pipeline.types import WorkflowResult
from pipeline.workspace_bootstrap import bootstrap_client_workspace as _pipeline_bootstrap_client_workspace
from pipeline.workspace_bootstrap_service import ensure_local_workspace_for_ui as _service_ensure_local_workspace_for_ui
from pipeline.workspace_layout import WorkspaceLayout
from storage import decision_ledger

bootstrap_client_workspace = _pipeline_bootstrap_client_workspace


def _prompt(msg: str) -> str:
    """Raccoglie input da CLI (abilitato solo negli orchestratori)."""
    return input(msg).strip()


def _sync_env(context: ClientContext, *, require_env: bool) -> None:
    """Allinea nel `context.env` le variabili critiche lette da os.environ."""
    for key in ("SERVICE_ACCOUNT_FILE", "DRIVE_ID"):
        if not context.env.get(key):
            val = get_env_var(key, required=require_env)
            if val:
                context.env[key] = val


# ------- FUNZIONI ESTRATTE: piccole, testabili, senza side-effects esterni -------


def _prepare_context_and_logger(
    slug: str,
    *,
    interactive: bool,
    require_drive_env: bool = False,
    run_id: Optional[str],
    client_name: Optional[str],
) -> Tuple[ClientContext, logging.Logger, str]:
    """Wrapper CLI sul servizio runtime di bootstrap context/logger."""
    return _service_prepare_context_and_logger(
        slug,
        interactive=interactive,
        require_drive_env=require_drive_env,
        run_id=run_id,
        client_name=client_name,
        prompt=_prompt,
        bootstrap_workspace_fn=bootstrap_client_workspace,
    )


def _utc_now_iso() -> str:
    return _dt.datetime.now(tz=_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _summarize_error(exc: BaseException) -> str:
    name = type(exc).__name__
    message = str(exc).splitlines()[:1]
    first_line = message[0] if message else "error"
    return f"{name}: {first_line}"


def _build_evidence_refs(layout: WorkspaceLayout, *, extra_refs: list[str] | None = None) -> list[str]:
    slug_value = layout.slug
    if not slug_value:
        raise ConfigError("Slug mancante nel layout durante la costruzione dell'evidence.", slug=slug_value)
    refs = [
        f"slug:{slug_value}",
        _path_ref(layout.config_path, layout),
        _path_ref(layout.repo_root_dir, layout),
    ]
    if extra_refs:
        refs.extend(extra_refs)
    return refs


def _path_ref(path: Path, layout: WorkspaceLayout) -> str:
    try:
        repo_root = layout.repo_root_dir
        rel_path = path.relative_to(repo_root).as_posix() if repo_root else path.as_posix()
    except Exception:
        rel_path = path.as_posix()
    return f"path:{rel_path}"


def _normative_verdict_for_error(exc: BaseException) -> tuple[str, str]:
    if isinstance(exc, ArtifactPolicyViolation):
        return decision_ledger.NORMATIVE_BLOCK, decision_ledger.STOP_CODE_ARTIFACT_POLICY_VIOLATION
    if isinstance(exc, ConfigError):
        exc_code = getattr(exc, "code", None)
        if exc_code == "vision.artifact.missing":
            return decision_ledger.NORMATIVE_BLOCK, decision_ledger.STOP_CODE_VISION_ARTIFACT_MISSING
        if exc_code in ("vision.prompt.missing", "vision.prompt.write_failed"):
            return decision_ledger.NORMATIVE_BLOCK, decision_ledger.STOP_CODE_VISION_PROMPT_FAILURE
        return decision_ledger.NORMATIVE_BLOCK, decision_ledger.STOP_CODE_CONFIG_ERROR
    if isinstance(exc, PipelineError):
        return decision_ledger.NORMATIVE_FAIL, decision_ledger.STOP_CODE_PIPELINE_ERROR
    return decision_ledger.NORMATIVE_FAIL, decision_ledger.STOP_CODE_UNEXPECTED_ERROR


def _deny_rationale(exc: BaseException) -> str:
    if isinstance(exc, ArtifactPolicyViolation):
        return "deny_artifact_policy_violation"
    if isinstance(exc, ConfigError):
        return "deny_config_error"
    if isinstance(exc, PipelineError):
        return "deny_pipeline_error"
    return "deny_unexpected_error"


def _is_local_only_mode(context: ClientContext, *, dry_run: bool) -> bool:
    """Determina se la run deve rimanere 'local-only' basandosi sul flag UI."""
    if dry_run:
        return True
    try:
        cfg = get_client_config(context) or {}
    except Exception as exc:
        raise ConfigError(
            "Impossibile determinare la modalita local-only: configurazione non leggibile.",
            slug=context.slug,
            error=str(exc),
            code="local_only.check_failed",
        ) from exc
    ui_section = cfg.get("ui")
    if not isinstance(ui_section, dict):
        return False
    return bool(ui_section.get("allow_local_only"))


def _create_local_structure(context: ClientContext, logger: logging.Logger, *, client_name: str) -> Path:
    """Wrapper CLI sul servizio runtime di creazione struttura locale."""
    return _service_create_local_structure(
        context,
        logger,
        client_name=client_name,
        bootstrap_workspace_fn=bootstrap_client_workspace,
    )


def _merge_evidence_refs(base: list[str], exc: BaseException) -> list[str]:
    if isinstance(exc, ArtifactPolicyViolation):
        return [*base, *exc.evidence_refs]
    return base


def _hash_file_sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8192), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _resolve_vision_pdf_path(repo_root: Path, candidate: str | Path) -> Path:
    target = Path(candidate)
    if not target.is_absolute():
        target = repo_root / target
    return ensure_within_and_resolve(repo_root, target)


def _validate_vision_artifacts(context: ClientContext, layout: WorkspaceLayout) -> list[str]:
    repo_root = layout.repo_root_dir
    if repo_root is None:
        return []

    config = get_client_config(context) or {}
    vision_cfg = config.get("ai", {}).get("vision")
    if not (isinstance(vision_cfg, dict) and vision_cfg.get("vision_statement_pdf")):
        return []

    pdf_path = _resolve_vision_pdf_path(repo_root, vision_cfg["vision_statement_pdf"])
    if not pdf_path.exists() or not pdf_path.is_file():
        raise ConfigError(
            "VisionStatement.pdf mancante o non leggibile nel workspace.",
            slug=context.slug,
            file_path=str(pdf_path),
            code="vision.artifact.missing",
        )

    prompt_path = layout.config_path.parent / "assistant_vision_system_prompt.txt"
    if not prompt_path.exists() or not prompt_path.is_file():
        raise ConfigError(
            "System prompt Vision mancante nel workspace.",
            slug=context.slug,
            file_path=str(prompt_path),
            code="vision.prompt.missing",
        )

    return [
        f"vision_pdf_sha256:{_hash_file_sha256(pdf_path)}",
        f"vision_prompt_sha256:{_hash_file_sha256(prompt_path)}",
    ]


# ---- Entry point minimale per la UI (landing solo slug) ----------------------


def ensure_local_workspace_for_ui(
    slug: str,
    client_name: Optional[str] = None,
    vision_statement_pdf: Optional[bytes] = None,
) -> Path:
    """Wrapper CLI sul servizio runtime di bootstrap workspace UI."""
    return _service_ensure_local_workspace_for_ui(
        slug,
        client_name,
        vision_statement_pdf,
        prompt=_prompt,
        get_env_var_fn=get_env_var,
        get_client_config_fn=get_client_config,
        merge_client_config_from_template_fn=merge_client_config_from_template,
        bootstrap_workspace_fn=bootstrap_client_workspace,
    )


def _drive_phase(
    context: ClientContext,
    logger: logging.Logger,
    *,
    config_path: Path,
    client_name: str,
    require_env: bool,
) -> WorkflowResult:
    """Wrapper CLI sul servizio runtime della fase Drive."""
    return _service_drive_phase(
        context,
        logger,
        config_path=config_path,
        client_name=client_name,
        require_env=require_env,
    )


# --------------------------------- ORCHESTRATORE SNELLITO ---------------------------------


def pre_onboarding_main(
    slug: str,
    client_name: Optional[str] = None,
    *,
    interactive: bool = True,
    dry_run: bool = False,
    run_id: Optional[str] = None,
) -> None:
    """Esegue la fase di pre-onboarding per il cliente indicato (orchestratore sottile)."""
    if not dry_run:
        ensure_dotenv_loaded(strict=True)
    run_id = run_id or uuid.uuid4().hex

    context, logger, client_name = _prepare_context_and_logger(
        slug,
        interactive=interactive,
        require_drive_env=False,
        run_id=run_id,
        client_name=client_name,
    )
    if dry_run:
        logger.info("cli.pre_onboarding.offline_mode", extra={"slug": context.slug})
    layout = WorkspaceLayout.from_context(context)
    ledger_conn = None
    ledger_conn = decision_ledger.open_ledger(layout)
    decision_ledger.start_run(
        ledger_conn,
        run_id=run_id,
        slug=context.slug,
        started_at=_utc_now_iso(),
    )

    current_stage = "local_structure"
    vision_evidence_refs: list[str] = []
    try:
        config_path = _create_local_structure(context, logger, client_name=client_name)
        layout = WorkspaceLayout.from_context(context)
        vision_evidence_refs = _validate_vision_artifacts(context, layout)

        local_only_mode = _is_local_only_mode(context, dry_run=dry_run)
        strict_mode = is_beta_strict()
        if local_only_mode:
            if strict_mode:
                reason = "dry-run" if dry_run else "allow_local_only"
                logger.error(
                    "cli.pre_onboarding.local_only_disabled_strict",
                    extra={"slug": context.slug, "mode": reason},
                )
                raise ConfigError(
                    "Modalita local-only/dry-run non supportata in strict pre_onboarding.",
                    slug=context.slug,
                    code="local_only.strict_disallowed",
                )
            enforce_core_artifacts("pre_onboarding", layout=layout)
            reason = "dry-run" if dry_run else "allow_local_only"
            logger.info(
                "cli.pre_onboarding.local_only_mode",
                extra={"slug": context.slug, "local_only_reason": reason},
            )
            logger.info(
                "cli.pre_onboarding.completed",
                extra={
                    "slug": context.slug,
                    "mode": "local-only",
                    "artifacts": 1,
                    "config": str(config_path),
                },
            )
            decision_ledger.record_normative_decision(
                ledger_conn,
                decision_ledger.NormativeDecisionRecord(
                    decision_id=uuid.uuid4().hex,
                    run_id=run_id,
                    slug=context.slug,
                    gate_name="pre_onboarding",
                    from_state=decision_ledger.STATE_WORKSPACE_BOOTSTRAP,
                    to_state=decision_ledger.STATE_SEMANTIC_INGEST,
                    verdict=decision_ledger.NORMATIVE_PASS,
                    subject="workspace_bootstrap",
                    decided_at=_utc_now_iso(),
                    actor="cli.pre_onboarding",
                    evidence_refs=_build_evidence_refs(layout, extra_refs=vision_evidence_refs),
                    reason_code="local_only",
                ),
            )
            return

        current_stage = "drive_phase"
        _drive_phase(
            context,
            logger,
            config_path=config_path,
            client_name=client_name,
            require_env=True,
        )
        enforce_core_artifacts("pre_onboarding", layout=layout)
        logger.info("cli.pre_onboarding.completed", extra={"slug": context.slug, "artifacts": 1})
        decision_ledger.record_normative_decision(
            ledger_conn,
            decision_ledger.NormativeDecisionRecord(
                decision_id=uuid.uuid4().hex,
                run_id=run_id,
                slug=context.slug,
                gate_name="pre_onboarding",
                from_state=decision_ledger.STATE_WORKSPACE_BOOTSTRAP,
                to_state=decision_ledger.STATE_SEMANTIC_INGEST,
                verdict=decision_ledger.NORMATIVE_PASS,
                subject="workspace_bootstrap",
                decided_at=_utc_now_iso(),
                actor="cli.pre_onboarding",
                evidence_refs=_build_evidence_refs(layout, extra_refs=vision_evidence_refs),
                reason_code="ok",
            ),
        )
    except Exception as exc:
        original_error = _summarize_error(exc)
        try:
            verdict, stop_code = _normative_verdict_for_error(exc)
            decision_ledger.record_normative_decision(
                ledger_conn,
                decision_ledger.NormativeDecisionRecord(
                    decision_id=uuid.uuid4().hex,
                    run_id=run_id,
                    slug=context.slug,
                    gate_name="pre_onboarding",
                    from_state=decision_ledger.STATE_WORKSPACE_BOOTSTRAP,
                    to_state=decision_ledger.STATE_SEMANTIC_INGEST,
                    verdict=verdict,
                    subject="workspace_bootstrap",
                    decided_at=_utc_now_iso(),
                    actor="cli.pre_onboarding",
                    evidence_refs=_merge_evidence_refs(
                        _build_evidence_refs(layout, extra_refs=vision_evidence_refs),
                        exc,
                    ),
                    stop_code=stop_code,
                    reason_code=_deny_rationale(exc),
                ),
            )
        except Exception as ledger_exc:
            ledger_error = _summarize_error(ledger_exc)
            logger.error(
                "cli.pre_onboarding.ledger_write_failed",
                extra={
                    "slug": context.slug,
                    "run_id": run_id,
                    "stage": current_stage,
                    "gate": "pre_onboarding",
                    "ledger_error": ledger_error,
                    "original_error": original_error,
                },
            )
            raise PipelineError(
                "Ledger write failed for gate=pre_onboarding "
                f"slug={context.slug} run_id={run_id} stage={current_stage}; "
                f"ledger_error={ledger_error}; original_error={original_error}",
                slug=context.slug,
                run_id=run_id,
            ) from ledger_exc
        logger.exception(
            "cli.pre_onboarding.failed",
            extra={
                "slug": context.slug,
                "stage": current_stage,
                "error": str(exc).splitlines()[:1],
            },
        )
        raise
    finally:
        if ledger_conn is not None:
            ledger_conn.close()


# ------------------------------------ CLI ENTRYPOINT ------------------------------------


def _parse_args() -> argparse.Namespace:
    """Restituisce gli argomenti CLI per l'orchestratore di pre-onboarding."""
    p = argparse.ArgumentParser(description="Pre-onboarding Timmy-KB")
    p.add_argument("slug_pos", nargs="?", help="Slug cliente (posizionale)")
    p.add_argument("--slug", type=str, help="Slug cliente (es. acme-srl)")
    p.add_argument("--name", type=str, help="Nome cliente (es. ACME Srl)")
    p.add_argument("--non-interactive", action="store_true", help="Esecuzione senza prompt")
    p.add_argument(
        "--dry-run",
        action="store_true",
        help=("Esegue la parte locale, no Google Drive (nessuna variabile d'ambiente)."),
    )
    return p.parse_args()


def main(args: argparse.Namespace) -> None:
    """Entrypoint CLI orchestrato via `run_cli_orchestrator`."""
    run_id = uuid.uuid4().hex
    bootstrap_logger = logging.getLogger("pre_onboarding")

    unresolved_slug = args.slug_pos or args.slug
    resolved_slug: Optional[str] = None

    def _error_extra(err_value: list[str], slug_value: Optional[str] = None) -> Dict[str, Any]:
        slug_ref = slug_value if slug_value is not None else (resolved_slug or unresolved_slug)
        mode = "non-interactive" if args.non_interactive else "interactive"
        return {"slug": slug_ref, "mode": mode, "dry_run": bool(args.dry_run), "err": err_value, "run_id": run_id}

    if not unresolved_slug and args.non_interactive:
        bootstrap_logger.error(
            "cli.pre_onboarding.exit.config_error",
            extra=_error_extra(["Missing slug in non-interactive mode"], slug_value=None),
        )
        raise ConfigError("Missing slug in non-interactive mode")

    slug = ensure_valid_slug(
        unresolved_slug,
        interactive=not args.non_interactive,
        prompt=_prompt,
        logger=None,
    )
    resolved_slug = slug

    # Bootstrap solo dopo parse+slug valido (no side-effects su --help)
    ensure_strict_runtime(context="cli.pre_onboarding", require_workspace_root=True)
    start_metrics_server_once()
    early_logger = get_structured_logger("pre_onboarding", run_id=run_id)

    env = get_env_var("TIMMY_ENV", default="dev")
    with start_root_trace(
        "onboarding",
        slug=slug,
        run_id=run_id,
        entry_point="cli",
        env=env,
        trace_kind="onboarding",
    ):
        try:
            pre_onboarding_main(
                slug=slug,
                client_name=args.name,
                interactive=not args.non_interactive,
                dry_run=args.dry_run,
                run_id=run_id,
            )
        except KeyboardInterrupt:
            raise
        except ConfigError as exc:
            early_logger.error(
                "cli.pre_onboarding.exit.config_error", extra=_error_extra(str(exc).splitlines()[:1], slug)
            )
            raise
        except PipelineError as exc:
            early_logger.error(
                "cli.pre_onboarding.exit.pipeline_error",
                extra=_error_extra(str(exc).splitlines()[:1], slug),
            )
            raise
        except Exception as exc:  # noqa: BLE001
            early_logger.error(
                "cli.pre_onboarding.exit.unhandled",
                extra=_error_extra(str(exc).splitlines()[:1], slug),
            )
            raise


if __name__ == "__main__":
    run_cli_orchestrator("pre_onboarding", _parse_args, main)
