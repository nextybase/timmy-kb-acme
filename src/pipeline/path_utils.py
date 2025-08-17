# src/pipeline/path_utils.py

"""
Utility di gestione path e slug per la pipeline Timmy-KB.

✅ Principi:
- Niente side-effect (no I/O esterni, salvo lettura facoltativa di config locale).
- Firme e comportamento invariati rispetto alla versione stabile.
- Logging strutturato solo in caso di errore (silenzioso quando tutto va bene).
"""

from pathlib import Path
import unicodedata
import re
import yaml
import os

from pipeline.logging_utils import get_structured_logger

# Punto di verità per messaggi di errore di questo modulo
_logger = get_structured_logger("pipeline.path_utils")


def is_safe_subpath(path: Path, base: Path) -> bool:
    """
    Verifica in modo sicuro se `path` è contenuto all'interno di `base`.
    Usa path risolti per prevenire path traversal.
    Ritorna False in caso di eccezioni durante la risoluzione.
    """
    try:
        path_resolved = Path(path).resolve()
        base_resolved = Path(base).resolve()
        return base_resolved in path_resolved.parents or path_resolved == base_resolved
    except Exception as e:
        _logger.error(f"Errore nella validazione path: {e}")
        return False


def _load_slug_regex() -> str:
    """
    Carica la regex per la validazione dello slug da `config/config.yaml` (chiave: slug_regex).
    Se il file non esiste o la chiave è assente/non valida, usa un default sicuro.
    Nota: qui non si usa ClientContext per evitare dipendenze circolari.
    """
    config_path = os.path.join("config", "config.yaml")
    default_regex = r"^[a-z0-9-]+$"
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f) or {}
            pattern = cfg.get("slug_regex", default_regex)
            return pattern if isinstance(pattern, str) and pattern else default_regex
        except Exception:
            # in caso di parsing/lettura problematica, fallback silenzioso
            return default_regex
    return default_regex


def is_valid_slug(slug: str) -> bool:
    """
    Valida lo `slug` secondo la regex di progetto (configurabile via `config/config.yaml`).
    Default: minuscole, numeri e trattini (`^[a-z0-9-]+$`).
    """
    pattern = _load_slug_regex()
    try:
        return bool(re.fullmatch(pattern, slug))
    except re.error as e:
        # Regex malformata in config → fallback sicuro
        _logger.error(f"Regex slug non valida in config: {e}")
        return bool(re.fullmatch(r"^[a-z0-9-]+$", slug))


def normalize_path(path: Path) -> Path:
    """
    Restituisce il path normalizzato/risolto.
    In caso di errore, ritorna il path originale senza interrompere il flusso.
    """
    try:
        return Path(path).resolve()
    except Exception as e:
        _logger.error(f"Errore nella normalizzazione path: {e}")
        return Path(path)


def sanitize_filename(name: str, max_length: int = 100) -> str:
    """
    Pulisce un nome file per l’uso su filesystem:
    - normalizza Unicode (NFKC)
    - sostituisce i caratteri vietati con underscore
    - rimuove controlli ASCII
    - tronca a `max_length`
    - garantisce un fallback non vuoto
    """
    try:
        # Normalizzazione unicode
        safe_name = unicodedata.normalize("NFKC", name)

        # Rimozione caratteri vietati
        safe_name = re.sub(r'[<>:"/\\|?*]', "_", safe_name)

        # Rimozione caratteri di controllo e trim
        safe_name = re.sub(r'[\x00-\x1f\x7f]', "", safe_name).strip()

        # Troncamento
        if len(safe_name) > max_length:
            safe_name = safe_name[:max_length].rstrip()

        # Fallback
        if not safe_name:
            safe_name = "file"

        return safe_name
    except Exception as e:
        _logger.error(f"Errore nella sanitizzazione nome file '{name}': {e}")
        return "file"


__all__ = [
    "is_safe_subpath",
    "_load_slug_regex",
    "is_valid_slug",
    "normalize_path",
    "sanitize_filename",
]
