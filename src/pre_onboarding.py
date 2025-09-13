#!/usr/bin/env python3
# src/pre_onboarding.py
"""
Orchestratore della fase di **pre-onboarding** per Timmy-KB.

ResponsabilitÃ :
- Preparare il contesto locale del cliente (`output/timmy-kb-<slug>/...`).
- Validare/minimizzare la configurazione e generare/aggiornare `config.yaml`.
- Creare struttura locale e la struttura remota su Google Drive.
- Caricare `config.yaml` su Drive e aggiornare il config locale con gli ID remoti.
- Copiare i template semantici di base nella cartella `semantic/` cliente.

Note architetturali:
- Gli orchestratori gestiscono **I/O utente (prompt)** e **terminazione del processo**
  (mappando eccezioni â†’ `EXIT_CODES`). I moduli invocati **non** chiamano `sys.exit()` o `input()`.
- **Redazione centralizzata** via `logging_utils`.
- **Path-safety STRONG**: `ensure_within()` prima di ogni write/copy/delete.
- Non stampa segreti nei log (usa mascheratura parziale per ID e percorsi).
"""
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
    update_config_with_drive_ids,
    write_client_config_file,
)
from pipeline.constants import LOG_FILE_NAME, LOGS_DIR_NAME
from pipeline.context import ClientContext
from pipeline.drive_utils import (
    create_drive_folder,
    create_drive_structure_from_yaml,
    create_local_base_structure,
    get_drive_service,
    upload_config_to_drive_folder,
)
from pipeline.env_utils import get_env_var
from pipeline.exceptions import EXIT_CODES, ConfigError, PipelineError
from pipeline.file_utils import safe_write_bytes, safe_write_text  # SSoT per scritture atomiche
from pipeline.logging_utils import (
    get_structured_logger,
    mask_id_map,
    mask_partial,
    mask_updates,
    metrics_scope,
    tail_path,
)
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


def bootstrap_semantic_templates(
    repo_root: Path, context: ClientContext, client_name: str, logger: logging.Logger
) -> None:
    """
    Copia i template semantici globali nella cartella cliente:
    - cartelle_raw.yaml -> semantic/cartelle_raw.yaml
    - default_semantic_mapping.yaml -> semantic/tags_reviewed.yaml (+ blocco context)

    Nota: se vuoi retro-compatibilitÃ , puoi duplicare anche in semantic/semantic_mapping.yaml.
    """
    if context.base_dir is None:
        raise PipelineError("Contesto incompleto: base_dir mancante", slug=context.slug)
    semantic_dir = context.base_dir / "semantic"
    semantic_dir.mkdir(parents=True, exist_ok=True)

    cfg_dir = repo_root / "config"
    struct_src = _resolve_yaml_structure_file()
    mapping_src = cfg_dir / "default_semantic_mapping.yaml"

    struct_dst = semantic_dir / "cartelle_raw.yaml"
    mapping_dst = semantic_dir / "tags_reviewed.yaml"  # <- nuovo nome allineato alla UI

    ensure_within(semantic_dir, struct_dst)
    ensure_within(semantic_dir, mapping_dst)

    if not struct_dst.exists() and struct_src.exists():
        shutil.copy2(struct_src, struct_dst)
        logger.info({"event": "semantic_template_copied", "file": str(struct_dst)})

    if not mapping_dst.exists() and mapping_src.exists():
        shutil.copy2(mapping_src, mapping_dst)
        logger.info({"event": "semantic_template_copied", "file": str(mapping_dst)})

    # Iniezione blocco `context` nel mapping (atomico)
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
            logger.info({"event": "semantic_mapping_context_injected", "file": str(mapping_dst)})

        # (Opzionale) retro-compatibilitÃ : mantieni anche semantic_mapping.yaml
        legacy = semantic_dir / "semantic_mapping.yaml"
        if not legacy.exists():
            try:
                shutil.copy2(mapping_dst, legacy)
                logger.info({"event": "semantic_mapping_legacy_copied", "file": str(legacy)})
            except Exception:
                pass

    except Exception as e:  # non blocca il flusso
        logger.warning(
            {"event": "semantic_mapping_context_inject_failed", "err": str(e).splitlines()[:1]}
        )


# ------- FUNZIONI ESTRATTE: piccole, testabili, senza side-effects esterni oltre I/O necessario -------


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
    early_logger = get_structured_logger("pre_onboarding", run_id=run_id)
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
        "pre_onboarding", log_file=log_file, context=context, run_id=run_id
    )
    if not require_env:
        logger.info(
            "ModalitÃ  offline: variabili d'ambiente esterne non richieste (require_env=False)."
        )
    logger.info(f"Config cliente caricata: {context.config_path}")
    logger.info("Avvio pre-onboarding")
    return context, logger, client_name


