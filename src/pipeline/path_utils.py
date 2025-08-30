# src/pipeline/path_utils.py
"""
Utility di gestione path e slug per la pipeline Timmy-KB.

Ruolo del modulo (path-safety SSoT + regole di normalizzazione):
- `is_safe_subpath(path, base) -> bool`
  Guardia **SOFT**: ritorna True/False se `path` ricade sotto `base`. Usare solo come pre-check.
- `ensure_within(base, target) -> None`
  Guardia **STRONG**: solleva `ConfigError` se `target` NON ricade sotto `base`. Da usare prima di write/copy/delete.
- `_load_slug_regex()` / `clear_slug_regex_cache()`
  Carica/azzera la regex di validazione slug da `config/config.yaml` (chiave `slug_regex`) con fallback sicuro.
- `is_valid_slug(slug)` / `validate_slug(slug)`
  Valida lo slug; `validate_slug` alza `InvalidSlug` se non conforme.
- `normalize_path(path) -> Path`
  Normalizza/risolve un path con gestione errori non-critica (log + fallback al path originale).
- `sanitize_filename(name, max_length=100) -> str`
  **Ottimizzata**: usa regex precompilata; ammette solo `[A-Za-z0-9_.-]`,
  compatta separatori, NFKC, tronca a `max_length`.
- `sorted_paths(paths, base=None) -> List[Path]`
  Ordinamento deterministico case-insensitive, relativo a `base` se fornita.
- `ensure_valid_slug(initial_slug, *, interactive, prompt, logger) -> str`
  Wrapper interattivo/non-interattivo che richiede/valida uno slug.

Principi:
- Nessun I/O distruttivo; solo letture facoltative (es. `config/config.yaml`).
- Logging strutturato solo su errori (silenzioso quando tutto ok).
- Portabilità: niente dipendenze da `ClientContext`; fallback a `Path.relative_to` dove serve.
"""

from __future__ import annotations

from pathlib import Path
import unicodedata
import re
import yaml
import logging
from typing import Optional, Iterable, List, Tuple, Callable
from functools import lru_cache  # caching per slug regex

from .exceptions import ConfigError, InvalidSlug
from .logging_utils import get_structured_logger

# Logger di modulo
_logger = get_structured_logger("pipeline.path_utils")

# -----------------------------------------------------------------------------
# Regex precompilate (micro-ottimizzazioni e chiarezza)
# -----------------------------------------------------------------------------
# Consenti lettere/numeri/underscore/punto/trattino; sostituisci il resto.
_SANITIZE_DISALLOWED_RE = re.compile(r"[^\w.\-]+", flags=re.UNICODE)


# Comprimi ripetizioni del carattere di rimpiazzo (iniettata dinamicamente)
def _compress_replacement(s: str, replacement: str) -> str:
    if not replacement:
        return s
    rep_re = re.compile(re.escape(replacement) + r"{2,}")
    return rep_re.sub(replacement, s)


def is_safe_subpath(path: Path, base: Path) -> bool:
    """
    Verifica in modo sicuro se `path` è contenuto all'interno di `base`.
    SOFT guard: usare SOLO come pre-check booleano (mai per autorizzare write/delete).

    Usa i percorsi risolti (realpath) per prevenire path traversal e link simbolici.
    In caso di eccezioni durante la risoluzione, ritorna `False` e registra un errore.
    """
    try:
        path_resolved = Path(path).resolve()
        base_resolved = Path(base).resolve()
        try:
            path_resolved.relative_to(base_resolved)
            return True
        except Exception:
            return False
    except Exception as e:
        _logger.error(
            "Errore nella validazione path (is_safe_subpath)",
            extra={"error": str(e), "path": str(path), "base": str(base)},
        )
        return False


