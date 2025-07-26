import yaml
from pathlib import Path
from pipeline.logging_utils import get_structured_logger

logger = get_structured_logger("pipeline.config_utils")

def load_client_config(slug: str) -> dict:
    """
    Carica la configurazione del cliente dal file config.yaml situato in output/timmy-kb-{slug}/config/config.yaml
    Ritorna un dizionario con la config e imposta il campo 'slug'.
    """
    config_path = Path("output") / f"timmy-kb-{slug}" / "config" / "config.yaml"
    if not config_path.exists():
        logger.error(f"❌ Config file non trovato: {config_path}")
        raise FileNotFoundError(f"Config file non trovato: {config_path}")
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    config["slug"] = slug
    return config

def write_client_config_file(config: dict, slug: str) -> Path:
    """
    Scrive il file di configurazione arricchito del cliente nella posizione standard.
    Ritorna il path assoluto del file creato.
    """
    config_dir = Path("output") / f"timmy-kb-{slug}" / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    config_path = config_dir / "config.yaml"
    try:
        with open(config_path, "w", encoding="utf-8") as f:
            yaml.dump(config, f, allow_unicode=True)
        logger.info(f"✅ Config YAML scritto in: {config_path}")
    except Exception as e:
        logger.error(f"❌ Errore scrivendo config YAML in {config_path}: {e}")
        raise
    return config_path
