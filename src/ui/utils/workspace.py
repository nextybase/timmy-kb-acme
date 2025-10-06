# src/ui/utils/workspace.py
from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any, Optional, Tuple, cast

from pipeline.path_utils import ensure_within_and_resolve

# Import opzionale di Streamlit senza type: ignore.
# Se non disponibile, st è un Any con valore None.
try:
    import streamlit as _st  # type: ignore[unused-ignore]  # noqa: F401
except Exception:  # pragma: no cover
    _st = None

st: Any = _st  # st rimane Any; accessi protetti da guardie runtime


def _load_context_base_dir(slug: str) -> Optional[Path]:
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
    # Usa output/timmy-kb-<slug> ma con guardie path-safe
    root = Path("output")
    # slug è già normalizzato da resolve_raw_dir; qui non ripetiamo la normalizzazione
    return cast(Path, ensure_within_and_resolve(root, root / f"timmy-kb-{slug}"))


def resolve_raw_dir(slug: str) -> Path:
    slug_value = slug.strip().lower()
    if not slug_value:
        raise ValueError("Slug must be a non-empty string")
    base_dir = _load_context_base_dir(slug_value) or _fallback_base_dir(slug_value)
    # Impedisci traversal/symlink: raw deve stare sotto la base del workspace
    return cast(Path, ensure_within_and_resolve(base_dir, Path(base_dir) / "raw"))


def _dir_mtime(p: Path) -> float:
    try:
        return float(p.stat().st_mtime)
    except Exception:  # pragma: no cover
        return 0.0


def has_raw_pdfs(slug: Optional[str]) -> Tuple[bool, Optional[Path]]:
    slug_value = (slug or "").strip().lower()
    if not slug_value:
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

    # Scansione robusta: evita rglob (può seguire symlink) e valida ogni path
    has_pdf = False
    try:
        for root, _dirs, files in os.walk(raw_dir, followlinks=False):
            for name in files:
                if not name.lower().endswith(".pdf"):
                    continue
                candidate = Path(root) / name
                try:
                    ensure_within_and_resolve(raw_dir, candidate)
                except Exception:
                    # fuori perimetro o path sospetto: ignora
                    continue
                has_pdf = True
                break
            if has_pdf:
                break
    except Exception:
        return False, raw_dir

    if st is not None and hasattr(st, "session_state"):
        st.session_state[cache_key] = {
            "has_pdf": has_pdf,
            "mtime": _dir_mtime(raw_dir),
            "ts": now,
        }

    return has_pdf, raw_dir
