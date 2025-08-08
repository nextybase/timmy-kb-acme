"""
utils.py
Utility di validazione e supporto per la pipeline Timmy-KB.
"""

import logging
import re
import yaml
from pathlib import Path
from typing import Optional

from pipeline.exceptions import PreOnboardingValidationError, PipelineError
from pipeline.constants import CONFIG_FILE_NAME


def is_valid_slug(slug: Optional[str] = None) -> bool:
    """
    Verifica che lo slug sia conforme al pattern definito in settings.
    """
    if slug is None:
        from pipeline.config_utils import settings  # import locale anti-ciclo
        slug = getattr(settings, "slug", None)

    if not slug:
        return False

    normalized_slug = slug.replace("_", "-").lower()
    from pipeline.config_utils import settings  # import locale per pattern
    pattern = getattr(settings, "SLUG_PATTERN", r"[a-z0-9-]+")
    if not re.fullmatch(pattern, normalized_slug):
        logging.getLogger("slug.validation").debug(
            f"Slug '{slug}' non valido. Normalizzato: '{normalized_slug}', pattern: {pattern}"
        )
        return False
    return True


def _validate_path_in_base_dir(path: Path, base_dir: Path) -> None:
    """
    Verifica che il path sia figlio di base_dir.
    """
    resolved_path = path.resolve()
    if not str(resolved_path).startswith(str(base_dir.resolve())):
        raise PipelineError(f"Percorso non consentito: {resolved_path} fuori da {base_dir}")


def validate_preonboarding_environment(base_dir: Optional[Path] = None, logger: Optional[logging.Logger] = None) -> None:
    """
    STEP 1: Verifica config principale.
    STEP 2: Verifica directory critiche.
    """
    if logger is None:
        logger = logging.getLogger("preonboarding.validation")

    if base_dir is None:
        from pipeline.config_utils import settings  # import locale anti-ciclo
        base_dir = getattr(settings, "base_dir", Path("."))

    # STEP 1 – Validazione config principale
    config_path = Path("config") / CONFIG_FILE_NAME
    config_path = config_path.resolve()

    if not config_path.exists():
        logger.error(f"❌ File di configurazione non trovato: {config_path}")
        raise PreOnboardingValidationError(f"File di configurazione non trovato: {config_path}")

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
    except Exception as e:
        logger.error(f"❌ Errore di lettura/parsing YAML in {config_path}: {e}")
        raise PreOnboardingValidationError(f"Errore di lettura/parsing YAML in {config_path}: {e}")

    required_base_keys = ["cartelle_raw_yaml"]
    missing_keys = [k for k in required_base_keys if k not in config]
    if missing_keys:
        logger.error(f"❌ Chiavi obbligatorie mancanti in {config_path}: {missing_keys}")
        raise PreOnboardingValidationError(f"Chiavi obbligatorie mancanti: {missing_keys}")

    logger.info(f"✅ Config {config_path} esistente e leggibile.")

    # STEP 2 – Validazione e creazione directory critiche
    required_dirs = ["logs"]
    for dir_name in required_dirs:
        dir_path = Path(dir_name).resolve()
        try:
            _validate_path_in_base_dir(dir_path, base_dir)
        except PipelineError as e:
            logger.error(f"❌ Directory fuori scope: {dir_path}")
            raise PreOnboardingValidationError(str(e))
        if not dir_path.exists():
            logger.warning(f"⚠️ Directory mancante: {dir_path}, creazione automatica...")
            dir_path.mkdir(parents=True, exist_ok=True)

    logger.info("✅ Tutti i file e le directory richieste sono presenti o create.")
