"""
utils.py

Utility di validazione e supporto per la pipeline Timmy-KB.
Include funzioni per validazione slug e per la verifica preventiva dell’ambiente di pre-onboarding,
con controllo file di configurazione, chiavi obbligatorie e directory critiche.
"""

import sys
import logging
from pathlib import Path
import yaml
import re
from pipeline.exceptions import PreOnboardingValidationError
from pipeline.config_utils import settings  # Config centralizzata

def is_valid_slug(slug: str = None) -> bool:
    """
    Verifica che lo slug sia conforme a [a-z0-9-], senza caratteri non ammessi o path traversali.
    Normalizza lo slug sostituendo underscore con trattini e convertendo in lowercase.
    Regex configurabile da settings (es. settings.SLUG_PATTERN).

    Args:
        slug (str): Stringa da validare. Default: settings.slug

    Returns:
        bool: True se valido, False altrimenti.
    """
    if slug is None:
        slug = settings.slug

    if not slug:
        return False

    # Normalizzazione
    normalized_slug = slug.replace("_", "-").lower()

    # Pattern regex da settings se disponibile, altrimenti default
    pattern = getattr(settings, "SLUG_PATTERN", r"[a-z0-9-]+")
    if not re.fullmatch(pattern, normalized_slug):
        logging.getLogger("slug.validation").debug(
            f"Slug '{slug}' normalizzato in '{normalized_slug}' non conforme al pattern: {pattern}"
        )
        return False
    return True


def validate_preonboarding_environment():
    """
    Step 1: Verifica presenza, leggibilità e conformità di config/config.yaml.
    Step 2: Se tutto ok, verifica l'esistenza degli altri file e directory critici.
    In caso di errore, logga un report dettagliato e solleva eccezione custom.

    Raises:
        PreOnboardingValidationError: Se mancano file, chiavi obbligatorie o directory critiche.
    """
    logger = logging.getLogger("preonboarding.validation")

    # --- STEP 1: Validazione config principale ---
    config_path = Path("config/config.yaml").resolve()
    required_base_keys = [
        "cartelle_raw_yaml",  # Deve contenere questa chiave
        # Aggiungi altre chiavi obbligatorie qui se servono
    ]

    if not config_path.exists():
        logger.error(f"❌ File di configurazione non trovato: {config_path}")
        raise PreOnboardingValidationError(f"File di configurazione non trovato: {config_path}")

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
    except Exception as e:
        logger.error(f"❌ Errore di lettura/parsing YAML in {config_path}: {e}")
        raise PreOnboardingValidationError(f"Errore di lettura/parsing YAML in {config_path}: {e}")

    missing_keys = [k for k in required_base_keys if k not in config]
    if missing_keys:
        logger.error(f"❌ Chiavi obbligatorie mancanti in {config_path}: {missing_keys}")
        raise PreOnboardingValidationError(f"Chiavi obbligatorie mancanti: {missing_keys}")

    logger.info(f"✅ {config_path} esistente, leggibile e conforme.")

    # --- STEP 2: Validazione file e directory aggiuntive ---
    required_files = [
        config["cartelle_raw_yaml"],  # Ricavato dinamicamente dal config
    ]
    required_dirs = [
        "logs",
    ]

    # Verifica file richiesti
    missing_files = [str(Path(f).resolve()) for f in required_files if not Path(f).exists()]
    if missing_files:
        logger.error(f"❌ File richiesti mancanti: {missing_files}")
        raise PreOnboardingValidationError(f"File richiesti mancanti: {missing_files}")

    # Verifica directory richieste
    for d in required_dirs:
        dir_path = Path(d).resolve()
        if not dir_path.exists():
            logger.warning(f"📂 Directory mancante: {dir_path}, creazione automatica...")
            dir_path.mkdir(parents=True, exist_ok=True)

    logger.info("✅ Tutti i file e directory richiesti sono presenti.")

# Questo modulo viene usato in più punti della pipeline:
# - is_valid_slug: validazione CLI e orchestratori
# - validate_preonboarding_environment: check iniziale in pre_onboarding.py
