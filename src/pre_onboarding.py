#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Optional, Dict, Any

from pipeline.logging_utils import get_structured_logger
from pipeline.exceptions import PipelineError, ConfigError
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

YAML_STRUCTURE_FILE = Path(__file__).resolve().parents[1] / "config" / "cartelle_raw.yaml"


def _prompt(msg: str) -> str:
    # prompt consentito solo qui (orchestratore)
    return input(msg).strip()


def pre_onboarding_main(
    slug: str,
    client_name: Optional[str] = None,
    *,
    interactive: bool = True,
    dry_run: bool = False,
) -> None:
    """
    Prepara contesto cliente locale + struttura su Drive (se non dry_run):
      - struttura locale: output/timmy-kb-<slug>/{raw,book,config}
      - struttura Drive da YAML
      - upload config.yaml su Drive
      - aggiornamento config locale con ID Drive
    """
    # === Logger unificato: file unico per cliente ===
    log_file = Path("output") / f"timmy-kb-{slug}" / "logs" / "onboarding.log"
    log_file.parent.mkdir(parents=True, exist_ok=True)
    logger = get_structured_logger("pre_onboarding", log_file=log_file)

    try:
        # === Validazione minima input ===
        if not slug:
            raise ConfigError("Slug mancante.")
        if client_name is None and interactive:
            client_name = _prompt("Inserisci nome cliente: ").strip()
        if not client_name:
            client_name = slug  # fallback innocuo

        # === Caricamento/creazione contesto cliente ===
        context: ClientContext = ClientContext.load(slug=slug, interactive=interactive)
        logger.info(f"Config cliente caricata: {context.config_path}")

        logger.info("🚀 Avvio pre-onboarding")

        # === Config iniziale: assicurati che esista un file config.yaml coerente ===
        cfg: Dict[str, Any] = get_client_config(context) or {}
        if client_name:
            cfg["client_name"] = client_name
        write_client_config_file(context, cfg)  # crea/aggiorna con backup .bak

        # === Struttura locale convenzionale ===
        if not YAML_STRUCTURE_FILE.exists():
            raise ConfigError(
                f"File YAML per struttura cartelle non trovato: {YAML_STRUCTURE_FILE}",
                file_path=YAML_STRUCTURE_FILE,
            )
        create_local_base_structure(context, YAML_STRUCTURE_FILE)

        if dry_run:
            logger.info("🧪 Modalità dry-run: salto operazioni su Google Drive.")
            logger.info("✅ Pre-onboarding locale completato (dry-run).")
            return

        # === Inizializza client Google Drive (Service Account) ===
        service = get_drive_service(context)

        # Determina parent della cartella cliente (Shared Drive o cartella specifica)
        drive_parent_id = context.env.get("DRIVE_PARENT_FOLDER_ID") or context.env.get("DRIVE_ID")
        if not drive_parent_id:
            raise ConfigError("DRIVE_ID o DRIVE_PARENT_FOLDER_ID non impostati nell'ambiente (.env).")

        # === Crea cartella cliente sul Drive condiviso ===
        client_folder_id = create_drive_folder(service, context.slug, parent_id=drive_parent_id)
        logger.info(f"📄 Cartella cliente creata su Drive: {client_folder_id}")

        # === Crea struttura remota da YAML ===
        created_map = create_drive_structure_from_yaml(service, YAML_STRUCTURE_FILE, client_folder_id)
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
        uploaded_cfg_id = upload_config_to_drive_folder(service, context, parent_id=client_folder_id)
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

    except (PipelineError, ConfigError) as e:
        logger.error(f"⚠️ Errore pre-onboarding: {e}", exc_info=True)
        raise
    except KeyboardInterrupt:
        logger.warning("Operazione annullata dall'utente.")
        raise
    except Exception as e:
        logger.error(f"🔥 Errore imprevisto: {e}", exc_info=True)
        raise


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Pre-onboarding NeXT KB")
    p.add_argument("--slug", type=str, help="Slug cliente (es. acme-srl)")
    p.add_argument("--name", type=str, help="Nome cliente (es. ACME Srl)")
    p.add_argument("--non-interactive", action="store_true", help="Esecuzione senza prompt")
    p.add_argument("--dry-run", action="store_true", help="Esegue solo la parte locale, salta Google Drive")
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    slug = args.slug or _prompt("Inserisci slug cliente: ").strip()
    pre_onboarding_main(
        slug=slug,
        client_name=args.name,
        interactive=not args.non_interactive,
        dry_run=args.dry_run,
    )
