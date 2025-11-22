#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
# src/pre_onboarding.py
"""
Orchestratore della fase di pre-onboarding per Timmy-KB.

ResponsabilitÃ :
- Preparare il contesto locale del cliente (`output/timmy-kb-<slug>/...`).
- Validare/minimizzare la configurazione e generare/aggiornare `config.yaml`.
- Creare struttura locale e la struttura remota su Google Drive.
- Caricare `config.yaml` su Drive e aggiornare il config locale con gli ID remoti.
- Copiare i template semantici di base nella cartella `semantic/` cliente.

Note architetturali:
- Gli orchestratori gestiscono I/O utente e terminazione del processo
  (mappano eccezioni con `exit_code_for`). I moduli non chiamano `sys.exit()` o `input()`.
- Redazione centralizzata via `logging_utils`.
- Path-safety STRONG: `ensure_within()` prima di ogni write/copy/delete.
- Non stampare segreti nei log (mascheratura parziale per ID e percorsi).
"""

# Fase pre-Vision (MINIMAL): nessun uso di YAML.
# 1) LOCALE: crea raw/, book/, config/ e scrive config/config.yaml
# 2) DRIVE: crea cartella cliente + raw/ + contrattualistica/ e carica config.yaml

from __future__ import annotations

import argparse
import datetime as _dt
import logging
import shutil
import sys
import uuid
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from pipeline.config_utils import (
    get_client_config,
    merge_client_config_from_template,
    update_config_with_drive_ids,
    write_client_config_file,
)
from pipeline.constants import LOG_FILE_NAME, LOGS_DIR_NAME
from pipeline.context import ClientContext
from pipeline.env_utils import get_env_var
from pipeline.exceptions import ConfigError, PipelineError, exit_code_for
from pipeline.file_utils import safe_write_bytes, safe_write_text  # SSoT scritture atomiche
from pipeline.logging_utils import (
    get_structured_logger,
    mask_id_map,
    mask_partial,
    mask_updates,
    phase_scope,
    tail_path,
)
from pipeline.observability_config import load_observability_settings
from pipeline.path_utils import ensure_valid_slug, ensure_within  # STRONG guard SSoT

create_drive_folder = None
create_drive_minimal_structure = None
get_drive_service = None
upload_config_to_drive_folder = None
try:
    import pipeline.drive_utils as _du

    create_drive_folder = _du.create_drive_folder
    create_drive_minimal_structure = getattr(_du, "create_drive_minimal_structure", None)
    get_drive_service = _du.get_drive_service
    upload_config_to_drive_folder = _du.upload_config_to_drive_folder
except Exception:
    # Import opzionale: in modalitÃ  --dry-run non Ã¨ richiesto googleapiclient
    pass


def _prompt(msg: str) -> str:
    """Raccoglie input da CLI (abilitato solo negli orchestratori)."""
    return input(msg).strip()


