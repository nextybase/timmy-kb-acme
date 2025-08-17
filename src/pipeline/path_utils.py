# src/pipeline/path_utils.py
from pathlib import Path
import unicodedata
import re
import yaml
import os
from typing import Optional

def is_safe_subpath(path: Path, base: Path) -> bool:
    """
    Verifica se 'path' è contenuto all'interno di 'base' in modo sicuro.
    Usa path risolti (resolve) per evitare attacchi path traversal.
    """
    try:
        path_resolved = path.resolve()
        base_resolved = base.resolve()
        return base_resolved in path_resolved.parents or path_resolved == base_resolved
    except Exception as e:
        from pipeline.logging_utils import get_structured_logger
        logger = get_structured_logger(__name__)
        logger.error(f"Errore nella validazione path: {e}")
        return False


def _load_slug_regex() -> str:
    """
    Carica la regex slug da config/config.yaml, se presente.
    Ritorna la regex di default se il file non esiste o la chiave non è definita.
    """
    config_path = os.path.join("config", "config.yaml")
    default_regex = r"^[a-z0-9-]+$"
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f) or {}
            return cfg.get("slug_regex", default_regex)
        except Exception:
            return default_regex
    return default_regex


def is_valid_slug(slug: str) -> bool:
    """
    Valida lo slug secondo la regex configurata in config/config.yaml (chiave 'slug_regex'),
    altrimenti usa il default: solo lettere minuscole, numeri e trattini.
    """
    pattern = _load_slug_regex()
    return bool(re.fullmatch(pattern, slug))


def normalize_path(path: Path) -> Path:
    """
    Restituisce il path normalizzato e risolto.
    Utile per confronti consistenti e logging.
    """
    try:
        return path.resolve()
    except Exception as e:
        from pipeline.logging_utils import get_structured_logger
        logger = get_structured_logger(__name__)
        logger.error(f"Errore nella normalizzazione path: {e}")
        return path


def sanitize_filename(name: str, max_length: int = 100) -> str:
    """
    Pulisce un nome file rimuovendo caratteri non sicuri per il filesystem.
    - Rimuove caratteri vietati: <>:"/\\|?*
    - Normalizza Unicode in forma compatta (NFKC)
    - Tronca alla lunghezza massima specificata
    - Garantisce un valore di fallback non vuoto
    """
    try:
        # Normalizzazione unicode
        safe_name = unicodedata.normalize("NFKC", name)

        # Rimozione caratteri vietati
        safe_name = re.sub(r'[<>:"/\\|?*]', "_", safe_name)

        # Rimozione caratteri di controllo e trim spazi
        safe_name = re.sub(r'[\x00-\x1f\x7f]', '', safe_name).strip()

        # Troncamento
        if len(safe_name) > max_length:
            safe_name = safe_name[:max_length].rstrip()

        # Evita nomi vuoti
        if not safe_name:
            safe_name = "file"

        return safe_name
    except Exception as e:
        from pipeline.logging_utils import get_structured_logger
        logger = get_structured_logger(__name__)
        logger.error(f"Errore nella sanitizzazione nome file '{name}': {e}")
        return "file"