def _create_local_structure(
    context: ClientContext, logger: logging.Logger, *, client_name: str
) -> Path:
    """Crea struttura locale, scrive config, copia template semantici; restituisce il path allo YAML struttura."""
    if context.base_dir is None or context.config_path is None:
        raise PipelineError(
            "Contesto incompleto: base_dir/config_path mancanti",
            slug=context.slug,
        )
    ensure_within(context.base_dir, context.config_path)

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

    yaml_structure_file = _resolve_yaml_structure_file()
    logger.info(
        "pre_onboarding.yaml.resolved",
        extra={
            "yaml_path": str(yaml_structure_file),
            "yaml_path_tail": tail_path(yaml_structure_file),
        },
    )

    if context.base_dir is None or context.raw_dir is None or context.md_dir is None:
        raise PipelineError(
            "Contesto incompleto: base_dir/raw_dir/md_dir mancanti",
            slug=context.slug,
        )
    ensure_within(context.base_dir, context.raw_dir)
    ensure_within(context.base_dir, context.md_dir)
    with metrics_scope(logger, stage="create_local_structure", customer=context.slug):
        create_local_base_structure(context, yaml_structure_file)

    repo_root = Path(__file__).resolve().parents[1]
    bootstrap_semantic_templates(repo_root, context, client_name, logger)
    return yaml_structure_file


# ---- Entry point minimale per la UI (landing solo slug) ----------------------


def ensure_local_workspace_for_ui(
    slug: str,
    client_name: Optional[str] = None,
    vision_statement_pdf: Optional[bytes] = None,
) -> Path:
    """Garantisce la presenza del workspace locale del cliente per la UI.

    Comportamento:
      - Prepara contesto offline (interactive=False, require_env=False) e logger.
      - RIUSA la creazione struttura locale e config tramite `_create_local_structure`.
      - Se `vision_statement_pdf` è fornito, lo salva in `config/VisionStatement.pdf` (atomico) e
        aggiorna `config.yaml` con:
          * `vision_statement_pdf: 'config/VisionStatement.pdf'`
          * `client_name: <client_name>` (se fornito)
      - Ritorna il path allo YAML struttura usato per la creazione locale.

    Note:
      - Nessuna interazione con Google Drive/GitHub.
      - Path-safety e scritture atomiche applicate (ensure_within, safe_write_bytes).
    """
    # Prepara contesto/log in modalità offline e valida lo slug
    context, logger, resolved_name = _prepare_context_and_logger(
        slug,
        interactive=False,
        require_env=False,
        run_id=None,
        client_name=client_name,
    )

    # Crea struttura locale e config di base (idempotente)
    yaml_structure_file = _create_local_structure(
        context, logger, client_name=(resolved_name or slug)
    )

    # Salva VisionStatement.pdf se fornito
    if vision_statement_pdf:
        if context.base_dir is None:
            raise PipelineError("Contesto incompleto: base_dir mancante", slug=context.slug)
        cfg_dir = context.base_dir / "config"
        target = cfg_dir / "VisionStatement.pdf"
        cfg_dir.mkdir(parents=True, exist_ok=True)
        ensure_within(context.base_dir, target)
        # Scrittura atomica del PDF
        safe_write_bytes(target, vision_statement_pdf, atomic=True)
        logger.info(
            {"event": "vision_statement_saved", "slug": context.slug, "file_path": str(target)}
        )

        # Aggiorna config con percorso PDF e nome cliente
        updates: Dict[str, Any] = {"vision_statement_pdf": "config/VisionStatement.pdf"}
        if resolved_name:
            updates["client_name"] = resolved_name
        update_config_with_drive_ids(context, updates, logger=logger)

        # Genera YAML strutturato del Vision Statement (placeholder parser)
        try:
            from semantic.vision_parser import pdf_to_vision_yaml  # type: ignore

            out_yaml = cfg_dir / "vision_statement.yaml"
            ensure_within(context.base_dir, out_yaml)
            pdf_to_vision_yaml(target, out_yaml)
            logger.info(
                {
                    "event": "vision_yaml_generated",
                    "slug": context.slug,
                    "file_path": str(out_yaml),
                }
            )
        except Exception as e:
            logger.warning(
                {
                    "event": "vision_yaml_generation_failed",
                    "slug": context.slug,
                    "error": str(e).splitlines()[:1],
                }
            )

    logger.info(
        {
            "event": "new_client_workspace_created",
            "slug": context.slug,
            "base": str(context.base_dir) if context.base_dir else None,
            "yaml": str(yaml_structure_file),
        }
    )
    return yaml_structure_file