def _require_drive_utils() -> None:
    """Verifica che le utilitÃ  Google Drive siano disponibili e callabili.

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
        raise ConfigError(msg)


def _resolve_yaml_structure_file() -> Path:
    """Risolve in modo robusto il percorso dello YAML della struttura cartelle."""
    here = Path(__file__).resolve()
    repo_root = here.parents[1]

    env_path = get_env_var("YAML_STRUCTURE_FILE", required=False)
    if env_path:
        p = Path(env_path).expanduser().resolve()
        try:
            ensure_within(repo_root, p)
        except ConfigError:
            raise ConfigError(
                f"YAML_STRUCTURE_FILE punta fuori dal repository: {p}",
                file_path=str(p),
            )
        if p.is_file():
            return p

    candidates = [
        repo_root / "config" / "cartelle_raw.yaml",
        repo_root / "src" / "config" / "cartelle_raw.yaml",
    ]
    for p in candidates:
        if p.is_file():
            return p

    raise ConfigError(
        "File YAML per struttura cartelle non trovato in nessuno dei percorsi noti. "
        "Imposta YAML_STRUCTURE_FILE oppure aggiungi config/cartelle_raw.yaml.",
        file_path="; ".join(str(c) for c in candidates),
    )


def _sync_env(context: ClientContext, *, require_env: bool) -> None:
    """Allinea nel `context.env` le variabili critiche lette da os.environ."""
    for key in ("SERVICE_ACCOUNT_FILE", "DRIVE_ID"):
        if not context.env.get(key):
            val = get_env_var(key, required=require_env)
            if val:
                context.env[key] = val


def bootstrap_semantic_templates(
    repo_root: Path, context: ClientContext, client_name: str, logger: logging.Logger
) -> None:
    """
    Copia i template semantici globali nella cartella cliente:
    - cartelle_raw.yaml -> semantic/cartelle_raw.yaml
    - default_semantic_mapping.yaml -> semantic/tags_reviewed.yaml (+ blocco context)

    Nota: duplica automaticamente anche semantic/semantic_mapping.yaml per compatibilita UI.
    """
    if context.base_dir is None:
        raise PipelineError("Contesto incompleto: base_dir mancante", slug=context.slug)
    semantic_dir = context.base_dir / "semantic"
    semantic_dir.mkdir(parents=True, exist_ok=True)

    cfg_dir = repo_root / "config"
    struct_src = _resolve_yaml_structure_file()
    mapping_src = cfg_dir / "default_semantic_mapping.yaml"

    struct_dst = semantic_dir / "cartelle_raw.yaml"
    mapping_dst = semantic_dir / "tags_reviewed.yaml"  # nuovo nome allineato alla UI

    ensure_within(semantic_dir, struct_dst)
    ensure_within(semantic_dir, mapping_dst)

    if not struct_dst.exists() and struct_src.exists():
        shutil.copy2(struct_src, struct_dst)
        logger.info(
            "cli.pre_onboarding.semantic_template_copied",
            extra={"slug": context.slug, "file_path": str(struct_dst)},
        )

    if not mapping_dst.exists() and mapping_src.exists():
        shutil.copy2(mapping_src, mapping_dst)
        logger.info(
            "cli.pre_onboarding.semantic_template_copied",
            extra={"slug": context.slug, "file_path": str(mapping_dst)},
        )

    # Iniezione blocco `context` nel mapping (scrittura atomica)
    try:
        import yaml

        data: Dict[str, Any] = {}
        if mapping_dst.exists():
            try:
                from pipeline.yaml_utils import yaml_read

                loaded = yaml_read(mapping_dst.parent, mapping_dst) or {}
                if isinstance(loaded, dict):
                    data = loaded
            except Exception:
                data = {}

        ctx = {
            "slug": context.slug,
            "client_name": client_name or context.slug,
            "created_at": _dt.datetime.utcnow().strftime("%Y-%m-%d"),
        }

        # Prepend `context` solo se non giÃ  presente
        if "context" not in data:
            data = {"context": ctx, **data}
            payload = yaml.safe_dump(data, allow_unicode=True, sort_keys=False)
            ensure_within(semantic_dir, mapping_dst)
            safe_write_text(mapping_dst, payload, atomic=True)
            logger.info(
                "cli.pre_onboarding.semantic_mapping_context_injected",
                extra={"slug": context.slug, "file_path": str(mapping_dst)},
            )

        # (Opzionale) retro-compatibilitÃ : mantieni anche semantic_mapping.yaml
        legacy = semantic_dir / "semantic_mapping.yaml"
        if not legacy.exists():
            try:
                shutil.copy2(mapping_dst, legacy)
                logger.info(
                    "cli.pre_onboarding.semantic_mapping_legacy_copied",
                    extra={"slug": context.slug, "file_path": str(legacy)},
                )
            except Exception:
                pass

    except Exception as e:  # non blocca il flusso
        logger.warning(
            "cli.pre_onboarding.semantic_mapping_context_inject_failed",
            extra={"slug": context.slug, "err": str(e).splitlines()[:1]},
        )


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
    obs_settings = load_observability_settings()
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
        slug=slug, interactive=interactive, require_env=require_env, run_id=run_id
    )

    if context.base_dir is None:
        raise PipelineError("Contesto incompleto: base_dir mancante", slug=context.slug)
    log_file = context.base_dir / LOGS_DIR_NAME / LOG_FILE_NAME
    ensure_within(context.base_dir, log_file)
    log_file.parent.mkdir(parents=True, exist_ok=True)

    logger = get_structured_logger(
        "pre_onboarding",
        log_file=log_file,
        context=context,
        run_id=run_id,
        **obs_kwargs,
    )
    if not require_env:
        logger.info("cli.pre_onboarding.offline_mode", extra={"slug": context.slug})
    logger.info("cli.pre_onboarding.config_loaded", extra={"slug": context.slug, "path": str(context.config_path)})
    logger.info("cli.pre_onboarding.started", extra={"slug": context.slug})
    return context, logger, client_name


def _create_local_structure(context: ClientContext, logger: logging.Logger, *, client_name: str) -> Path:
    """Crea raw/, book/, config/ e scrive config.yaml minimale. Restituisce il path di config."""
    if context.base_dir is None or context.config_path is None:
        raise PipelineError(
            "Contesto incompleto: base_dir/config_path mancanti",
            slug=context.slug,
        )
    ensure_within(context.base_dir, context.config_path)

    cfg_path = context.config_path

    cfg: Dict[str, Any] = {}
    try:
        cfg = get_client_config(context) or {}
    except ConfigError:
        cfg = {}
    if client_name:
        cfg["client_name"] = client_name

    # Default coerenti con la nuova UI
    rel_semantic_dir = Path(f"timmy-kb-{context.slug}/semantic")
    cfg.setdefault("cartelle_raw_yaml", str(rel_semantic_dir / "cartelle_raw.yaml"))
    cfg.setdefault("semantic_mapping_yaml", str(rel_semantic_dir / "tags_reviewed.yaml"))

    write_client_config_file(context, cfg)

    repo_root = Path(__file__).resolve().parents[1]
    bootstrap_semantic_templates(repo_root, context, client_name, logger)

    if context.base_dir is None or context.raw_dir is None or context.md_dir is None:
        raise PipelineError(
            "Contesto incompleto: base_dir/raw_dir/md_dir mancanti",
            slug=context.slug,
        )
    ensure_within(context.base_dir, context.raw_dir)
    ensure_within(context.base_dir, context.md_dir)
    ensure_within(context.base_dir, cfg_path.parent)

    with phase_scope(logger, stage="create_local_structure", customer=context.slug) as m:
        context.base_dir.mkdir(parents=True, exist_ok=True)
        context.raw_dir.mkdir(parents=True, exist_ok=True)
        context.md_dir.mkdir(parents=True, exist_ok=True)
        cfg_dir = cfg_path.parent
        cfg_dir.mkdir(parents=True, exist_ok=True)
        # telemetria: numero directory top-level nella base cliente
        try:
            base = context.base_dir
            count = sum(1 for p in (base.iterdir() if base else []) if p.is_dir())
            m.set_artifacts(count)
        except Exception:
            m.set_artifacts(None)

    logger.info(
        "cli.pre_onboarding.local_skeleton.created",
        extra={
            "raw": str(context.raw_dir),
            "book": str(context.md_dir),
            "config": str(cfg_path.parent),
        },
    )

    return cfg_path


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
          * `vision_statement_pdf: 'config/VisionStatement.pdf'`
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

    # Salva VisionStatement.pdf se fornito
    if vision_statement_pdf:
        if context.base_dir is None:
            raise PipelineError("Contesto incompleto: base_dir mancante", slug=context.slug)
        cfg_dir = context.base_dir / "config"
        target = cfg_dir / "VisionStatement.pdf"
        cfg_dir.mkdir(parents=True, exist_ok=True)
        ensure_within(context.base_dir, target)
        safe_write_bytes(target, vision_statement_pdf, atomic=True)
        logger.info({"event": "vision_statement_saved", "slug": context.slug, "file_path": str(target)})

        # Aggiorna config con percorso PDF e nome cliente
        updates: Dict[str, Any] = {"vision_statement_pdf": "config/VisionStatement.pdf"}
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
    except Exception as e:
        # Non blocca il flusso UI: finiamo comunque con un warning visibile in Diagnostica
        logger.warning(
            "cli.pre_onboarding.config_merge_failed",
            extra={"slug": context.slug, "err": str(e).splitlines()[:1]},
        )

    logger.info(
        {
            "event": "new_client_workspace_created",
            "slug": context.slug,
            "base": str(context.base_dir) if context.base_dir else None,
            "config": str(config_path),
        }
    )
    return config_path


def _drive_phase(
    context: ClientContext,
    logger: logging.Logger,
    *,
    config_path: Path,
    client_name: str,
    require_env: bool,
) -> None:
    """Crea struttura remota minima su Drive, carica config e aggiorna il config locale."""
    _sync_env(context, require_env=require_env)
    logger.info(
        "pre_onboarding.drive.preflight",
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

    drive_raw_folder_id = created_map.get("raw")
    if not drive_raw_folder_id:
        raise ConfigError(
            f"Cartella RAW non trovata su Drive per slug '{context.slug}'.",
            drive_id=client_folder_id,
            slug=context.slug,
        )
    drive_contrattualistica_folder_id = created_map.get("contrattualistica")
    if not drive_contrattualistica_folder_id:
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
        "drive_folder_id": client_folder_id,
        "drive_raw_folder_id": drive_raw_folder_id,
        "drive_contrattualistica_folder_id": drive_contrattualistica_folder_id,
        "drive_config_folder_id": client_folder_id,
        "client_name": client_name,
    }
    update_config_with_drive_ids(context, updates=updates, logger=logger)
    logger.info(
        "cli.pre_onboarding.config_updated_with_drive_ids",
        extra={"slug": context.slug, "updates_masked": mask_updates(updates)},
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
    require_env = not dry_run

    context, logger, client_name = _prepare_context_and_logger(
        slug,
        interactive=interactive,
        require_env=require_env,
        run_id=run_id,
        client_name=client_name,
    )

    current_stage = "local_structure"
    try:
        config_path = _create_local_structure(context, logger, client_name=client_name)

        if dry_run:
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
        logger.info("cli.pre_onboarding.completed", extra={"slug": context.slug, "artifacts": 1})
    except Exception as exc:
        logger.exception(
            "cli.pre_onboarding.failed",
            extra={
                "slug": context.slug,
                "stage": current_stage,
                "error": str(exc).splitlines()[:1],
            },
        )
        raise


# ------------------------------------ CLI ENTRYPOINT ------------------------------------


def _parse_args() -> argparse.ArgumentParser:
    """Costruisce e restituisce il parser CLI per l'orchestratore di pre-onboarding.

    Opzioni:
        slug_pos: Argomento posizionale per lo slug cliente.
        --slug: Slug cliente (alternativa al posizionale).
        --name: Nome cliente (es. ACME Srl).
        --non-interactive: Esecuzione senza prompt.
        --dry-run: Esegue solo la parte locale e salta Google Drive.

    Restituisce:
        argparse.ArgumentParser: parser configurato (non ancora parsed).
    """
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
    return p


if __name__ == "__main__":
    args = _parse_args().parse_args()
    run_id = uuid.uuid4().hex
    early_logger = get_structured_logger("pre_onboarding", run_id=run_id)

    def _error_extra(err_value: list[str], slug_value: Optional[str] = None) -> Dict[str, Any]:
        slug_ref = slug_value if slug_value is not None else (unresolved_slug or None)
        mode = "non-interactive" if args.non_interactive else "interactive"
        return {"slug": slug_ref, "mode": mode, "dry_run": bool(args.dry_run), "err": err_value, "run_id": run_id}

    unresolved_slug = args.slug_pos or args.slug
    if not unresolved_slug and args.non_interactive:
        early_logger.error(
            "cli.pre_onboarding.exit.config_error",
            extra=_error_extra(["Missing slug in non-interactive mode"], locals().get("slug")),
        )
        sys.exit(exit_code_for(ConfigError("Missing slug in non-interactive mode")))
    try:
        slug = ensure_valid_slug(
            unresolved_slug,
            interactive=not args.non_interactive,
            prompt=_prompt,
            logger=early_logger,
        )
    except ConfigError as exc:
        sys.exit(exit_code_for(exc))

    try:
        pre_onboarding_main(
            slug=slug,
            client_name=args.name,
            interactive=not args.non_interactive,
            dry_run=args.dry_run,
            run_id=run_id,
        )
        sys.exit(0)
    except KeyboardInterrupt:
        sys.exit(130)
    except ConfigError as exc:
        early_logger.error(
            "cli.pre_onboarding.exit.config_error",
            extra=_error_extra(str(exc).splitlines()[:1], slug),
        )
        sys.exit(exit_code_for(exc))
    except PipelineError as exc:
        early_logger.error(
            "cli.pre_onboarding.exit.pipeline_error",
            extra=_error_extra(str(exc).splitlines()[:1], slug),
        )
        sys.exit(exit_code_for(exc))
    except Exception as exc:  # noqa: BLE001 - hardening finale
        early_logger.error(
            "cli.pre_onboarding.exit.unhandled",
            extra=_error_extra(str(exc).splitlines()[:1], slug),
        )
        sys.exit(exit_code_for(PipelineError(str(exc))))
