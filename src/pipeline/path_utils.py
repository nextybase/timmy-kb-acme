# src/pipeline/path_utils.py
"""
Utility di gestione path e slug per la pipeline Timmy-KB.

✅ Principi:
- Niente side-effect (no I/O esterni, salvo lettura facoltativa di config locale).
- Logging strutturato solo in caso di errore (silenzioso quando tutto va bene).
- Le guardie STRONG sui path vivono in `pipeline.file_utils.ensure_within`.
"""

from __future__ import annotations

from pathlib import Path
import unicodedata
import re
import yaml
import os
import logging
from typing import Optional, Iterable, List, Tuple, Callable
from functools import lru_cache  # caching per slug regex

from .exceptions import ConfigError, InvalidSlug
from .logging_utils import get_structured_logger

# Punto di verità per messaggi di errore di questo modulo
_logger = get_structured_logger("pipeline.path_utils")


def is_safe_subpath(path: Path, base: Path) -> bool:
    """
    Verifica in modo sicuro se `path` è contenuto all'interno di `base`.

    Usa i percorsi risolti (realpath) per prevenire path traversal e link simbolici
    indesiderati. In caso di eccezioni durante la risoluzione, ritorna `False`
    e registra un errore sul logger di modulo.
    """
    try:
        path_resolved = Path(path).resolve()
        base_resolved = Path(base).resolve()
        # Implementazione robusta sugli edge-case (Python ≥ 3.10)
        return path_resolved.is_relative_to(base_resolved)
    except Exception as e:
        _logger.error(
            "Errore nella validazione path",
            extra={"error": str(e), "path": str(path), "base": str(base)},
        )
        return False


@lru_cache(maxsize=1)
def _load_slug_regex() -> str:
    """
    Carica la regex per la validazione dello slug da `config/config.yaml` (chiave: `slug_regex`).

    Se il file non esiste o la chiave è assente/non valida, usa un default sicuro.
    Non si usa ClientContext per evitare dipendenze circolari.
    """
    config_path = os.path.join("config", "config.yaml")
    default_regex = r"^[a-z0-9-]+$"
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f) or {}
            pattern = cfg.get("slug_regex", default_regex)
            return pattern if isinstance(pattern, str) and pattern else default_regex
        except Exception as e:
            _logger.error("Errore caricamento config slug_regex", extra={"error": str(e)})
            return default_regex
    return default_regex


def clear_slug_regex_cache() -> None:
    """Svuota la cache della regex dello slug (da chiamare dopo update della config)."""
    try:
        _load_slug_regex.cache_clear()  # type: ignore[attr-defined]
    except Exception as e:
        _logger.error("Errore nel reset della cache slug_regex", extra={"error": str(e)})


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
        _logger.error("Regex slug non valida in config", extra={"error": str(e)})
        return bool(re.fullmatch(r"^[a-z0-9-]+$", slug))


# -------------------------
# Helper dominio (quick win)
# -------------------------
def validate_slug(slug: str) -> str:
    """
    Valida lo slug e alza un'eccezione di dominio in caso di non conformità.
    """
    if not is_valid_slug(slug):
        raise InvalidSlug(f"Slug '{slug}' non valido secondo le regole configurate.", slug=slug)
    return slug


def normalize_path(path: Path) -> Path:
    """
    Restituisce il path normalizzato/risolto.

    In caso di errore, ritorna il path originale senza interrompere il flusso
    e registra l'errore sul logger.
    """
    try:
        return Path(path).resolve()
    except Exception as e:
        _logger.error("Errore nella normalizzazione path", extra={"error": str(e)})
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
        _logger.error("Errore nella sanitizzazione nome file", extra={"error": str(e), "name": name})
        return "file"


# ----------------------------------------
# Nuovo helper: ordinamento deterministico
# ----------------------------------------
def sorted_paths(paths: Iterable[Path], base: Optional[Path] = None) -> List[Path]:
    """
    Restituisce i path ordinati in modo deterministico.

    Criterio: confronto case-insensitive sul path relativo a `base` (se fornita),
    altrimenti sul path assoluto risolto. I path non risolvibili vengono gestiti
    con fallback non-eccezionale e inclusi comunque nell’ordinamento.
    """
    items: List[Tuple[str, Path]] = []
    base_resolved: Optional[Path] = None
    if base is not None:
        try:
            base_resolved = Path(base).resolve()
        except Exception:
            base_resolved = None

    for p in paths:
        q = Path(p)
        try:
            q_res = q.resolve()
        except Exception:
            q_res = q

        if base_resolved is not None:
            try:
                rel = q_res.relative_to(base_resolved).as_posix()
            except Exception:
                rel = q_res.as_posix()
            key = rel.lower()
        else:
            key = q_res.as_posix().lower()

        items.append((key, q))
    items.sort(key=lambda t: t[0])
    return [q for _, q in items]


def ensure_valid_slug(
    initial_slug: str | None,
    *,
    interactive: bool,
    prompt: Callable[[str], str],
    logger: logging.Logger
) -> str:
    """
    Richiede/valida uno slug secondo le regole configurate (usa validate_slug).
    - In non-interactive: solleva ConfigError se slug mancante/ invalido.
    - In interactive: ripete il prompt finché non è valido.
    """
    slug = (initial_slug or "").strip()
    while True:
        if not slug:
            if not interactive:
                raise ConfigError("Slug mancante.")
            slug = (prompt("Inserisci slug cliente: ") or "").strip()
            continue
        try:
            validate_slug(slug)
            return slug
        except InvalidSlug:
            logger.error("Slug non valido secondo le regole configurate.")
            if not interactive:
                raise
            slug = ""


__all__ = [
    "is_safe_subpath",
    "clear_slug_regex_cache",  # reset cache regex
    "is_valid_slug",
    "validate_slug",           # helper dominio
    "normalize_path",
    "sanitize_filename",
    "sorted_paths",            # ordinamento deterministico
    "ensure_valid_slug",       # wrapper interattivo
]
