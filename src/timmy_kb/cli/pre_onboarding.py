#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
# src/pre_onboarding.py
"""
Orchestratore della fase di pre-onboarding per Timmy-KB.

Responsabilità:
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
import logging
import uuid
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from pipeline.artifact_policy import enforce_core_artifacts
from pipeline.cli_runner import run_cli_orchestrator
from pipeline.config_utils import (
    ensure_config_migrated,
    get_client_config,
    merge_client_config_from_template,
    update_config_with_drive_ids,
    write_client_config_file,
)
from pipeline.context import ClientContext
from pipeline.env_utils import ensure_dotenv_loaded, get_env_var
from pipeline.exceptions import ArtifactPolicyViolation, ConfigError, PipelineError
from pipeline.file_utils import safe_write_bytes, safe_write_text  # SSoT scritture atomiche
from pipeline.logging_utils import (
    get_structured_logger,
    mask_id_map,
    mask_partial,
    mask_updates,
    phase_scope,
    tail_path,
)
from pipeline.metrics import start_metrics_server_once
from pipeline.observability_config import get_observability_settings
from pipeline.path_utils import ensure_valid_slug, ensure_within, read_text_safe  # STRONG guard SSoT
from pipeline.runtime_guard import ensure_strict_runtime
from pipeline.tracing import start_root_trace
from pipeline.types import WorkflowResult
from pipeline.workspace_bootstrap import bootstrap_client_workspace as _pipeline_bootstrap_client_workspace
from pipeline.workspace_layout import WorkspaceLayout
from storage import decision_ledger

bootstrap_client_workspace = _pipeline_bootstrap_client_workspace

create_drive_folder = None
create_drive_minimal_structure = None
get_drive_service = None
upload_config_to_drive_folder = None
_drive_import_error: Optional[str] = None
try:
    import pipeline.drive_utils as _du

    create_drive_folder = _du.create_drive_folder
    create_drive_minimal_structure = getattr(_du, "create_drive_minimal_structure", None)
    get_drive_service = _du.get_drive_service
    upload_config_to_drive_folder = _du.upload_config_to_drive_folder
except ImportError as exc:
    # Import opzionale: in modalità --dry-run non è richiesto googleapiclient
    _drive_import_error = str(exc).splitlines()[0]


def _prompt(msg: str) -> str:
    """Raccoglie input da CLI (abilitato solo negli orchestratori)."""
    return input(msg).strip()


def _require_drive_utils() -> None:
    """Verifica che le utilità Google Drive siano disponibili e callabili.

    Solleva ConfigError con istruzioni d'installazione se mancanti.
    """
    missing: list[str] = []
    if not callable(get_drive_service):
        missing.append("get_drive_service")
    if not callable(create_drive_folder):
        missing.append("create_drive_folder")
    if not callable(create_drive_minimal_structure):
        missing.append("create_drive_minimal_structure")
    if not callable(upload_config_to_drive_folder):
        missing.append("upload_config_to_drive_folder")
    if missing:
        msg = (
            "Supporto Google Drive non disponibile: funzioni non presenti/callabili: "
            f"{', '.join(missing)}.\n"
            "Installa gli extra Drive e rileggi i docs:\n"
            "  pip install .[drive]\n"
            "Oppure disattiva il ramo Drive (usa --dry-run o source=local)."
        )
        if _drive_import_error:
            msg = f"{msg}\nDettagli import Drive: {_drive_import_error}"
        raise ConfigError(msg)


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
    require_env: bool,
    run_id: Optional[str],
    client_name: Optional[str],
) -> Tuple[ClientContext, logging.Logger, str]:
    """Prepara `ClientContext` e logger strutturato per il pre-onboarding.

    Args:
        slug: Identificatore del cliente (slug) da validare.
        interactive: Se True abilita i prompt CLI (es. richiesta `client_name`).
        require_env: Se True richiede variabili d'ambiente esterne (no dry-run).
        run_id: Correlazione opzionale per i log.
        client_name: Nome cliente; se assente e `interactive=True` viene richiesto via prompt.

    Returns:
        Tuple[ClientContext, logging.Logger, str]: contesto caricato, logger configurato,
        e `client_name` risolto (mai vuoto).
    """
    obs_settings = get_observability_settings()
    obs_kwargs = {
        "level": obs_settings.log_level,
        "redact_logs": obs_settings.redact_logs,
        "enable_tracing": obs_settings.tracing_enabled,
    }

    early_logger = get_structured_logger("pre_onboarding", run_id=run_id, **obs_kwargs)
    slug = ensure_valid_slug(slug, interactive=interactive, prompt=_prompt, logger=early_logger)

    if client_name is None and interactive:
        client_name = _prompt("Inserisci nome cliente: ").strip()
    if not client_name:
        client_name = slug

    context: ClientContext = ClientContext.load(
        slug=slug,
        require_env=require_env,
        run_id=run_id,
        bootstrap_config=True,
    )

    layout = WorkspaceLayout.from_context(context)
    layout.logs_dir.mkdir(parents=True, exist_ok=True)
    log_file = layout.log_file

    logger = get_structured_logger(
        "pre_onboarding",
        log_file=log_file,
        context=context,
        run_id=run_id,
        **obs_kwargs,
    )
    if not require_env:
        logger.info("cli.pre_onboarding.offline_mode", extra={"slug": context.slug})
    logger.info("cli.pre_onboarding.config_loaded", extra={"slug": context.slug, "path": str(layout.config_path)})
    logger.info("cli.pre_onboarding.started", extra={"slug": context.slug})
    return context, logger, client_name


def _utc_now_iso() -> str:
    return _dt.datetime.now(tz=_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _summarize_error(exc: BaseException) -> str:
    name = type(exc).__name__
    message = str(exc).splitlines()[:1]
    first_line = message[0] if message else "error"
    return f"{name}: {first_line}"


def _build_evidence_refs(layout: WorkspaceLayout) -> list[str]:
    return [
        f"path:{layout.config_path}",
        f"path:{layout.repo_root_dir}",
    ]


def _normative_verdict_for_error(exc: BaseException) -> tuple[str, str]:
    if isinstance(exc, ArtifactPolicyViolation):
        return decision_ledger.NORMATIVE_BLOCK, decision_ledger.STOP_CODE_ARTIFACT_POLICY_VIOLATION
    if isinstance(exc, ConfigError):
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


def _create_local_structure(context: ClientContext, logger: logging.Logger, *, client_name: str) -> Path:
    """Crea raw/, book/, config/ e scrive config.yaml minimale. Restituisce il path di config."""
    bootstrap_client_workspace(context)
    layout = WorkspaceLayout.from_context(context)
    cfg_path = layout.config_path
    repo_root_dir = layout.repo_root_dir

    cfg: Dict[str, Any] = {}
    try:
        cfg = get_client_config(context) or {}
    except ConfigError:
        cfg = {}
    if client_name:
        cfg["client_name"] = client_name

    write_client_config_file(context, cfg)

    ensure_within(repo_root_dir, layout.raw_dir)
    ensure_within(repo_root_dir, layout.book_dir)
    ensure_within(repo_root_dir, cfg_path.parent)

    cfg_dir = cfg_path.parent
    cfg_dir.mkdir(parents=True, exist_ok=True)

    with phase_scope(logger, stage="create_local_structure", customer=context.slug) as m:
        # telemetria: numero directory top-level nella base cliente
        try:
            base = repo_root_dir
            count = sum(1 for p in (base.iterdir() if base else []) if p.is_dir()) if base else None
            m.set_artifacts(count)
        except Exception:
            m.set_artifacts(None)

    logger.info(
        "cli.pre_onboarding.local_skeleton.created",
        extra={
            "raw": str(layout.raw_dir),
            "book": str(layout.book_dir),
            "config": str(cfg_path.parent),
        },
    )

    return cfg_path


def _merge_evidence_refs(base: list[str], exc: BaseException) -> list[str]:
    if isinstance(exc, ArtifactPolicyViolation):
        return [*base, *exc.evidence_refs]
    return base


# ---- Entry point minimale per la UI (landing solo slug) ----------------------


def ensure_local_workspace_for_ui(
    slug: str,
    client_name: Optional[str] = None,
    vision_statement_pdf: Optional[bytes] = None,
) -> Path:
    """Garantisce la presenza del workspace locale del cliente per la UI.

    Comportamento:
      - Prepara contesto offline (interactive=False, require_env=False) e logger.
      - Riusa la creazione struttura locale e config tramite `_create_local_structure`.
      - Se `vision_statement_pdf` è fornito, lo salva in `config/VisionStatement.pdf`
        (scrittura atomica) e aggiorna `config.yaml` con:
          * `ai.vision.vision_statement_pdf: 'config/VisionStatement.pdf'`
          * `client_name: <client_name>` (se fornito)
      - Ritorna il path al config.yaml locale.

    Note:
      - Nessuna interazione con Google Drive/GitHub.
      - Path-safety e scritture atomiche applicate (ensure_within, safe_write_bytes).
    """
    context, logger, resolved_name = _prepare_context_and_logger(
        slug,
        interactive=False,
        require_env=False,
        run_id=None,
        client_name=client_name,
    )

    # Crea struttura locale e config di base (idempotente)
    config_path = _create_local_structure(context, logger, client_name=(resolved_name or slug))
    layout = WorkspaceLayout.from_context(context)

    # Salva VisionStatement.pdf se fornito
    if vision_statement_pdf:
        repo_root_dir = layout.repo_root_dir
        cfg_dir = layout.config_path.parent
        target = layout.vision_pdf
        cfg_dir.mkdir(parents=True, exist_ok=True)
        ensure_within(repo_root_dir, target)
        safe_write_bytes(target, vision_statement_pdf, atomic=True)
        logger.info(
            "vision_statement_saved",
            extra={
                "slug": context.slug,
                "file_path": str(target),
                "context_repo_root_dir": str(repo_root_dir),
                "repo_root_dir": str(context.repo_root_dir or "<none>"),
            },
        )

        # Aggiorna config con percorso PDF e nome cliente
        updates: Dict[str, Any] = {"ai": {"vision": {"vision_statement_pdf": "config/VisionStatement.pdf"}}}
        if resolved_name:
            updates["client_name"] = resolved_name
        update_config_with_drive_ids(context, updates, logger=logger)

    # --- NOVITÀ: merge dal template di repository ---
    try:
        # Permette override nei test/ambienti: TEMPLATE_CONFIG_ROOT=/path/alla/repo
        template_root = get_env_var("TEMPLATE_CONFIG_ROOT", required=False)
        if template_root:
            template_cfg = Path(template_root).expanduser().resolve() / "config" / "config.yaml"
        else:
            repo_root = Path(__file__).resolve().parents[1]
            template_cfg = repo_root / "config" / "config.yaml"

        if template_cfg.exists():
            merge_client_config_from_template(context, template_cfg)
            logger.info(
                "cli.pre_onboarding.config_merged_from_template",
                extra={"slug": context.slug, "file_path": str(template_cfg)},
            )
    except ConfigError:
        raise
    except Exception as e:
        logger.warning(
            "cli.pre_onboarding.config_merge_failed",
            extra={"slug": context.slug, "err": str(e).splitlines()[:1]},
        )
        raise ConfigError(
            "Merge del template config.yaml fallito durante il bootstrap UI.",
            slug=context.slug,
            file_path=str(template_cfg) if "template_cfg" in locals() else None,
        ) from e

    # Copia il system prompt Vision nel workspace (serve per test/casi con REPO_ROOT_DIR override)
    try:
        repo_root = Path(__file__).resolve().parents[1]
        prompt_src = repo_root / "config" / "assistant_vision_system_prompt.txt"
        if prompt_src.exists():
            prompt_dest = layout.config_path.parent / "assistant_vision_system_prompt.txt"
            prompt_dest.parent.mkdir(parents=True, exist_ok=True)
            ensure_within(layout.repo_root_dir, prompt_dest)
            source_text = read_text_safe(prompt_src.parent, prompt_src, encoding="utf-8")
            safe_write_text(prompt_dest, source_text, encoding="utf-8", atomic=True)
    except Exception as exc:
        logger.warning(
            "cli.pre_onboarding.prompt_copy_failed",
            extra={"slug": context.slug, "error": str(exc)},
        )

    logger.info(
        "cli.pre_onboarding.workspace.created",
        extra={
            "slug": context.slug,
            "base": str(layout.repo_root_dir),
            "config": str(config_path),
        },
    )
    return config_path


def _drive_phase(
    context: ClientContext,
    logger: logging.Logger,
    *,
    config_path: Path,
    client_name: str,
    require_env: bool,
) -> WorkflowResult:
    """Crea struttura remota minima su Drive, carica config e aggiorna il config locale."""
    _sync_env(context, require_env=require_env)
    logger.info(
        "cli.pre_onboarding.drive.preflight",
        extra={
            "SERVICE_ACCOUNT_FILE": mask_partial(context.env.get("SERVICE_ACCOUNT_FILE")),
            "DRIVE_ID": mask_partial(context.env.get("DRIVE_ID")),
        },
    )
    from typing import Any, Callable, cast

    gds = cast(Callable[..., Any], get_drive_service)
    service = gds(context)

    drive_parent_id = context.env.get("DRIVE_ID")
    if not drive_parent_id:
        raise ConfigError("DRIVE_ID non impostato nell'ambiente (.env).")

    redact = bool(getattr(context, "redact_logs", False))
    logger.info(
        "cli.pre_onboarding.drive.start",
        extra={"slug": context.slug, "parent": mask_partial(drive_parent_id)},
    )

    with phase_scope(logger, stage="drive_create_client_folder", customer=context.slug) as m:
        cdf = cast(Callable[..., str], create_drive_folder)
        client_folder_id = cdf(service, context.slug, parent_id=drive_parent_id, redact_logs=redact)
        m.set_artifacts(1)
    logger.info(
        "cli.pre_onboarding.drive.folder_created",
        extra={"client_folder_id": mask_partial(client_folder_id)},
    )

    with phase_scope(logger, stage="drive_create_structure_minimal", customer=context.slug) as m:
        cdm = cast(Callable[..., Dict[str, str]], create_drive_minimal_structure)
        created_map = cdm(service, client_folder_id, redact_logs=redact)
        try:
            m.set_artifacts(len(created_map or {}))
        except Exception:
            m.set_artifacts(None)
    logger.info(
        "cli.pre_onboarding.drive.structure_created",
        extra={
            "config_tail": tail_path(config_path),
            "created_map_masked": mask_id_map(created_map),
        },
    )

    raw_folder_id = created_map.get("raw")
    if not raw_folder_id:
        raise ConfigError(
            f"Cartella RAW non trovata su Drive per slug '{context.slug}'.",
            drive_id=client_folder_id,
            slug=context.slug,
        )
    contrattualistica_folder_id = created_map.get("contrattualistica")
    if not contrattualistica_folder_id:
        raise ConfigError(
            f"Cartella contrattualistica non trovata su Drive per slug '{context.slug}'.",
            drive_id=client_folder_id,
            slug=context.slug,
        )

    with phase_scope(logger, stage="drive_upload_config", customer=context.slug) as m:
        ucf = cast(Callable[..., str], upload_config_to_drive_folder)
        uploaded_cfg_id = ucf(service, context, parent_id=client_folder_id, redact_logs=redact)
        m.set_artifacts(1)
    logger.info(
        "cli.pre_onboarding.drive_config_uploaded",
        extra={"slug": context.slug, "uploaded_cfg_id": mask_partial(uploaded_cfg_id)},
    )

    updates = {
        "integrations": {
            "drive": {
                "folder_id": client_folder_id,
                "raw_folder_id": raw_folder_id,
                "contrattualistica_folder_id": contrattualistica_folder_id,
                "config_folder_id": client_folder_id,
            }
        },
        "client_name": client_name,
    }
    update_config_with_drive_ids(context, updates=updates, logger=logger)
    logger.info(
        "cli.pre_onboarding.config_updated_with_drive_ids",
        extra={"slug": context.slug, "updates_masked": mask_updates(updates)},
    )
    return {
        "ok": True,
        "message": "cli.pre_onboarding.drive_phase_completed",
        "details": {"slug": context.slug, "stage": "drive_phase"},
    }


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
    require_env = not dry_run
    if require_env:
        ensure_dotenv_loaded(strict=True, allow_fallback=False)
    run_id = run_id or uuid.uuid4().hex

    context, logger, client_name = _prepare_context_and_logger(
        slug,
        interactive=interactive,
        require_env=require_env,
        run_id=run_id,
        client_name=client_name,
    )
    ensure_config_migrated(context, logger=logger)
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
    try:
        config_path = _create_local_structure(context, logger, client_name=client_name)

        if dry_run:
            enforce_core_artifacts("pre_onboarding", layout=layout)
            logger.info("cli.pre_onboarding.dry_run", extra={"slug": context.slug, "mode": "dry-run"})
            logger.info(
                "cli.pre_onboarding.completed",
                extra={
                    "slug": context.slug,
                    "mode": "dry-run",
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
                    evidence_refs=_build_evidence_refs(layout),
                    rationale="ok",
                ),
            )
            return

        current_stage = "drive_phase"
        # Verifica disponibilita funzioni Drive prima della fase remota
        _require_drive_utils()
        _drive_phase(
            context,
            logger,
            config_path=config_path,
            client_name=client_name,
            require_env=require_env,
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
                evidence_refs=_build_evidence_refs(layout),
                rationale="ok",
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
                    evidence_refs=_merge_evidence_refs(_build_evidence_refs(layout), exc),
                    stop_code=stop_code,
                    rationale=_deny_rationale(exc),
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
    ensure_strict_runtime(context="cli.pre_onboarding")
    run_id = uuid.uuid4().hex
    start_metrics_server_once()
    early_logger = get_structured_logger("pre_onboarding", run_id=run_id)

    unresolved_slug = args.slug_pos or args.slug
    resolved_slug: Optional[str] = None

    def _error_extra(err_value: list[str], slug_value: Optional[str] = None) -> Dict[str, Any]:
        slug_ref = slug_value if slug_value is not None else (resolved_slug or unresolved_slug)
        mode = "non-interactive" if args.non_interactive else "interactive"
        return {"slug": slug_ref, "mode": mode, "dry_run": bool(args.dry_run), "err": err_value, "run_id": run_id}

    if not unresolved_slug and args.non_interactive:
        early_logger.error(
            "cli.pre_onboarding.exit.config_error",
            extra=_error_extra(["Missing slug in non-interactive mode"], slug_value=None),
        )
        raise ConfigError("Missing slug in non-interactive mode")

    slug = ensure_valid_slug(
        unresolved_slug,
        interactive=not args.non_interactive,
        prompt=_prompt,
        logger=early_logger,
    )
    resolved_slug = slug

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
            raise PipelineError(str(exc)) from exc


if __name__ == "__main__":
    run_cli_orchestrator("pre_onboarding", _parse_args, main)