def _drive_phase(
    context: ClientContext,
    logger: logging.Logger,
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
        client_folder_id = create_drive_folder(
            service, context.slug, parent_id=drive_parent_id, redact_logs=redact
        )
    logger.info(
        "ðŸ“„ Cartella cliente creata su Drive",
        extra={"client_folder_id": mask_partial(client_folder_id)},
    )

    with metrics_scope(logger, stage="drive_create_structure", customer=context.slug):
        created_map = create_drive_structure_from_yaml(
            service, yaml_structure_file, client_folder_id, redact_logs=redact
        )
    logger.info(
        "ðŸ“„ Struttura Drive creata",
        extra={
            "yaml_tail": tail_path(yaml_structure_file),
            "created_map_masked": mask_id_map(created_map),
        },
    )

    drive_raw_folder_id = created_map.get("raw")
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
    logger.info(
        "ðŸ“¤ Config caricato su Drive", extra={"uploaded_cfg_id": mask_partial(uploaded_cfg_id)}
    )

    updates = {
        "drive_folder_id": client_folder_id,
        "drive_raw_folder_id": drive_raw_folder_id,
        "drive_config_folder_id": client_folder_id,
        "client_name": client_name,
    }
    update_config_with_drive_ids(context, updates=updates, logger=logger)
    logger.info("ðŸ”‘ Config aggiornato con dati", extra={"updates_masked": mask_updates(updates)})


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
    # FIX: l'ambiente Ã¨ richiesto ogni volta che NON Ã¨ dry-run (indipendentemente dall'interattivitÃ )
    require_env = not dry_run

    context, logger, client_name = _prepare_context_and_logger(
        slug,
        interactive=interactive,
        require_env=require_env,
        run_id=run_id,
        client_name=client_name,
    )

    yaml_structure_file = _create_local_structure(context, logger, client_name=client_name)

    if dry_run:
        logger.info("ModalitÃ  dry-run: salto operazioni su Google Drive.")
        logger.info("Pre-onboarding locale completato (dry-run).")
        return

    _drive_phase(
        context,
        logger,
        yaml_structure_file=yaml_structure_file,
        client_name=client_name,
        require_env=require_env,
    )
    logger.info(f"âœ… Pre-onboarding completato per cliente: {context.slug}")


# ------------------------------------ CLI ENTRYPOINT ------------------------------------


def _parse_args() -> argparse.ArgumentParser:
    """Costruisce e restituisce il parser CLI per lâ€™orchestratore di pre-onboarding.

    Opzioni:
        slug_pos: Argomento posizionale per lo slug cliente.
        --slug: Slug cliente (alternativa al posizionale).
        --name: Nome cliente (es. â€œACME Srlâ€).
        --non-interactive: Esecuzione senza prompt.
        --dry-run: Esegue solo la parte locale e salta Google Drive.

    Restituisce:
        argparse.ArgumentParser: parser configurato (non ancora â€œparsedâ€).
    """
    p = argparse.ArgumentParser(description="Pre-onboarding Timmy-KB")
    p.add_argument("slug_pos", nargs="?", help="Slug cliente (posizionale)")
    p.add_argument("--slug", type=str, help="Slug cliente (es. acme-srl)")
    p.add_argument("--name", type=str, help="Nome cliente (es. ACME Srl)")
    p.add_argument("--non-interactive", action="store_true", help="Esecuzione senza prompt")
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Esegue solo la parte locale e salta Google Drive (nessuna variabile d'ambiente richiesta).",
    )
    return p


if __name__ == "__main__":
    args = _parse_args().parse_args()
    run_id = uuid.uuid4().hex
    early_logger = get_structured_logger("pre_onboarding", run_id=run_id)

    unresolved_slug = args.slug_pos or args.slug
    if not unresolved_slug and args.non_interactive:
        early_logger.error(
            "Errore: in modalitÃ  non interattiva Ã¨ richiesto --slug (o slug posizionale)."
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
    except Exception as e:  # noqa: BLE001 - hardening finale
        early_logger.error(f"Uscita per errore non gestito: {e}")
        sys.exit(EXIT_CODES.get("PipelineError", 1))
