# SPDX-License-Identifier: GPL-3.0-only
# src/pipeline/path_utils.py
"""Utility di gestione path e slug per la pipeline Timmy-KB.

Ruolo del modulo (path-safety SSoT + regole di normalizzazione):
- `is_safe_subpath(path, base) -> bool`
  Guardia **SOFT**: ritorna True/False se `path` ricade sotto `base`. Usare solo come pre-check.
- `ensure_within(base, target) -> None`
  Guardia **STRONG**: solleva `ConfigError` se `target` NON ricade sotto `base`.
  Da usare prima di write/copy/delete.
- `_load_slug_regex()` / `clear_slug_regex_cache()`
  Carica/azzera la regex di validazione slug da `config/config.yaml`
  (chiave `slug_regex`) con fallback sicuro.
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

import logging
import os
import re
import time
import unicodedata
from collections import OrderedDict
from contextlib import contextmanager
from dataclasses import dataclass
from functools import lru_cache  # caching per slug regex
from pathlib import Path
from typing import Any, BinaryIO, Callable, Iterable, Iterator, List, Optional, Sequence, TextIO, Tuple

from .exceptions import ConfigError, InvalidSlug, PathTraversalError
from .logging_utils import get_structured_logger
from .yaml_utils import yaml_read

# Logger di modulo
_logger = get_structured_logger("pipeline.path_utils")

# Prefissi path estesi Windows
_WIN_EXTENDED_PREFIX = "\\\\?\\"
_WIN_UNC_PREFIX = "\\\\?\\UNC\\"

# -----------------------------------------------------------------------------
# Regex precompilate (micro-ottimizzazioni e chiarezza)
# -----------------------------------------------------------------------------
# Consenti lettere/numeri/underscore/punto/trattino; sostituisci il resto.
_SANITIZE_DISALLOWED_RE = re.compile(r"[^\w.\-]+", flags=re.UNICODE)


# Cache opportunistica per iter_safe_pdfs
_DEFAULT_RAW_CACHE_TTL = 300.0
_DEFAULT_RAW_CACHE_CAPACITY = 8
_SAFE_PDF_CACHE_CAPACITY = _DEFAULT_RAW_CACHE_CAPACITY


@dataclass(frozen=True)
class _SafePdfCacheEntry:
    mtime: float
    files: tuple[Path, ...]
    timestamp: float


_SAFE_PDF_CACHE: "OrderedDict[Path, _SafePdfCacheEntry]" = OrderedDict()
_SAFE_PDF_CACHE_DEFAULT_TTL = _DEFAULT_RAW_CACHE_TTL
_CACHE_DEFAULTS_LOADED = False


def _parse_positive_float(value: Any, default: float) -> float:
    try:
        parsed = float(str(value).strip())
        return parsed if parsed >= 0 else default
    except Exception:
        return default


def _parse_positive_int(value: Any, default: int) -> int:
    try:
        parsed = int(float(str(value).strip()))
        return parsed if parsed > 0 else default
    except Exception:
        return default


def _load_raw_cache_defaults() -> None:
    """Carica TTL/capacita della cache RAW da config/config.yaml."""
    global _SAFE_PDF_CACHE_DEFAULT_TTL, _SAFE_PDF_CACHE_CAPACITY

    ttl = _DEFAULT_RAW_CACHE_TTL
    capacity = _DEFAULT_RAW_CACHE_CAPACITY

    config_path = Path(__file__).resolve().parents[2] / "config" / "config.yaml"
    try:
        config = yaml_read(config_path.parent, config_path, use_cache=True) or {}
        cfg = (config.get("raw_cache") or {}) if isinstance(config, dict) else {}
        ttl = _parse_positive_float(cfg.get("ttl_seconds"), ttl)
        capacity = _parse_positive_int(cfg.get("max_entries"), capacity)
    except Exception as exc:
        # se il file manca o e' invalido manteniamo i fallback ma segnaliamo warning
        _logger.warning(
            "pipeline.raw_cache.defaults_invalid",
            extra={"error": str(exc), "config_path": str(config_path)},
        )

    _SAFE_PDF_CACHE_DEFAULT_TTL = ttl
    _SAFE_PDF_CACHE_CAPACITY = capacity


def _ensure_raw_cache_defaults_loaded() -> None:
    global _CACHE_DEFAULTS_LOADED
    if _CACHE_DEFAULTS_LOADED:
        return
    _CACHE_DEFAULTS_LOADED = True
    _load_raw_cache_defaults()


def _dir_mtime(path: Path) -> float:
    try:
        return float(path.stat().st_mtime)
    except Exception:
        return 0.0


def clear_iter_safe_pdfs_cache(*, root: Path | None = None) -> None:
    """Invalidates the cached PDF listings (entire cache or a specific root)."""
    _ensure_raw_cache_defaults_loaded()
    if root is None:
        _SAFE_PDF_CACHE.clear()
        return
    try:
        resolved = Path(root).resolve()
    except Exception:
        return
    _SAFE_PDF_CACHE.pop(resolved, None)


def _resolve_raw_root_from_path(path: Path | str) -> Path | None:
    try:
        resolved = Path(path).resolve()
    except Exception:
        return None
    parts = list(resolved.parts)
    for idx, part in enumerate(parts):
        if part.lower() == "raw":
            return Path(*parts[: idx + 1])
    return None


def preload_iter_safe_pdfs_cache(
    root: Path,
    *,
    on_skip: Callable[[Path, str], None] | None = None,
) -> tuple[Path, ...]:
    """
    Pre-carica la cache dei PDF sicuri per `root`, restituendo lo snapshot.

    Se `root` non �� valido viene effettuata solo l'invalidazione.
    """
    _ensure_raw_cache_defaults_loaded()
    try:
        resolved_root = Path(root).resolve()
    except Exception:
        return tuple()

    if not resolved_root.exists() or not resolved_root.is_dir():
        clear_iter_safe_pdfs_cache(root=resolved_root)
        return tuple()

    pdfs = tuple(
        iter_safe_paths(
            resolved_root,
            include_dirs=False,
            include_files=True,
            suffixes=(".pdf",),
            on_skip=on_skip,
        )
    )
    if pdfs:
        _SAFE_PDF_CACHE[resolved_root] = _SafePdfCacheEntry(
            mtime=_dir_mtime(resolved_root),
            files=pdfs,
            timestamp=time.time(),
        )
        while len(_SAFE_PDF_CACHE) > _SAFE_PDF_CACHE_CAPACITY:
            _SAFE_PDF_CACHE.popitem(last=False)
    else:
        _SAFE_PDF_CACHE.pop(resolved_root, None)
    return pdfs


def refresh_iter_safe_pdfs_cache_for_path(
    path: Path,
    *,
    prewarm: bool = True,
    on_skip: Callable[[Path, str], None] | None = None,
) -> None:
    """
    Invalida (ed opzionalmente pre-riscalda) la cache PDF se `path` ricade in un albero `raw/`.
    """
    _ensure_raw_cache_defaults_loaded()
    raw_root = _resolve_raw_root_from_path(path)
    if raw_root is None:
        return
    clear_iter_safe_pdfs_cache(root=raw_root)
    if prewarm:
        preload_iter_safe_pdfs_cache(raw_root, on_skip=on_skip)


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
            "path_utils.validation_error",
            extra={"error": str(e), "path": str(path), "base": str(base)},
        )
        return False


def _resolve_and_check(base: Path | str, candidate: Path | str) -> Path:
    """Resolve base and candidate paths and ensure the candidate stays within base."""
    try:
        base_resolved = Path(base).resolve()
        candidate_resolved = Path(candidate).resolve()
    except Exception as exc:
        raise ConfigError(
            f"Unable to resolve paths: {exc}",
            file_path=str(candidate),
        ) from exc

    try:
        candidate_resolved.relative_to(base_resolved)
    except Exception as exc:
        raise PathTraversalError(
            f"Path traversal detected: {candidate_resolved} is not under {base_resolved}",
            file_path=str(candidate),
        ) from exc

    return candidate_resolved


def ensure_within(base: Path | str, target: Path | str) -> None:
    """Strong guard that validates the target stays within the base perimeter."""
    _resolve_and_check(base, target)


def ensure_within_and_resolve(base: Path | str, candidate: Path | str) -> Path:
    """Resolve a candidate path ensuring it remains within the base perimeter."""
    return _resolve_and_check(base, candidate)


def iter_safe_paths(
    root: Path,
    *,
    include_dirs: bool = False,
    include_files: bool = True,
    suffixes: Sequence[str] | None = None,
    on_skip: Callable[[Path, str], None] | None = None,
) -> Iterator[Path]:
    """
    Itera ricorsivamente percorsi sotto `root` applicando path-safety forte.

    Args:
        root: directory da scandire.
        include_dirs: se True, restituisce anche le directory non-root.
        include_files: se True, restituisce i file ammessi.
        suffixes: lista di suffissi (minuscoli) da accettare per i file;
            se None accetta tutti i file.
        on_skip: callback opzionale invocata con (path, motivo) per
            symlink, errori di resolve o altre condizioni scartate.
    """

    if not include_dirs and not include_files:
        return

    suffix_set = None
    if suffixes is not None:
        suffix_set = {s.lower() for s in suffixes}

    try:
        root_resolved = Path(root).resolve()
    except Exception as exc:
        if on_skip:
            on_skip(Path(root), f"resolve-root:{exc}")
        return

    if not root_resolved.exists() or not root_resolved.is_dir():
        return

    def _traverse(current: Path) -> Iterator[Path]:
        try:
            entries = sorted(current.iterdir(), key=lambda p: p.name.lower())
        except Exception as exc:
            if on_skip:
                on_skip(current, f"iterdir:{exc}")
            return

        for entry in entries:
            try:
                safe_entry = ensure_within_and_resolve(root_resolved, entry)
            except Exception as exc:
                if on_skip:
                    on_skip(entry, f"resolve:{exc}")
                continue

            try:
                if entry.is_symlink():
                    if on_skip:
                        on_skip(entry, "symlink")
                    continue
            except Exception as exc:
                if on_skip:
                    on_skip(entry, f"symlink-check:{exc}")
                continue

            try:
                is_dir = entry.is_dir()
            except Exception as exc:
                if on_skip:
                    on_skip(entry, f"stat:{exc}")
                continue

            if is_dir:
                if include_dirs:
                    yield safe_entry
                yield from _traverse(safe_entry)
            else:
                if not include_files:
                    continue
                if suffix_set is not None:
                    if safe_entry.suffix.lower() not in suffix_set:
                        continue
                yield safe_entry

    yield from _traverse(root_resolved)


def iter_safe_pdfs(
    root: Path,
    *,
    on_skip: Callable[[Path, str], None] | None = None,
    use_cache: bool = False,
    cache_ttl_s: float | None = None,
) -> Iterator[Path]:
    """Convenience wrapper che restituisce solo file PDF in modo path-safe."""
    if not use_cache:
        yield from iter_safe_paths(
            root,
            include_dirs=False,
            include_files=True,
            suffixes=(".pdf",),
            on_skip=on_skip,
        )
        return

    _ensure_raw_cache_defaults_loaded()
    try:
        resolved_root = Path(root).resolve()
    except Exception as exc:
        if on_skip:
            on_skip(Path(root), f"resolve-root:{exc}")
        return

    if not resolved_root.exists() or not resolved_root.is_dir():
        clear_iter_safe_pdfs_cache(root=resolved_root)
        return

    current_mtime = _dir_mtime(resolved_root)
    cached = _SAFE_PDF_CACHE.get(resolved_root)
    effective_ttl = cache_ttl_s if cache_ttl_s is not None else _SAFE_PDF_CACHE_DEFAULT_TTL
    if cached and abs(cached.mtime - current_mtime) <= 1e-6:
        if effective_ttl and effective_ttl > 0:
            if (time.time() - cached.timestamp) > effective_ttl:
                cached = None
        if cached:
            _SAFE_PDF_CACHE.move_to_end(resolved_root)
            for cached_path in cached.files:
                yield cached_path
            return

    pdfs = preload_iter_safe_pdfs_cache(resolved_root, on_skip=on_skip)

    for pdf in pdfs:
        yield pdf


@contextmanager
def open_for_read(
    base: Path,
    p: Path,
    *,
    encoding: str = "utf-8",
    newline: str | None = None,
) -> Iterator[TextIO]:
    """
    Helper ergonomico: apre in lettura un file entro il perimetro `base` in modo sicuro.

    Esempio:
        with open_for_read(book_dir, md) as f:
            text = f.read()
    """
    safe_p = ensure_within_and_resolve(base, p)
    f = safe_p.open("r", encoding=encoding, newline=newline)
    try:
        yield f
    finally:
        try:
            f.close()
        except Exception:
            pass


@contextmanager
def open_for_read_bytes_selfguard(p: Path) -> Iterator[BinaryIO]:
    """Apre un file in lettura binaria applicando una guardia di path-safety locale.

    Regola: il path risolto deve restare sotto la propria directory padre.
    Impedisce traversal via symlink o componenti "..".

    Args:
        p: Path del file da leggere (binario).

    Ritorna:
        Context manager che fornisce un handle binario sicuro.

    Raises:
        ConfigError: se la risoluzione fallisce, se il path esce dalla dir padre
        o se l'apertura del file fallisce.
    """
    safe_p = ensure_within_and_resolve(p.parent, p)
    try:
        f = safe_p.open("rb")
    except Exception as e:  # pragma: no cover
        raise ConfigError(f"Errore apertura file: {e}", file_path=str(safe_p)) from e
    try:
        yield f
    finally:
        try:
            f.close()
        except Exception:
            pass


def read_text_safe(base: Path, p: Path, *, encoding: str = "utf-8") -> str:
    """Legge l'intero contenuto testo applicando path-safety (wrapper comodo)."""
    safe_p = ensure_within_and_resolve(base, p)
    return safe_p.read_text(encoding=encoding)


