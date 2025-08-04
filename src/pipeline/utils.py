import sys
from pathlib import Path
import yaml
import re

def is_valid_slug(slug: str) -> bool:
    """
    Verifica che lo slug sia conforme a [a-z0-9-], senza caratteri strani o path traversali.
    Utile per validare identificativi di clienti, repo, cartelle output, ecc.
    """
    if not slug:
        return False
    return re.fullmatch(r"[a-z0-9-]+", slug) is not None

def validate_preonboarding_environment():
    """
    Step 1: Verifica presenza, leggibilità e conformità di config/config.yaml.
    Step 2: Se tutto ok, verifica l'esistenza degli altri file e directory critici.
    In caso di errore, stampa un report dettagliato e interrompe il processo.
    """
    # --- STEP 1: Validazione config principale ---
    config_path = Path("config/config.yaml")
    required_base_keys = [
        "cartelle_raw_yaml",  # deve contenere questa chiave
        # aggiungi altre chiavi obbligatorie qui se servono
    ]
    if not config_path.exists():
        print(f"❌ File di configurazione non trovato: {config_path}")
        sys.exit(1)
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
    except Exception as e:
        print(f"❌ Errore di lettura/parsing YAML in {config_path}:\n{e}")
        sys.exit(1)
    missing_keys = [k for k in required_base_keys if k not in config]
    if missing_keys:
        print(f"❌ Chiavi obbligatorie mancanti in {config_path}: {missing_keys}")
        sys.exit(1)
    print("✅ config.yaml esistente, leggibile e conforme.")

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
        print(f"❌ File richiesti mancanti: {missing}")
        sys.exit(1)
    # Verifica directory richieste
    for d in required_dirs:
        Path(d).mkdir(parents=True, exist_ok=True)
    print("✅ Tutti i file e directory richiesti sono presenti.")

# Puoi ora chiamare validate_preonboarding_environment() in pre_onboarding.py
