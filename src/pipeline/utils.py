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
from pipeline.exceptions import PreOnboardingValidationError  # ✅ Import dalla posizione corretta
from pipeline.config_utils import settings  # <--- Importa config centralizzata

def is_valid_slug(slug: str = None) -> bool:
    """
    Verifica che lo slug sia conforme a [a-z0-9-], senza caratteri strani o path traversali.
    Utile per validare identificativi di clienti, repo, cartelle output, ecc.

    Args:
        slug (str): Stringa da validare. Default: settings.slug

    Returns:
        bool: True se valido, False altrimenti.
    """
    if slug is None:
        slug = settings.slug
    if not slug:
        return False
    return re.fullmatch(r"[a-z0-9-]+", slug) is not None

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
    config_path = Path("config/config.yaml")
    required_base_keys = [
        "cartelle_raw_yaml",  # deve contenere questa chiave
        # aggiungi altre chiavi obbligatorie qui se servono
    ]
    if not config_path.exists():
        logger.error(f"❌ File di configurazione non trovato: {config_path}")
        raise PreOnboardingValidationError(f"File di configurazione non trovato: {config_path}")
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
    except Exception as e:
        logger.error(f"❌ Errore di lettura/parsing YAML in {config_path}: {e}")
        raise PreOnboardingValidationError(f"Errore di lettura/parsing YAML: {e}")
    missing_keys = [k for k in required_base_keys if k not in config]
    if missing_keys:
        logger.error(f"❌ Chiavi obbligatorie mancanti in {config_path}: {missing_keys}")
        raise PreOnboardingValidationError(f"Chiavi obbligatorie mancanti: {missing_keys}")
    logger.info("✅ config.yaml esistente, leggibile e conforme.")

    # --- STEP 2: Validazione file e directory aggiuntivi ---
    required_files = [
        config["cartelle_raw_yaml"],  # Ricavato dinamicamente dal config
    ]
    required_dirs = [
        "logs",
    ]
    # Verifica file richiesti (escluso config.yaml già validato)
    missing = [f for f in required_files if not Path(f).exists()]
    if missing:
        logger.error(f"❌ File richiesti mancanti: {missing}")
        raise PreOnboardingValidationError(f"File richiesti mancanti: {missing}")
    # Verifica directory richieste
    for d in required_dirs:
        Path(d).mkdir(parents=True, exist_ok=True)
    logger.info("✅ Tutti i file e directory richiesti sono presenti.")

# Puoi ora chiamare validate_preonboarding_environment() in pre_onboarding.py
# Ricorda di gestire la PreOnboardingValidationError nell'orchestratore!
