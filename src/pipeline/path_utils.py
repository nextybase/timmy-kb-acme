# src/pipeline/path_utils.py
"""
Utility di gestione path e slug per la pipeline Timmy-KB.

✅ Principi:
- Niente side-effect (no I/O esterni, salvo lettura facoltativa di config locale).
- Firme e comportamento invariati rispetto alla versione stabile.
- Logging strutturato solo in caso di errore (silenzioso quando tutto va bene).
"""

from __future__ import annotations

from pathlib import Path
import unicodedata
import re
import yaml
import os
from typing import Optional
from functools import lru_cache  # ← aggiunto per caching

from pipeline.logging_utils import get_structured_logger

# Punto di verità per messaggi di errore di questo modulo
_logger = get_structured_logger("pipeline.path_utils")


def is_safe_subpath(path: Path, base: Path) -> bool:
    """
    Verifica in modo sicuro se `path` è contenuto all'interno di `base`.

    Usa i percorsi **risolti** (realpath) per prevenire path traversal e link simbolici
    indesiderati. In caso di eccezioni durante la risoluzione, ritorna `False`
    e registra un errore sul logger di modulo.

    Args:
        path: Path da validare.
        base: Directory radice consentita.

    Returns:
        `True` se `path` è uguale a `base` o è un suo discendente; `False` altrimenti.
    """
    try:
        path_resolved = Path(path).resolve()
        base_resolved = Path(base).resolve()
        return base_resolved in path_resolved.parents or path_resolved == base_resolved
    except Exception as e:
        _logger.error(f"Errore nella validazione path: {e}")
        return False


@lru_cache(maxsize=1)  # ← cache 1-entry: invalida esplicitamente dopo update config
def _load_slug_regex() -> str:
    """
    Carica la regex per la validazione dello slug da `config/config.yaml` (chiave: `slug_regex`).

    Se il file non esiste o la chiave è assente/non valida, usa un default sicuro.

    Note:
        Non si usa `ClientContext` per evitare dipendenze circolari.

    Returns:
        La regex (come stringa) da usare per la validazione dello slug.
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


def clear_slug_regex_cache() -> None:
    """
    Svuota la cache della regex dello slug.

    Usa questa funzione dopo aver aggiornato/sovrascritto `config/config.yaml`
    per rendere effettivo il nuovo valore di `slug_regex` senza riavviare il processo.
    """
    try:
        _load_slug_regex.cache_clear()  # type: ignore[attr-defined]
    except Exception as e:
        _logger.error(f"Errore nel reset della cache slug_regex: {e}")


def is_valid_slug(slug: str) -> bool:
    """
    Valida lo `slug` secondo la regex di progetto (configurabile via `config/config.yaml`).

    Default: minuscole, numeri e trattini (`^[a-z0-9-]+$`).

    Args:
        slug: Stringa da validare come identificatore cliente.

    Returns:
        `True` se lo slug è conforme alla regex di progetto, `False` altrimenti.
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

    In caso di errore, ritorna il path originale senza interrompere il flusso
    e registra l'errore sul logger.

    Args:
        path: Percorso da normalizzare.

    Returns:
        Il percorso risolto (o quello originale in caso di errore).
    """
    try:
        return Path(path).resolve()
    except Exception as e:
        _logger.error(f"Errore nella normalizzazione path: {e}")
        return Path(path)


def sanitize_filename(name: str, max_length: int = 100) -> str:
    """
    Pulisce un nome file per l’uso su filesystem.

    Operazioni:
    - normalizza Unicode (NFKC)
    - sostituisce i caratteri vietati con underscore
    - rimuove controlli ASCII
    - tronca a `max_length`
    - garantisce un fallback non vuoto

    Args:
        name: Nome file di partenza (potenzialmente non sicuro).
        max_length: Lunghezza massima consentita per il nome finale.

    Returns:
        Un nome file sicuro e non vuoto.
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
    "clear_slug_regex_cache",  # ← export della funzione di reset cache
    "is_valid_slug",
    "normalize_path",
    "sanitize_filename",
]