@lru_cache(maxsize=1)
def _load_slug_regex() -> str:
    """Carica la regex per la validazione dello slug da `config/config.yaml` (chiave: `slug_regex`).

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
                from pipeline.yaml_utils import yaml_read

                cfg = yaml_read(cfg_path.parent, cfg_path) or {}
                pattern = cfg.get("slug_regex", default_regex)
                return pattern if isinstance(pattern, str) and pattern else default_regex
        except Exception as e:
            _logger.error(
                "path_utils.slug_regex_load_error",
                extra={"error": str(e), "file_path": str(cfg_path)},
            )
    return default_regex


def clear_slug_regex_cache() -> None:
    """Svuota la cache della regex dello slug (da chiamare dopo update della config)."""
    try:
        _load_slug_regex.cache_clear()
    except Exception as e:
        _logger.error("path_utils.slug_regex_reset_failed", extra={"error": str(e)})


def is_valid_slug(slug: str) -> bool:
    """Valida lo `slug` secondo la regex di progetto (configurabile via `config/config.yaml`).

    Default: minuscole, numeri e trattini (`^[a-z0-9-]+$`).
    """
    pattern = _load_slug_regex()
    try:
        return bool(re.fullmatch(pattern, slug))
    except re.error as e:
        # Regex malformata in config → fallback sicuro
        _logger.error("path_utils.slug_regex_invalid", extra={"error": str(e)})
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
    """Restituisce il path normalizzato/risolto.

    In caso di errore, ritorna il path originale senza interrompere il flusso e registra l'errore
    sul logger.
    """
    try:
        return Path(path).resolve()
    except Exception as e:
        _logger.error("path_utils.normalize_error", extra={"error": str(e)})
        return Path(path)


def sanitize_filename(name: str, max_length: int = 100, *, replacement: str = "_") -> str:
    """Pulisce un nome file per l’uso su filesystem.

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
            "path_utils.sanitize_filename.error",
            extra={"error": str(e), "raw_name": name},
        )
        return "file"


