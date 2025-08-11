from pathlib import Path
import unicodedata
import re
from pipeline.logging_utils import get_structured_logger

logger = get_structured_logger(__name__)

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
        logger.error(f"Errore nella validazione path: {e}")
        return False


def normalize_path(path: Path) -> Path:
    """
    Restituisce il path normalizzato e risolto.
    Utile per confronti consistenti e logging.
    """
    try:
        return path.resolve()
    except Exception as e:
        logger.error(f"Errore nella normalizzazione path: {e}")
        return path


def sanitize_filename(name: str, max_length: int = 100) -> str:
    """
    Pulisce un nome file rimuovendo caratteri non sicuri per il filesystem.
    - Rimuove caratteri vietati: <>:"/\\|?*
    - Normalizza Unicode in forma compatta (NFKC)
    - Trunca alla lunghezza massima specificata
    """
    try:
        # Normalizzazione unicode
        safe_name = unicodedata.normalize("NFKC", name)

        # Rimozione caratteri vietati
        safe_name = re.sub(r'[<>:"/\\|?*]', '_', safe_name)

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
        logger.error(f"Errore nella sanitizzazione nome file '{name}': {e}")
        return "file"
