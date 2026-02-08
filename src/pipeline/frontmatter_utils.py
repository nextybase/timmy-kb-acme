# SPDX-License-Identifier: GPL-3.0-or-later
# src/pipeline/frontmatter_utils.py
from __future__ import annotations

"""
Utility condivise per frontmatter Markdown (parse/dump + read con cache).

Regole:
- Nessun I/O distruttivo; letture sicure tramite `path_utils.read_text_safe`.
- Cache opzionale invalidata da (mtime_ns, size) per ridurre YAML parse ripetuti.
- Import-safe: nessun side-effect a import-time.
"""

import logging
import re
from pathlib import Path
from typing import Any, Dict, Mapping, Tuple

try:
    import yaml
except Exception:  # pragma: no cover
    yaml = None  # type: ignore

from .exceptions import ConfigError
from .path_utils import ensure_within_and_resolve, read_text_safe

LOG = logging.getLogger(__name__)

# Cache: {resolved_path: (mtime_ns, size, (meta, body))}
_CACHE: Dict[Path, Tuple[int, int, Tuple[Dict[str, Any], str]]] = {}


def parse_frontmatter(md_text: str) -> Tuple[Dict[str, Any], str]:
    if not md_text.startswith("---"):
        raise ConfigError("Frontmatter mancante")
    try:
        m = re.match(r"^---\r?\n(.*?)\r?\n---\r?\n", md_text, flags=re.DOTALL)
        if not m:
            raise ConfigError("Frontmatter non valida")
        header = m.group(1)
        body = md_text[m.end() :]
        if yaml is None:
            raise ConfigError("yaml non disponibile")
        data = yaml.safe_load(header)
        if data is None:
            raise ConfigError("Frontmatter vuota")
        if not isinstance(data, dict):
            raise ConfigError("Frontmatter non valida")
        return data, body
    except Exception as exc:
        if isinstance(exc, ConfigError):
            raise
        raise ConfigError("Errore parse frontmatter.") from exc


def dump_frontmatter(meta: Mapping[str, Any]) -> str:
    try:
        if yaml is None:
            raise RuntimeError("yaml unavailable")
        return "---\n" + yaml.safe_dump(dict(meta), sort_keys=False, allow_unicode=True).strip() + "\n---\n"
    except Exception as exc:
        raise ConfigError("Errore dump frontmatter.") from exc


def _stat_signature(p: Path) -> tuple[int, int] | None:
    """Ritorna (mtime_ns, size) oppure None se non disponibile.

    Nota: la cache è un'ottimizzazione; se la stat fallisce, degradiamo a "no cache"
    ma in modo osservabile (debug).
    """
    try:
        st = p.stat()
        mtime_ns = int(getattr(st, "st_mtime_ns", int(st.st_mtime * 1e9)))
        size = int(st.st_size)
        return mtime_ns, size
    except Exception:
        LOG.debug("frontmatter.cache.stat_failed", extra={"path": str(p)}, exc_info=True)
        return None


def read_frontmatter(
    base: Path,
    path: Path,
    *,
    encoding: str = "utf-8",
    use_cache: bool = True,
) -> Tuple[Dict[str, Any], str]:
    safe = ensure_within_and_resolve(base, path)

    if use_cache:
        sig = _stat_signature(safe)
        if sig is not None:
            mtime_ns, size = sig
            cached = _CACHE.get(safe)
            if cached and cached[0] == mtime_ns and cached[1] == size:
                return cached[2]

    text = read_text_safe(safe.parent, safe, encoding=encoding)
    meta, body = parse_frontmatter(text)

    if use_cache:
        sig = _stat_signature(safe)
        if sig is not None:
            mtime_ns, size = sig
            _CACHE[safe] = (mtime_ns, size, (meta, body))
        else:
            # cache write skipped (già loggato da _stat_signature)
            pass

    return meta, body


def clear_frontmatter_cache() -> None:
    try:
        _CACHE.clear()
    except Exception:
        # Anche questo è best-effort, ma non silenzioso.
        LOG.debug("frontmatter.cache.clear_failed", exc_info=True)


__all__ = [
    "parse_frontmatter",
    "dump_frontmatter",
    "read_frontmatter",
    "clear_frontmatter_cache",
]
