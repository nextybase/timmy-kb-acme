# src/ui/utils/workspace.py
from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any, Iterator, Optional, Tuple, cast

from pipeline.logging_utils import get_structured_logger
from pipeline.path_utils import ensure_within_and_resolve, validate_slug

# Import opzionale di Streamlit senza type: ignore.
# Se non disponibile, st è un Any con valore None.
try:
    import streamlit as _st  # type: ignore[unused-ignore]  # noqa: F401
except Exception:  # pragma: no cover
    _st = None

st: Any = _st  # st rimane Any; accessi protetti da guardie runtime
_log = get_structured_logger("ui.workspace")


def _load_context_base_dir(slug: str) -> Optional[Path]:
    """Prova a caricare il base_dir dal ClientContext (se disponibile)."""
    try:
        from pipeline.context import ClientContext
    except Exception:
        return None

    try:
        ctx = ClientContext.load(slug=slug, interactive=False, require_env=False, run_id=None)
    except Exception:
        return None

    base_dir = getattr(ctx, "base_dir", None)
    if not base_dir:
        return None
    return Path(base_dir)


def _fallback_base_dir(slug: str) -> Path:
    """Fallback: output/timmy-kb-<slug>, con guardie path-safe."""
    root = Path("output")
    # slug è già normalizzato/validato da resolve_raw_dir; qui non ripetiamo la normalizzazione
    return cast(Path, ensure_within_and_resolve(root, root / f"timmy-kb-{slug}"))


def resolve_raw_dir(slug: str) -> Path:
    """
    Restituisce il path assoluto di raw/ per lo slug dato applicando:
    - normalizzazione e validazione slug (validate_slug)
    - guardie di path-safety (ensure_within_and_resolve)
    """
    slug_value = (slug or "").strip().lower()
    # Conforma lo slug alle policy di progetto (solleva InvalidSlug/ConfigError se non valido)
    validate_slug(slug_value)

    base_dir = _load_context_base_dir(slug_value) or _fallback_base_dir(slug_value)
    # Impedisci traversal/symlink: raw deve stare sotto la base del workspace
    return cast(Path, ensure_within_and_resolve(base_dir, Path(base_dir) / "raw"))


def workspace_root(slug: str) -> Path:
    """
    Restituisce la radice del workspace per lo slug validato.
    Invariante: sempre dentro al perimetro sicuro del cliente.
    """
    raw_dir = resolve_raw_dir(slug)
    return raw_dir.parent


def iter_pdfs_safe(root: Path) -> Iterator[Path]:
    """
    Itera i PDF sotto `root` senza seguire symlink.
    Applica ensure_within_and_resolve a ogni candidato.
    """
    if not root.exists():
        return
    for rw, _dirs, files in os.walk(root, followlinks=False):
        base = Path(rw)
        for name in files:
            if not name.lower().endswith(".pdf"):
                continue
            candidate = base / name
            try:
                # Verifica perimetro per ogni file
                ensure_within_and_resolve(root, candidate)
            except Exception:
                # fuori perimetro o path sospetto: ignora
                continue
            yield candidate


def count_pdfs_safe(root: Path) -> int:
    """Conta i PDF in modo sicuro usando iter_pdfs_safe."""
    return sum(1 for _ in iter_pdfs_safe(root))


def _dir_mtime(p: Path) -> float:
    try:
        return float(p.stat().st_mtime)
    except Exception:  # pragma: no cover
        return 0.0


def has_raw_pdfs(slug: Optional[str]) -> Tuple[bool, Optional[Path]]:
    """
    Verifica se esistono PDF entro raw/ per lo slug dato.
    - TTL cache breve (3s) su risultati POSITIVI (evita caching negativo).
    - Path-safety su ogni file incontrato durante la scansione.
    - In caso di errore I/O/logico, non cache-izza il risultato e registra un warning.
    """
    slug_value = (slug or "").strip().lower()
    if not slug_value:
        return False, None

    # Validazione coerente con resolve_raw_dir (non solleva verso l'UI in questo helper)
    try:
        validate_slug(slug_value)
    except Exception:
        return False, None

    raw_dir = resolve_raw_dir(slug_value)
    if not raw_dir.is_dir():
        return False, raw_dir

    # Cache opzionale in session_state (se Streamlit presente)
    cache_key = f"_raw_has_pdf::{raw_dir}"
    now = time.time()
    ttl_seconds = 3.0  # TTL breve per evitare staleness percettibile in UI
    if st is not None and hasattr(st, "session_state"):
        cached = st.session_state.get(cache_key)
        if isinstance(cached, dict):
            cached_ts = float(cached.get("ts", 0))
            cached_mtime = float(cached.get("mtime", 0))
            current_mtime = _dir_mtime(raw_dir)
            if (now - cached_ts) <= ttl_seconds and abs(cached_mtime - current_mtime) < 1e-6:
                has_pdf_cached = bool(cached.get("has_pdf", False))
                return has_pdf_cached, raw_dir

    # Scansione robusta utilizzando l'helper condiviso
    try:
        # basta verificare l'esistenza del primo elemento
        first = next(iter_pdfs_safe(raw_dir), None)
        has_pdf = first is not None
    except Exception as e:
        # Non scrivere cache negative su errore: segnala e rientra
        try:
            _log.warning("Errore durante la scansione di raw/", extra={"error": str(e), "raw_dir": str(raw_dir)})
        except Exception:
            pass
        return False, raw_dir

    if st is not None and hasattr(st, "session_state"):
        if has_pdf:
            st.session_state[cache_key] = {
                "has_pdf": True,
                "mtime": _dir_mtime(raw_dir),
                "ts": now,
            }
        else:
            # Evita negative-caching: rimuovi eventuale cache precedente
            try:
                if cache_key in st.session_state:
                    del st.session_state[cache_key]
            except Exception:
                pass

    return has_pdf, raw_dir