def ensure_within(base: Path, target: Path) -> None:
    """
    Guardia STRONG: garantisce che `target` risieda sotto `base` una volta risolti i path.
    Solleva ConfigError se la condizione non è rispettata o se la risoluzione fallisce.

    Args:
        base: directory radice consentita.
        target: path del file/dir da validare.

    Note:
        - SSoT per sicurezza write/copy/delete.
        - Non restituire boolean: solleva eccezioni su casi non conformi.
    """
    try:
        base_r = Path(base).resolve()
        tgt_r = Path(target).resolve()
    except Exception as e:
        raise ConfigError(f"Impossibile risolvere i path: {e}", file_path=str(target)) from e

    try:
        tgt_r.relative_to(base_r)
    except Exception:
        raise ConfigError(
            f"Path traversal rilevato: {tgt_r} non è sotto {base_r}",
            file_path=str(target),
        )


@lru_cache(maxsize=1)
def _load_slug_regex() -> str:
    """
    Carica la regex per la validazione dello slug da `config/config.yaml` (chiave: `slug_regex`).

    Strategia:
    - Cerca prima `./config/config.yaml` (working dir),
      poi `<project_root>/config/config.yaml` risalendo da questo file.
    - Fallback: `^[a-z0-9-]+$`.
    """
    default_regex = r"^[a-z0-9-]+$"
    candidates = [
        Path("config") / "config.yaml",
        Path(__file__).resolve().parents[2] / "config" / "config.yaml",
    ]
    for cfg_path in candidates:
        try:
            if cfg_path.exists():
                with cfg_path.open("r", encoding="utf-8") as f:
                    cfg = yaml.safe_load(f) or {}
                pattern = cfg.get("slug_regex", default_regex)
                return pattern if isinstance(pattern, str) and pattern else default_regex
        except Exception as e:
            _logger.error(
                "Errore caricamento config slug_regex",
                extra={"error": str(e), "file_path": str(cfg_path)},
            )
    return default_regex


def clear_slug_regex_cache() -> None:
    """Svuota la cache della regex dello slug (da chiamare dopo update della config)."""
    try:
        _load_slug_regex.cache_clear()
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
    """Valida lo slug e alza un'eccezione di dominio in caso di non conformità."""
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


def sanitize_filename(name: str, max_length: int = 100, *, replacement: str = "_") -> str:
    """
    Pulisce un nome file per l’uso su filesystem.

    Operazioni:
    - normalizzazione Unicode (NFKC)
    - consente solo `[A-Za-z0-9_.-]`; gli altri caratteri diventano `replacement`
    - comprime ripetizioni contigue di `replacement` e trimma ai lati
    - rimuove caratteri di controllo
    - tronca a `max_length`
    - garantisce un fallback non vuoto

    Args:
        name: nome originale.
        max_length: lunghezza massima del risultato (default 100).
        replacement: carattere con cui sostituire i caratteri non permessi (default "_").
    """
    try:
        # Normalizzazione unicode
        s = unicodedata.normalize("NFKC", str(name or ""))

        # Sostituisci tutto ciò che non è [\w.-] con replacement
        s = _SANITIZE_DISALLOWED_RE.sub(replacement, s)

        # Rimuovi caratteri di controllo residui
        s = re.sub(r"[\x00-\x1f\x7f]", "", s)

        # Comprimi e ripulisci i separatori
        s = _compress_replacement(s, replacement).strip(replacement)

        # Troncamento “morbido”
        if max_length and len(s) > int(max_length):
            s = s[: int(max_length)].rstrip(replacement)

        # Fallback
        return s or "file"
    except Exception as e:
        _logger.error(
            "Errore nella sanitizzazione nome file", extra={"error": str(e), "name": name}
        )
        return "file"


# ----------------------------------------
# Ordinamento deterministico
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
    logger: logging.Logger,
) -> str:
    """
    Richiede/valida uno slug secondo le regole configurate (usa validate_slug).
    - In non-interactive: solleva ConfigError se slug mancante/invalido.
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
    "ensure_within",  # SSoT guardia STRONG
    "clear_slug_regex_cache",  # reset cache regex
    "is_valid_slug",
    "validate_slug",  # helper dominio
    "normalize_path",
    "sanitize_filename",
    "sorted_paths",  # ordinamento deterministico
    "ensure_valid_slug",  # wrapper interattivo
]