def to_kebab(s: str) -> str:
    """Normalizza una stringa in kebab-case stabile per nomi cartella.

    Regole:
    - trim + lower
    - sostituisce spazi/underscore con '-'
    - rimuove caratteri non [a-z0-9-]
    - comprime '-' ripetuti e li trimma ai lati
    """
    try:
        import re as _re

        s = (s or "").strip().lower().replace("_", "-").replace(" ", "-")
        s = _re.sub(r"[^a-z0-9-]+", "-", s)
        s = _re.sub(r"-{2,}", "-", s).strip("-")
        return s
    except Exception:
        return str(s or "").strip().lower() or "-"


# ----------------------------------------
# Ordinamento deterministico
# ----------------------------------------
def sorted_paths(paths: Iterable[Path], base: Optional[Path] = None) -> List[Path]:
    """Restituisce i path ordinati in modo deterministico.

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


def to_extended_length_path(path: Path | str) -> str:
    """
    Restituisce il path con prefisso esteso Windows (\\?\\) quando necessario.

    - Su sistemi non-Windows ritorna semplicemente `str(path)`.
    - Su Windows converte in percorso assoluto normalizzato e aggiunge il prefisso
      extended-length. I path UNC (`\\\\server\\share`) vengono trasformati in
      `\\\\?\\UNC\\server\\share`.
    - Path gi\u00e0 estesi vengono restituiti invariati.
    """
    path_obj = Path(path)
    path_str = str(path_obj)
    if os.name != "nt":
        return path_str

    if path_str.startswith(_WIN_EXTENDED_PREFIX) or path_str.startswith(_WIN_UNC_PREFIX):
        return os.path.normpath(path_str)

    # Garantisce path assoluto senza richiedere l'esistenza sul filesystem
    if not path_obj.is_absolute():
        path_obj = path_obj.absolute()
        path_str = str(path_obj)
    else:
        path_str = os.path.normpath(path_str)

    if path_str.startswith("\\\\"):
        return _WIN_UNC_PREFIX + path_str[2:]

    return _WIN_EXTENDED_PREFIX + path_str.lstrip("\\")


def strip_extended_length_path(path: Path | str) -> Path:
    """
    Rimuove il prefisso esteso Windows restituendo un `Path` normale.
    Su sistemi non-Windows ritorna semplicemente `Path(path)`.
    """
    path_str = str(path)
    if os.name != "nt":
        return Path(path_str)

    if path_str.startswith(_WIN_UNC_PREFIX):
        return Path("\\" * 2 + path_str[len(_WIN_UNC_PREFIX) :])

    if path_str.startswith(_WIN_EXTENDED_PREFIX):
        return Path(path_str[len(_WIN_EXTENDED_PREFIX) :])

    return Path(path_str)


def ensure_valid_slug(
    initial_slug: str | None,
    *,
    interactive: bool,
    prompt: Callable[[str], str],
    logger: logging.Logger,
) -> str:
    """Richiede/valida uno slug secondo le regole configurate (usa validate_slug).

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
            logger.error("path_utils.slug_invalid", extra={"slug": slug})
            if not interactive:
                raise
            slug = ""


__all__ = [
    "is_safe_subpath",
    "ensure_within",  # SSoT guardia STRONG
    "ensure_within_and_resolve",  # guardia LETTURA + resolve
    "open_for_read",  # helper ergonomico context manager
    "open_for_read_bytes_selfguard",  # helper ergonomico binario (self-guard)
    "read_text_safe",  # helper ergonomico testo
    "clear_slug_regex_cache",  # reset cache regex
    "is_valid_slug",
    "validate_slug",  # helper dominio
    "normalize_path",
    "sanitize_filename",
    "sorted_paths",  # ordinamento deterministico
    "ensure_valid_slug",  # wrapper interattivo
    "iter_safe_paths",
    "iter_safe_pdfs",
    "clear_iter_safe_pdfs_cache",
    "preload_iter_safe_pdfs_cache",
    "refresh_iter_safe_pdfs_cache_for_path",
    "to_extended_length_path",
    "strip_extended_length_path",
]
