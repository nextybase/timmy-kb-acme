# SPDX-License-Identifier: GPL-3.0-only
# src/pipeline/frontmatter_utils.py
from __future__ import annotations

"""
Utility condivise per frontmatter Markdown (parse/dump + read con cache).

Regole:
- Nessun I/O distruttivo; letture sicure tramite `path_utils.read_text_safe`.
- Cache opzionale invalidata da (mtime_ns, size) per ridurre YAML parse ripetuti.
- Import-safe: nessun side-effect a import-time.
"""

import re
from pathlib import Path
from typing import Any, Dict, Mapping, Tuple

try:
    import yaml
except Exception:  # pragma: no cover
    yaml = None  # type: ignore

from .exceptions import ConfigError
from .logging_utils import get_structured_logger
from .path_utils import ensure_within_and_resolve, read_text_safe

_LOGGER = get_structured_logger("pipeline.frontmatter_utils")

# Cache: {resolved_path: (mtime_ns, size, (meta, body))}
_CACHE: Dict[Path, Tuple[int, int, Tuple[Dict[str, Any], str]]] = {}


def parse_frontmatter(md_text: str, *, allow_fallback: bool = False) -> Tuple[Dict[str, Any], str]:
    if not md_text.startswith("---"):
        if allow_fallback:
            _LOGGER.warning("frontmatter.missing_fallback")
            return {}, md_text
        raise ConfigError("Frontmatter mancante")
    try:
        m = re.match(r"^---\r?\n(.*?)\r?\n---\r?\n", md_text, flags=re.DOTALL)
        if not m:
            if allow_fallback:
                _LOGGER.warning("frontmatter.invalid_fallback")
                return {}, md_text
            raise ConfigError("Frontmatter non valida")
        header = m.group(1)
        body = md_text[m.end() :]
        if yaml is None:
            if allow_fallback:
                _LOGGER.warning("frontmatter.yaml_unavailable_fallback")
                return {}, md_text
            raise ConfigError("yaml non disponibile")
        data = yaml.safe_load(header)
        if data is None:
            if allow_fallback:
                _LOGGER.warning("frontmatter.empty_fallback")
                return {}, body
            raise ConfigError("Frontmatter vuota")
        if not isinstance(data, dict):
            if allow_fallback:
                _LOGGER.warning("frontmatter.invalid_type_fallback")
                return {}, body
            raise ConfigError("Frontmatter non valida")
        return data, body
    except Exception as exc:
        if allow_fallback:
            return {}, md_text
        if isinstance(exc, ConfigError):
            raise
        raise ConfigError(f"Errore parse frontmatter: {exc}") from exc


def dump_frontmatter(meta: Mapping[str, Any], *, allow_fallback: bool = False) -> str:
    try:
        if yaml is None:
            raise RuntimeError("yaml unavailable")
        return "---\n" + yaml.safe_dump(dict(meta), sort_keys=False, allow_unicode=True).strip() + "\n---\n"
    except Exception as exc:
        if not allow_fallback:
            raise ConfigError(f"Errore dump frontmatter: {exc}") from exc
        # Fallback esplicito: serializzazione minima per contesti non-exec.
        lines = ["---"]
        for k, v in meta.items():
            if isinstance(v, list):
                lines.append(f"{k}:")
                lines.extend([f"  - {str(i)}" for i in v])
            elif v is not None:
                lines.append(f"{k}: {v}")
        lines.append("---\n")
        return "\n".join(lines)


def read_frontmatter(
    base: Path,
    path: Path,
    *,
    encoding: str = "utf-8",
    use_cache: bool = True,
    allow_fallback: bool = False,
) -> Tuple[Dict[str, Any], str]:
    safe = ensure_within_and_resolve(base, path)
    if use_cache:
        try:
            st = safe.stat()
            mtime_ns = int(getattr(st, "st_mtime_ns", int(st.st_mtime * 1e9)))
            size = int(st.st_size)
            cached = _CACHE.get(safe)
            if cached and cached[0] == mtime_ns and cached[1] == size:
                return cached[2]
        except Exception:
            pass

    text = read_text_safe(safe.parent, safe, encoding=encoding)
    meta, body = parse_frontmatter(text, allow_fallback=allow_fallback)

    if use_cache:
        try:
            st = safe.stat()
            mtime_ns = int(getattr(st, "st_mtime_ns", int(st.st_mtime * 1e9)))
            size = int(st.st_size)
            _CACHE[safe] = (mtime_ns, size, (meta, body))
        except Exception:
            pass
    return meta, body


def clear_frontmatter_cache() -> None:
    try:
        _CACHE.clear()
    except Exception:
        pass


__all__ = [
    "parse_frontmatter",
    "dump_frontmatter",
    "read_frontmatter",
    "clear_frontmatter_cache",
]
