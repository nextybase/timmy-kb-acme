#!/usr/bin/env python3
# src/pre_onboarding.py
"""
Orchestratore della fase di **pre-onboarding** per Timmy-KB.

Responsabilità:
- Preparare il contesto locale del cliente (`output/timmy-kb-<slug>/...`).
- Validare/minimizzare la configurazione e generare/aggiornare `config.yaml`.
- Creare struttura locale e, se non in `--dry-run`, la struttura remota su Google Drive.
- Caricare `config.yaml` su Drive e aggiornare il config locale con gli ID remoti.

Nota architetturale:
- Gli orchestratori gestiscono **I/O utente (prompt)** e **terminazione del processo**
  (mappando eccezioni → `EXIT_CODES`). I moduli invocati **non** devono chiamare
  `sys.exit()` o `input()`. Questo file rispetta tali regole.

Questo modulo **non** stampa segreti nei log (maschera ID e percorsi sensibili).
"""
from __future__ import annotations

import argparse
import sys
import uuid
from pathlib import Path
from typing import Optional, Dict, Any

from pipeline.logging_utils import get_structured_logger
from pipeline.exceptions import PipelineError, ConfigError, EXIT_CODES, InvalidSlug
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
from pipeline.env_utils import is_log_redaction_enabled, get_env_var
from pipeline.constants import OUTPUT_DIR_NAME, LOGS_DIR_NAME, LOG_FILE_NAME
from pipeline.path_utils import validate_slug as _validate_slug_helper


def _prompt(msg: str) -> str:
    """Raccoglie input da CLI (abilitato **solo** negli orchestratori)."""
    return input(msg).strip()


def _ensure_valid_slug(initial_slug: Optional[str], interactive: bool, early_logger) -> str:
    """Valida/ottiene uno slug valido prima di creare i path/log o caricare il contesto."""
    slug = (initial_slug or "").strip()
    while True:
        if not slug:
            if not interactive:
                raise ConfigError("Slug mancante.")
            slug = _prompt("Inserisci slug cliente: ").strip()
            continue
        try:
            _validate_slug_helper(slug)
            return slug
        except InvalidSlug:
            early_logger.error("Slug non valido secondo le regole configurate. Riprovare.")
            if not interactive:
                raise ConfigError(f"Slug '{slug}' non valido.")
            slug = _prompt("Inserisci uno slug valido (es. acme-srl): ").strip()


def _mask(s: Optional[str]) -> str:
    """Maschera parziale di ID/percorsi per log non sensibili."""
    if not s:
        return ""
    s = str(s)
    if len(s) <= 7:
        return "***"
    return f"{s[:3]}***{s[-3:]}"


