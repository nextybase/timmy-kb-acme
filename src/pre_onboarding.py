#!/usr/bin/env python3
# src/pre_onboarding.py
"""
Orchestratore della fase di **pre-onboarding** per Timmy-KB.
[omissis: docstring invariata]
"""
from __future__ import annotations

import argparse
import sys
import uuid
from pathlib import Path
from typing import Optional, Dict, Any

from pipeline.logging_utils import (
    get_structured_logger,
    mask_partial,
    tail_path,
    mask_id_map,
    mask_updates,
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
from pipeline.env_utils import get_env_var, compute_redact_flag
from pipeline.constants import LOGS_DIR_NAME, LOG_FILE_NAME
from pipeline.path_utils import ensure_valid_slug, is_safe_subpath
from pipeline.file_utils import ensure_within  # ← guardia STRONG per override path


def _prompt(msg: str) -> str:
    """Raccoglie input da CLI (abilitato **solo** negli orchestratori)."""
    return input(msg).strip()


def _resolve_yaml_structure_file() -> Path:
    """
    Risolve in modo robusto il percorso dello YAML della struttura cartelle.

    Ordine di ricerca:
      1) Env `YAML_STRUCTURE_FILE` (se definita) — DEVE stare dentro il repo.
      2) `<repo_root>/config/cartelle_raw.yaml`
      3) `<repo_root>/src/config/cartelle_raw.yaml`
    """
    here = Path(__file__).resolve()
    repo_root = here.parents[1]  # …/<repo>

    # 1) Override via env (centralizzato; non redigiamo il path in clear nei log qui)
    env_path = get_env_var("YAML_STRUCTURE_FILE", required=False, redact=False)
    if env_path:
        p = Path(env_path).expanduser().resolve()
        # ✅ Path-safety forte: l'override DEVE vivere dentro al repo
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


def pre_onboarding_main(
    slug: str,
    client_name: Optional[str] = None,
    *,
    interactive: bool = True,
    dry_run: bool = False,
    run_id: Optional[str] = None,
) -> None:
    """
    Esegue la fase di pre-onboarding per il cliente indicato.
    """
    # === Logger console “early” (prima dei path cliente) ===
    early_logger = get_structured_logger("pre_onboarding", run_id=run_id)

    # ✅ Validazione slug PRIMA di costruire i path/log di cliente (helper centralizzato)
    slug = ensure_valid_slug(
        slug,
        interactive=interactive,
        prompt=_prompt,
        logger=early_logger,
    )

    # Validazioni base input (senza cambiare UX)
    if client_name is None and interactive:
        client_name = _prompt("Inserisci nome cliente: ").strip()
    if not client_name:
        client_name = slug  # fallback innocuo

    # === Caricamento/creazione contesto cliente ===
    require_env = not (dry_run or (not interactive))
    context: ClientContext = ClientContext.load(
        slug=slug,
        interactive=interactive,
        require_env=require_env,
        run_id=run_id,
    )

    # ✅ PR-2: Single source of truth per log path (derivato dal contesto)
    log_file = context.repo_root_dir / LOGS_DIR_NAME / LOG_FILE_NAME
    log_file.parent.mkdir(parents=True, exist_ok=True)

    # ✅ PR-2: Propagazione uniforme del flag di redazione (guardia difensiva)
    if not hasattr(context, "redact_logs"):
        context.redact_logs = compute_redact_flag(context.env, getattr(context, "log_level", "INFO"))

    # 🔁 Rebind logger con il contesto
    logger = get_structured_logger("pre_onboarding", log_file=log_file, context=context, run_id=run_id)

    if not require_env:
        logger.info("🌐 Modalità offline: variabili d'ambiente esterne non richieste (require_env=False).")
    logger.info(f"Config cliente caricata: {context.config_path}")
    logger.info("🚀 Avvio pre-onboarding")

    # === Config iniziale: assicurati che esista un file config.yaml coerente ===
    cfg: Dict[str, Any] = {}
    try:
        cfg = get_client_config(context) or {}
    except ConfigError:
        cfg = {}
    if client_name:
        cfg["client_name"] = client_name
    write_client_config_file(context, cfg)  # crea/aggiorna con backup .bak

    # === Risoluzione YAML + Struttura locale convenzionale ===
    try:
        yaml_structure_file = _resolve_yaml_structure_file()
        logger.info(
            "pre_onboarding.yaml.resolved",
            extra={"yaml_path": str(yaml_structure_file), "yaml_path_tail": tail_path(yaml_structure_file)},
        )
        create_local_base_structure(context, yaml_structure_file)
    except ConfigError as e:
        logger.error("❌ Impossibile creare la struttura locale: " + str(e))
        raise

    if dry_run:
        logger.info("🧪 Modalità dry-run: salto operazioni su Google Drive.")
        logger.info("✅ Pre-onboarding locale completato (dry-run).")
        return

    # === Allineamento env: integra chiavi critiche in context.env (conservativo) ===
    for key in ("SERVICE_ACCOUNT_FILE", "DRIVE_ID"):
        if not context.env.get(key):
            val = get_env_var(key, required=require_env, redact=True)
            if val:
                context.env[key] = val

    # Preflight (log non sensibili, mascherati)
    logger.info(
        "pre_onboarding.drive.preflight",
        extra={
            "SERVICE_ACCOUNT_FILE": mask_partial(context.env.get("SERVICE_ACCOUNT_FILE")),
            "DRIVE_ID": mask_partial(context.env.get("DRIVE_ID")),
        },
    )

    # === Inizializza client Google Drive (Service Account) ===
    service = get_drive_service(context)

    # Determina parent della cartella cliente (Shared Drive o cartella specifica)
    drive_parent_id = context.env.get("DRIVE_ID")
    if not drive_parent_id:
        raise ConfigError("DRIVE_ID non impostato nell'ambiente (.env).")

    # Toggle redazione: usa la fonte di verità del contesto
    redact = bool(getattr(context, "redact_logs", False))

    logger.info("pre_onboarding.drive.start", extra={"parent": mask_partial(drive_parent_id)})

    # === Crea cartella cliente sul Drive condiviso (idempotente) ===
    client_folder_id = create_drive_folder(
        service, context.slug, parent_id=drive_parent_id, redact_logs=redact
    )
    logger.info("📄 Cartella cliente creata su Drive", extra={"client_folder_id": mask_partial(client_folder_id)})

    # === Crea struttura remota da YAML (idempotente) ===
    created_map = create_drive_structure_from_yaml(
        service, yaml_structure_file, client_folder_id, redact_logs=redact
    )
    logger.info(
        "📄 Struttura Drive creata",
        extra={
            "yaml_tail": tail_path(yaml_structure_file),
            "created_map_masked": mask_id_map(created_map),
        },
    )

    # Individua RAW (accetta alias RAW/raw dal mapping ritornato)
    drive_raw_folder_id = created_map.get("RAW") or created_map.get("raw")
    if not drive_raw_folder_id:
        raise ConfigError(
            f"Cartella RAW non trovata su Drive per slug '{context.slug}'. "
            f"Verifica lo YAML di struttura: {yaml_structure_file}",
            drive_id=client_folder_id,
            slug=context.slug,
            file_path=str(yaml_structure_file),
        )

    # === Carica config.yaml su Drive (sostituisce se esiste) ===
    uploaded_cfg_id = upload_config_to_drive_folder(
        service, context, parent_id=client_folder_id, redact_logs=redact
    )
    logger.info("📤 Config caricato su Drive", extra={"uploaded_cfg_id": mask_partial(uploaded_cfg_id)})

    # === Aggiorna config locale con gli ID Drive ===
    updates = {
        "drive_folder_id": client_folder_id,
        "drive_raw_folder_id": drive_raw_folder_id,
        "drive_config_folder_id": client_folder_id,
        "client_name": client_name,
    }
    update_config_with_drive_ids(context, updates=updates, logger=logger)
    logger.info("🔑 Config aggiornato con dati", extra={"updates_masked": mask_updates(updates)})

    logger.info(f"✅ Pre-onboarding completato per cliente: {slug}")


def _parse_args() -> argparse.ArgumentParser:
    """Parsa gli argomenti CLI dell’orchestratore di pre-onboarding."""
    p = argparse.ArgumentParser(description="Pre-onboarding NeXT KB")
    p.add_argument("slug_pos", nargs="?", help="Slug cliente (posizionale)")
    p.add_argument("--slug", type=str, help="Slug cliente (es. acme-srl)")
    p.add_argument("--name", type=str, help="Nome cliente (es. ACME Srl)")
    p.add_argument("--non-interactive", action="store_true", help="Esecuzione senza prompt")
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Esegue solo la parte locale, salta Google Drive",
    )
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
