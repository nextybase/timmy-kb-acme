#!/usr/bin/env python3
# src/pre_onboarding.py
"""
Orchestratore della fase di **pre-onboarding** per Timmy-KB.

Responsabilità:
- Preparare il contesto locale del cliente (`output/timmy-kb-<slug>/...`).
- Validare/minimizzare la configurazione e generare/aggiornare `config.yaml`.
- Creare struttura locale e, se non in `--dry-run`, la struttura remota su Google Drive.
- Caricare `config.yaml` su Drive e aggiornare il config locale con gli ID remoti.
- Copiare i template semantici di base nella cartella `semantic/` cliente.

Note architetturali:
- Gli orchestratori gestiscono **I/O utente (prompt)** e **terminazione del processo**
  (mappando eccezioni → `EXIT_CODES`). I moduli invocati **non** chiamano `sys.exit()` o `input()`.
- **Redazione centralizzata** via `logging_utils` (nessun masking in env).
- **Path-safety STRONG**: `ensure_within()` prima di ogni write/copy/delete.
- Non stampa segreti nei log (usa mascheratura parziale per ID e percorsi).
"""
from __future__ import annotations

import argparse
import sys
import uuid
import shutil
import datetime as _dt
from pathlib import Path
from typing import Optional, Dict, Any, Tuple

from pipeline.logging_utils import (
    get_structured_logger,
    mask_partial,
    tail_path,
    mask_id_map,
    mask_updates,
    metrics_scope,
)
from pipeline.exceptions import PipelineError, ConfigError, EXIT_CODES
from pipeline.context import ClientContext
from pipeline.config_utils import (
    get_client_config,
    write_client_config_file,
    update_config_with_drive_ids,
)
from pipeline.drive_utils import (
    get_drive_service,
    create_drive_folder,
    create_drive_structure_from_yaml,
    upload_config_to_drive_folder,
    create_local_base_structure,
)
from pipeline.env_utils import get_env_var
from pipeline.constants import LOGS_DIR_NAME, LOG_FILE_NAME
from pipeline.path_utils import ensure_valid_slug, ensure_within  # STRONG guard SSoT


def _prompt(msg: str) -> str:
    """Raccoglie input da CLI (abilitato **solo** negli orchestratori)."""
    return input(msg).strip()


def _resolve_yaml_structure_file() -> Path:
    """
    Risolve in modo robusto il percorso dello YAML della struttura cartelle.
    """
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


def bootstrap_semantic_templates(repo_root: Path, context: ClientContext, client_name: str, logger) -> None:
    """
    Copia i template semantici globali nella cartella cliente:
    - cartelle_raw.yaml -> semantic/cartelle_raw.yaml
    - default_semantic_mapping.yaml -> semantic/semantic_mapping.yaml (+ blocco context)
    """
    semantic_dir = context.base_dir / "semantic"
    semantic_dir.mkdir(parents=True, exist_ok=True)

    cfg_dir = repo_root / "config"
    struct_src = _resolve_yaml_structure_file()
    mapping_src = cfg_dir / "default_semantic_mapping.yaml"

    struct_dst = semantic_dir / "cartelle_raw.yaml"
    mapping_dst = semantic_dir / "semantic_mapping.yaml"

    ensure_within(semantic_dir, struct_dst)
    ensure_within(semantic_dir, mapping_dst)

    if not struct_dst.exists() and struct_src.exists():
        shutil.copy2(struct_src, struct_dst)
        logger.info({"event": "semantic_template_copied", "file": str(struct_dst)})

    if not mapping_dst.exists() and mapping_src.exists():
        shutil.copy2(mapping_src, mapping_dst)
        logger.info({"event": "semantic_template_copied", "file": str(mapping_dst)})
        try:
            import yaml
            with mapping_dst.open("r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            ctx = {
                "slug": context.slug,
                "client_name": client_name or context.slug,
                "created_at": _dt.datetime.utcnow().strftime("%Y-%m-%d"),
            }
            if "context" not in data and isinstance(data, dict):
                data = {"context": ctx, **data}
                with mapping_dst.open("w", encoding="utf-8") as f:
                    yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)
                logger.info({"event": "semantic_mapping_context_injected", "file": str(mapping_dst)})
        except Exception as e:
            logger.warning({"event": "semantic_mapping_context_inject_failed", "err": str(e).splitlines()[:1]})


# ------- FUNZIONI ESTRATTE: piccole, testabili, senza side-effects esterni oltre I/O necessario -------

def _prepare_context_and_logger(
    slug: str,
    *,
    interactive: bool,
    require_env: bool,
    run_id: Optional[str],
    client_name: Optional[str],
) -> Tuple[ClientContext, Any, str]:
    early_logger = get_structured_logger("pre_onboarding", run_id=run_id)
    slug = ensure_valid_slug(slug, interactive=interactive, prompt=_prompt, logger=early_logger)

    if client_name is None and interactive:
        client_name = _prompt("Inserisci nome cliente: ").strip()
    if not client_name:
        client_name = slug

    context: ClientContext = ClientContext.load(
        slug=slug, interactive=interactive, require_env=require_env, run_id=run_id
    )

    log_file = context.base_dir / LOGS_DIR_NAME / LOG_FILE_NAME
    ensure_within(context.base_dir, log_file)
    log_file.parent.mkdir(parents=True, exist_ok=True)

    logger = get_structured_logger("pre_onboarding", log_file=log_file, context=context, run_id=run_id)
    if not require_env:
        logger.info("🌐 Modalità offline: variabili d'ambiente esterne non richieste (require_env=False).")
    logger.info(f"Config cliente caricata: {context.config_path}")
    logger.info("🚀 Avvio pre-onboarding")
    return context, logger, client_name


