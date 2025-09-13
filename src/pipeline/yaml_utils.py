"""
Utility centralizzata per la lettura YAML sicura e uniforme.

Obiettivi
- Path-safety: valida che il file sia sotto una base consentita (fail-closed).
- Encoding coerente (utf-8) e SafeLoader ovunque.
- Errori chiari e consistenti (ConfigError con file_path).
- Cache opzionale con invalidazione su mtime/size per ridurre I/O.

Nota: questo modulo NON importa pipeline.path_utils per evitare cicli di import;
replica qui la sola guardia di lettura necessaria.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Tuple

import yaml

from .exceptions import ConfigError

# Cache: {resolved_path: (mtime_ns, size, value)}
_CACHE: Dict[Path, Tuple[int, int, Any]] = {}


def _ensure_within_and_resolve(base: Path | str, p: Path | str) -> Path:
    """Valida che `p` ricada sotto `base` e ritorna il path risolto.

    Fail-closed: solleva ConfigError su violazioni o risoluzioni fallite.
    """
    try:
        base_r = Path(base).resolve()
        p_r = Path(p).resolve()
    except Exception as e:  # pragma: no cover
        raise ConfigError(f"Impossibile risolvere i path: {e}", file_path=str(p)) from e
    try:
        p_r.relative_to(base_r)
    except Exception:
        raise ConfigError(
            f"Path di lettura non consentito: {p_r} non è sotto {base_r}",
            file_path=str(p),
        )
    return p_r


def yaml_read(
    base: Path | str,
    path: Path | str,
    *,
    encoding: str = "utf-8",
    use_cache: bool = True,
) -> Any:
    """Legge un file YAML in modo sicuro e uniforme.

    - Usa SafeLoader (yaml.safe_load).
    - Path-safety su `base` (fail-closed).
    - Cache opzionale invalidata da mtime/size.
    """
    safe_p = _ensure_within_and_resolve(base, path)
    if not safe_p.exists():
        raise ConfigError("File YAML non trovato", file_path=str(safe_p))

    if use_cache:
        try:
            st = safe_p.stat()
            mtime_ns = int(getattr(st, "st_mtime_ns", int(st.st_mtime * 1e9)))
            size = int(st.st_size)
            cached = _CACHE.get(safe_p)
            if cached and cached[0] == mtime_ns and cached[1] == size:
                return cached[2]
        except Exception:
            # Se la stat fallisce, ignora cache
            pass

    try:
        text = safe_p.read_text(encoding=encoding)
    except Exception as e:
        raise ConfigError(f"Errore lettura file: {e}", file_path=str(safe_p)) from e

    try:
        data = yaml.safe_load(text)
    except Exception as e:
        # YAML malformato
        raise ConfigError(f"YAML malformato: {e}", file_path=str(safe_p)) from e

    if use_cache:
        try:
            st = safe_p.stat()
            mtime_ns = int(getattr(st, "st_mtime_ns", int(st.st_mtime * 1e9)))
            size = int(st.st_size)
            _CACHE[safe_p] = (mtime_ns, size, data)
        except Exception:
            pass

    return data


def clear_yaml_cache() -> None:
    """Svuota la cache interna delle letture YAML."""
    try:
        _CACHE.clear()
    except Exception:
        pass


__all__ = [
    "yaml_read",
    "clear_yaml_cache",
]
