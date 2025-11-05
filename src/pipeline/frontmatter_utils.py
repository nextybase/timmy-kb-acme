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

from .path_utils import ensure_within_and_resolve, read_text_safe

# Cache: {resolved_path: (mtime_ns, size, (meta, body))}
_CACHE: Dict[Path, Tuple[int, int, Tuple[Dict[str, Any], str]]] = {}


def parse_frontmatter(md_text: str) -> Tuple[Dict[str, Any], str]:
    if not md_text.startswith("---"):
        return {}, md_text
    try:
        m = re.match(r"^---\r?\n(.*?)\r?\n---\r?\n", md_text, flags=re.DOTALL)
        if not m:
            return {}, md_text
        header = m.group(1)
        body = md_text[m.end() :]
        if yaml is None:
            return {}, md_text
        data = yaml.safe_load(header) or {}
        return data if isinstance(data, dict) else {}, body
    except Exception:
        return {}, md_text


def dump_frontmatter(meta: Mapping[str, Any]) -> str:
    try:
        if yaml is None:
            raise RuntimeError("yaml unavailable")
        return "---\n" + yaml.safe_dump(dict(meta), sort_keys=False, allow_unicode=True).strip() + "\n---\n"
    except Exception:
        # Fallback minimale
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
    meta, body = parse_frontmatter(text)

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