def _create_local_structure(context: ClientContext, logger, *, client_name: str) -> Path:
    """Crea struttura locale, scrive config, copia template semantici; restituisce il path allo YAML struttura."""
    ensure_within(context.base_dir, context.config_path)

    cfg: Dict[str, Any] = {}
    try:
        cfg = get_client_config(context) or {}
    except ConfigError:
        cfg = {}
    if client_name:
        cfg["client_name"] = client_name
    write_client_config_file(context, cfg)

    yaml_structure_file = _resolve_yaml_structure_file()
    logger.info(
        "pre_onboarding.yaml.resolved",
        extra={"yaml_path": str(yaml_structure_file), "yaml_path_tail": tail_path(yaml_structure_file)},
    )

    ensure_within(context.base_dir, context.raw_dir)
    ensure_within(context.base_dir, context.md_dir)
    with metrics_scope(logger, stage="create_local_structure", customer=context.slug):
        create_local_base_structure(context, yaml_structure_file)

    repo_root = Path(__file__).resolve().parents[1]
    bootstrap_semantic_templates(repo_root, context, client_name, logger)
    return yaml_structure_file


def _drive_phase(
    context: ClientContext,
    logger,
    *,
    yaml_structure_file: Path,
    client_name: str,
    require_env: bool,
) -> None:
    """Crea struttura remota su Drive, carica config, aggiorna config locale con ID remoti."""
    _sync_env(context, require_env=require_env)
    logger.info(
        "pre_onboarding.drive.preflight",
        extra={
            "SERVICE_ACCOUNT_FILE": mask_partial(context.env.get("SERVICE_ACCOUNT_FILE")),
            "DRIVE_ID": mask_partial(context.env.get("DRIVE_ID")),
        },
    )
    service = get_drive_service(context)

    drive_parent_id = context.env.get("DRIVE_ID")
    if not drive_parent_id:
        raise ConfigError("DRIVE_ID non impostato nell'ambiente (.env).")

    redact = bool(getattr(context, "redact_logs", False))
    logger.info("pre_onboarding.drive.start", extra={"parent": mask_partial(drive_parent_id)})

    with metrics_scope(logger, stage="drive_create_client_folder", customer=context.slug):
        client_folder_id = create_drive_folder(service, context.slug, parent_id=drive_parent_id, redact_logs=redact)
    logger.info("📄 Cartella cliente creata su Drive", extra={"client_folder_id": mask_partial(client_folder_id)})

    with metrics_scope(logger, stage="drive_create_structure", customer=context.slug):
        created_map = create_drive_structure_from_yaml(
            service, yaml_structure_file, client_folder_id, redact_logs=redact
        )
    logger.info(
        "📄 Struttura Drive creata",
        extra={"yaml_tail": tail_path(yaml_structure_file), "created_map_masked": mask_id_map(created_map)},
    )

    drive_raw_folder_id = created_map.get("RAW") or created_map.get("raw")
    if not drive_raw_folder_id:
        raise ConfigError(
            f"Cartella RAW non trovata su Drive per slug '{context.slug}'. "
            f"Verifica lo YAML di struttura: {yaml_structure_file}",
            drive_id=client_folder_id,
            slug=context.slug,
            file_path=str(yaml_structure_file),
        )

    with metrics_scope(logger, stage="drive_upload_config", customer=context.slug):
        uploaded_cfg_id = upload_config_to_drive_folder(
            service, context, parent_id=client_folder_id, redact_logs=redact
        )
    logger.info("📤 Config caricato su Drive", extra={"uploaded_cfg_id": mask_partial(uploaded_cfg_id)})

    updates = {
        "drive_folder_id": client_folder_id,
        "drive_raw_folder_id": drive_raw_folder_id,
        "drive_config_folder_id": client_folder_id,
        "client_name": client_name,
    }
    update_config_with_drive_ids(context, updates=updates, logger=logger)
    logger.info("🔑 Config aggiornato con dati", extra={"updates_masked": mask_updates(updates)})


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
    require_env = not (dry_run or (not interactive))
    context, logger, client_name = _prepare_context_and_logger(
        slug, interactive=interactive, require_env=require_env, run_id=run_id, client_name=client_name
    )

    yaml_structure_file = _create_local_structure(context, logger, client_name=client_name)

    if dry_run:
        logger.info("🧪 Modalità dry-run: salto operazioni su Google Drive.")
        logger.info("✅ Pre-onboarding locale completato (dry-run).")
        return

    _drive_phase(
        context,
        logger,
        yaml_structure_file=yaml_structure_file,
        client_name=client_name,
        require_env=require_env,
    )
    logger.info(f"✅ Pre-onboarding completato per cliente: {context.slug}")


# ------------------------------------ CLI ENTRYPOINT ------------------------------------

def _parse_args() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Pre-onboarding NeXT KB")
    p.add_argument("slug_pos", nargs="?", help="Slug cliente (posizionale)")
    p.add_argument("--slug", type=str, help="Slug cliente (es. acme-srl)")
    p.add_argument("--name", type=str, help="Nome cliente (es. ACME Srl)")
    p.add_argument("--non-interactive", action="store_true", help="Esecuzione senza prompt")
    p.add_argument("--dry-run", action="store_true", help="Esegue solo la parte locale, salta Google Drive")
    return p


if __name__ == "__main__":
    args = _parse_args().parse_args()
    run_id = uuid.uuid4().hex
    early_logger = get_structured_logger("pre_onboarding", run_id=run_id)

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