def _resolve_yaml_structure_file() -> Path:
    """
    Risolve in modo robusto il percorso dello YAML della struttura cartelle.

    Ordine di ricerca:
      1) Env `YAML_STRUCTURE_FILE` (se definita).
      2) `<repo_root>/config/cartelle_raw.yaml`  (../config dal file corrente).
      3) `<repo_root>/src/config/cartelle_raw.yaml` (./src/config).

    Ritorna:
        Path esistente allo YAML.

    Solleva:
        ConfigError se nessun candidato esiste.
    """
    # 1) Override via env (centralizzato; non redigiamo il path in clear nei log qui)
    env_path = get_env_var("YAML_STRUCTURE_FILE", required=False, redact=False)
    if env_path:
        p = Path(env_path).expanduser().resolve()
        if p.is_file():
            return p

    here = Path(__file__).resolve()
    repo_root = here.parents[1]  # …/<repo>
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

    Operazioni:
        1) Carica/crea il contesto cliente e inizializza il **logger file-based**.
        2) Genera/aggiorna `config.yaml` (con fallback minimale).
        3) Crea la **struttura locale** da YAML canonico.
        4) Se `dry_run` è `False`:
           - Crea la cartella cliente su **Google Drive** (Shared Drive o parent specificato).
           - Crea la **struttura remota** da YAML.
           - Carica `config.yaml` su Drive e **aggiorna localmente** gli ID (`drive_*_id`) in `config.yaml`.
    """
    # === Logger console “early” (prima dei path cliente) ===
    early_logger = get_structured_logger("pre_onboarding", run_id=run_id)

    # ✅ Validazione slug PRIMA di costruire i path/log di cliente
    slug = _ensure_valid_slug(slug, interactive, early_logger)

    # === Logger unificato: file unico per cliente ===
    log_file = Path(OUTPUT_DIR_NAME) / f"timmy-kb-{slug}" / LOGS_DIR_NAME / LOG_FILE_NAME
    log_file.parent.mkdir(parents=True, exist_ok=True)
    logger = get_structured_logger("pre_onboarding", log_file=log_file, run_id=run_id)

    # Validazioni base input (senza cambiare UX)
    if client_name is None and interactive:
        client_name = _prompt("Inserisci nome cliente: ").strip()
    if not client_name:
        client_name = slug  # fallback innocuo

    # === Caricamento/creazione contesto cliente ===
    # require_env=False in dry-run o non-interactive per abilitare flussi offline
    require_env = not (dry_run or (not interactive))
    context: ClientContext = ClientContext.load(
        slug=slug,
        interactive=interactive,
        require_env=require_env,
        run_id=run_id,
    )

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
        logger.info("pre_onboarding.yaml.resolved", extra={"yaml_path": str(yaml_structure_file)})
        create_local_base_structure(context, yaml_structure_file)
    except ConfigError as e:
        # Log esplicito prima di uscire (per capire subito perché si ferma)
        logger.error("❌ Impossibile creare la struttura locale: " + str(e))
        raise

    if dry_run:
        logger.info("🧪 Modalità dry-run: salto operazioni su Google Drive.")
        logger.info("✅ Pre-onboarding locale completato (dry-run).")
        return

    # === Allineamento env: integra chiavi critiche in context.env (conservativo) ===
    for key in ("SERVICE_ACCOUNT_FILE", "DRIVE_PARENT_FOLDER_ID", "DRIVE_ID"):
        if not context.env.get(key):
            val = get_env_var(key, required=require_env, redact=True)
            if val:
                context.env[key] = val

    # Preflight (log non sensibili, mascherati)
    logger.info(
        "pre_onboarding.drive.preflight",
        extra={
            "SERVICE_ACCOUNT_FILE": _mask(context.env.get("SERVICE_ACCOUNT_FILE")),
            "DRIVE_PARENT_FOLDER_ID": _mask(context.env.get("DRIVE_PARENT_FOLDER_ID")),
            "DRIVE_ID": _mask(context.env.get("DRIVE_ID")),
        },
    )

    # === Inizializza client Google Drive (Service Account) ===
    service = get_drive_service(context)

    # Determina parent della cartella cliente (Shared Drive o cartella specifica)
    drive_parent_id = (
        context.env.get("DRIVE_PARENT_FOLDER_ID")
        or context.env.get("DRIVE_ID")
    )
    if not drive_parent_id:
        raise ConfigError("DRIVE_ID o DRIVE_PARENT_FOLDER_ID non impostati nell'ambiente (.env).")

    # Toggle redazione centralizzato
    redact = is_log_redaction_enabled(context)

    logger.info("pre_onboarding.drive.start", extra={"parent": _mask(drive_parent_id)})

    # === Crea cartella cliente sul Drive condiviso (idempotente) ===
    client_folder_id = create_drive_folder(
        service, context.slug, parent_id=drive_parent_id, redact_logs=redact
    )
    logger.info(f"📄 Cartella cliente creata su Drive: {client_folder_id}")

    # === Crea struttura remota da YAML (idempotente) ===
    created_map = create_drive_structure_from_yaml(
        service, _resolve_yaml_structure_file(), client_folder_id, redact_logs=redact
    )
    logger.info(f"📄 Struttura Drive creata: {created_map}")

    # Individua RAW (accetta alias RAW/raw dal mapping ritornato)
    drive_raw_folder_id = created_map.get("RAW") or created_map.get("raw")
    if not drive_raw_folder_id:
        raise ConfigError(
            "Cartella RAW non trovata su Drive: verifica YAML di struttura cartelle.",
            drive_id=client_folder_id,
            slug=context.slug,
        )

    # === Carica config.yaml su Drive (sostituisce se esiste) ===
    uploaded_cfg_id = upload_config_to_drive_folder(
        service, context, parent_id=client_folder_id, redact_logs=redact
    )
    logger.info(f"📤 Config caricato su Drive con ID: {uploaded_cfg_id}")

    # === Aggiorna config locale con gli ID Drive ===
    updates = {
        "drive_folder_id": client_folder_id,
        "drive_raw_folder_id": drive_raw_folder_id,
        "drive_config_folder_id": client_folder_id,
        "client_name": client_name,
    }
    update_config_with_drive_ids(context, updates=updates, logger=logger)
    logger.info(f"🔑 Config aggiornato con dati: {updates}")

    logger.info(f"✅ Pre-onboarding completato per cliente: {slug}")


def _parse_args() -> argparse.Namespace:
    """Parsa gli argomenti CLI dell’orchestratore di pre-onboarding."""
    p = argparse.ArgumentParser(description="Pre-onboarding NeXT KB")
    # slug “soft” posizionale (opzionale) + flag --slug
    p.add_argument("slug_pos", nargs="?", help="Slug cliente (posizionale)")
    p.add_argument("--slug", type=str, help="Slug cliente (es. acme-srl)")
    p.add_argument("--name", type=str, help="Nome cliente (es. ACME Srl)")
    p.add_argument("--non-interactive", action="store_true", help="Esecuzione senza prompt")
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Esegue solo la parte locale, salta Google Drive",
    )
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()

    # run_id univoco per correlazione log dell’esecuzione
    run_id = uuid.uuid4().hex

    # Logger console “early” (prima di avere lo slug) per messaggi iniziali
    early_logger = get_structured_logger("pre_onboarding", run_id=run_id)

    # Risoluzione slug: posizionale > --slug > prompt (validazione inclusa)
    unresolved_slug = args.slug_pos or args.slug
    if not unresolved_slug and args.non_interactive:
        early_logger.error("Errore: in modalità non interattiva è richiesto --slug (o slug posizionale).")
        sys.exit(EXIT_CODES.get("ConfigError", 2))
    try:
        slug = _ensure_valid_slug(unresolved_slug, not args.non_interactive, early_logger)
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
        # Log finale per avere sempre il motivo della chiusura
        early_logger.error("Uscita per ConfigError: " + str(e))
        sys.exit(EXIT_CODES.get("ConfigError", 2))
    except PipelineError as e:
        code = EXIT_CODES.get(e.__class__.__name__, EXIT_CODES.get("PipelineError", 1))
        early_logger.error(f"Uscita per PipelineError: {e}")
        sys.exit(code)
    except Exception as e:
        early_logger.error(f"Uscita per errore non gestito: {e}")
        sys.exit(EXIT_CODES.get("PipelineError", 1))
