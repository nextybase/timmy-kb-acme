# SPDX-License-Identifier: GPL-3.0-only
# src/ui/utils/workspace.py
from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any, Iterator, Optional, Tuple

from pipeline.exceptions import ConfigError
from pipeline.logging_utils import get_structured_logger, tail_path
from pipeline.path_utils import clear_iter_safe_pdfs_cache, iter_safe_pdfs, validate_slug
from pipeline.workspace_layout import WorkspaceLayout
from semantic.tags_validator import load_yaml as _load_tags_yaml
from semantic.tags_validator import validate_tags_reviewed as _validate_tags_reviewed
from storage.tags_store import load_tags_reviewed as _load_tags_reviewed
from ui.utils.config import get_tags_env_config
from ui.utils.context_cache import get_client_context, invalidate_client_context

# Import opzionale di Streamlit senza type: ignore.
# Se non disponibile, st è un Any con valore None.
try:
    import streamlit as _st  # type: ignore[unused-ignore]  # noqa: F401
except Exception:  # pragma: no cover
    _st = None

st: Any = _st  # st rimane Any; accessi protetti da guardie runtime
_log = get_structured_logger("ui.workspace")
_LAYOUT_CACHE: dict[str, WorkspaceLayout] = {}
_UI_RAW_CACHE_TTL = 3.0  # secondi, garantisce feedback rapido in UI


def _log_workspace_failure(event: str, exc: Exception, *, extra: dict[str, object] | None = None) -> None:
    payload = {"error": repr(exc)}
    if extra:
        payload.update(extra)
    try:
        _log.warning(event, extra=payload)
    except Exception:
        logging.getLogger("ui.workspace").warning("%s error=%r", event, exc)


def _load_context_layout(slug: str) -> Optional[WorkspaceLayout]:
    """Carica il layout dal ClientContext in modo fail-fast."""
    slug_key = (slug or "").strip().lower()
    if not slug_key:
        return None
    cached = _LAYOUT_CACHE.get(slug_key)
    if cached:
        return cached
    ctx = get_client_context(slug_key, require_env=False)
    layout = WorkspaceLayout.from_context(ctx)
    _LAYOUT_CACHE[slug_key] = layout
    return layout


def get_ui_workspace_layout(slug: str, *, require_env: bool = True) -> WorkspaceLayout:
    """Helper compat per le UI: restituisce sempre il layout canonico per lo slug dato."""
    slug_value = (slug or "").strip().lower()
    validate_slug(slug_value)

    cached = _LAYOUT_CACHE.get(slug_value)
    if cached:
        return cached

    layout = _load_context_layout(slug_value)
    if layout is None:
        raise ConfigError("Slug mancante: impossibile risolvere il layout.", slug=slug_value)
    _LAYOUT_CACHE[slug_value] = layout
    return layout


def resolve_raw_dir(_slug: str) -> Path:
    """
    Compat helper legacy: non è più consentito ricavare manualmente il raw dir.
    """
    raise ConfigError(
        "DEPRECATO: `resolve_raw_dir` è stato disabilitato. Risolvi il workspace via WorkspaceLayout "
        "e, se serve creato o riparato, chiama pipeline.workspace_bootstrap.bootstrap_client_workspace, "
        "bootstrap_dummy_workspace o migrate_or_repair_workspace.",
    )


def clear_base_cache(*, slug: str | None = None) -> None:
    """Svuota la cache dei layout quando cambia il perimetro (es. REPO_ROOT_DIR)."""
    if slug:
        _LAYOUT_CACHE.pop(slug.strip().lower(), None)
    else:
        _LAYOUT_CACHE.clear()
    clear_iter_safe_pdfs_cache()
    invalidate_client_context(slug)


def workspace_root(_slug: str) -> Path:
    """
    Compat helper legacy: non è più consentito derivare manualmente la root.
    """
    raise ConfigError(
        "DEPRECATO: `workspace_root` è stato disabilitato. Risolvi il workspace tramite WorkspaceLayout "
        "e lancia la logica di bootstrap/migrazione (`pipeline.workspace_bootstrap.*`).",
    )


def iter_pdfs_safe(root: Path, *, use_cache: bool = False, cache_ttl_s: float | None = None) -> Iterator[Path]:
    """
    Itera i PDF sotto `root` senza seguire symlink.
    Applica ensure_within_and_resolve a ogni candidato.
    """
    yield from iter_safe_pdfs(root, use_cache=use_cache, cache_ttl_s=cache_ttl_s)


def count_pdfs_safe(root: Path, *, use_cache: bool = False, cache_ttl_s: float | None = None) -> int:
    """Conta i PDF in modo sicuro usando iter_pdfs_safe."""
    return sum(1 for _ in iter_pdfs_safe(root, use_cache=use_cache, cache_ttl_s=cache_ttl_s))


def _dir_mtime(p: Path) -> float:
    try:
        return float(p.stat().st_mtime)
    except Exception:  # pragma: no cover
        return 0.0


def has_raw_pdfs(slug: Optional[str], *, strict: bool = False) -> Tuple[bool, Optional[Path]]:
    """
    Verifica se esistono PDF entro raw/ per lo slug dato.
    - TTL cache breve (3s) su risultati POSITIVI (evita caching negativo).
    - Path-safety su ogni file incontrato durante la scansione.
    - In caso di errore I/O/logico, non cache-izza il risultato e registra un warning.
    """
    slug_value = (slug or "").strip().lower()
    if not slug_value:
        return False, None

    validate_slug(slug_value)

    raw_dir = get_ui_workspace_layout(slug_value, require_env=False).raw_dir
    if not raw_dir.is_dir():
        return False, raw_dir

    # Cache opzionale in session_state (se Streamlit presente)
    cache_key = f"_raw_has_pdf::{raw_dir}"
    now = time.time()
    ttl_seconds = 3.0  # TTL breve per evitare staleness percettibile in UI
    current_mtime: float | None = None
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
        first = next(iter_pdfs_safe(raw_dir, use_cache=True, cache_ttl_s=_UI_RAW_CACHE_TTL), None)
        has_pdf = first is not None
    except Exception as e:
        if strict:
            raise
        # Non scrivere cache negative su errore: segnala e rientra
        try:
            _log.warning(
                "ui.workspace.scan_raw_failed",
                extra={"error": str(e), "raw_dir": tail_path(raw_dir)},
            )
        except Exception:
            pass
        return False, raw_dir

    if st is not None and hasattr(st, "session_state"):
        if has_pdf:
            if current_mtime is None:
                current_mtime = _dir_mtime(raw_dir)
            st.session_state[cache_key] = {
                "has_pdf": True,
                "mtime": current_mtime,
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


def raw_ready(slug: Optional[str], *, strict: bool = False) -> tuple[bool, Optional[Path]]:
    """
    Predicate canonico per raw_ready: richiede layout/config validi e almeno un PDF in raw/.
    Ritorna (ready, raw_dir) per logging/gating.
    """
    slug_value = (slug or "").strip().lower()
    if not slug_value:
        # NOT_APPLICABLE: niente slug => niente gating su raw
        return True, None
    try:
        layout = get_ui_workspace_layout(slug_value, require_env=False)
    except Exception as exc:
        if strict:
            raise
        # Drastico ma non bug-friendly:
        # - se il layout non si può risolvere perché manca il contesto/slug, non bloccare la UI
        # - per errori reali (config/permessi/altro), non dichiarare ready
        if isinstance(exc, ConfigError):
            return True, None
        return False, None

    # Vision gating: raw/ non è semanticamente rilevante finché la Vision non è completata
    vision_hash = layout.semantic_dir / ".vision_hash"
    if not vision_hash.exists():
        # NOT_APPLICABLE: evita warning e check prematuri su raw/
        return True, None

    ready, raw_dir = has_raw_pdfs(slug_value, strict=strict)
    # `has_raw_pdfs` giù verifica slug/layout; il controllo su config/layout è quindi implicito.
    if not ready:
        return False, raw_dir or layout.raw_dir
    return True, raw_dir or layout.raw_dir


def tagging_ready(slug: Optional[str], *, strict: bool = False) -> tuple[bool, Optional[Path]]:
    """
    Predicate canonico per tagging_ready:
    - richiede raw_ready
    - richiede semantic/tags.db presente
    - richiede semantic/tags_reviewed.yaml presente e non vuoto
    Ritorna (ready, semantic_dir) per logging/gating.
    """
    if get_tags_env_config().is_stub:
        return False, None
    raw_ok, raw_dir = raw_ready(slug, strict=strict)
    if not raw_ok:
        return False, raw_dir
    try:
        layout = get_ui_workspace_layout(slug or "", require_env=False)
    except Exception as exc:
        if strict:
            raise
        _log_workspace_failure(
            "ui.workspace.tagging_ready_failed",
            exc,
            extra={"slug": slug or "", "stage": "layout", "strict": bool(strict)},
        )
        return False, None
    semantic_dir = layout.semantic_dir
    tags_db = layout.tags_db or (semantic_dir / "tags.db")
    tags_yaml = semantic_dir / "tags_reviewed.yaml"
    try:
        db_ok = tags_db.exists()
        yaml_ok = tags_yaml.exists() and tags_yaml.stat().st_size > 0
    except Exception as exc:
        if strict:
            raise
        _log_workspace_failure(
            "ui.workspace.tagging_ready_failed",
            exc,
            extra={"slug": slug or "", "stage": "io", "strict": bool(strict)},
        )
        return False, semantic_dir
    if not (db_ok and yaml_ok):
        return False, semantic_dir
    if not _tags_db_has_terms(tags_db, strict=strict, slug=slug):
        return False, semantic_dir
    if not _tags_yaml_has_terms(tags_yaml, strict=strict, slug=slug):
        return False, semantic_dir
    return True, semantic_dir


def _tags_db_has_terms(db_path: Path, *, strict: bool = False, slug: Optional[str] = None) -> bool:
    try:
        data = _load_tags_reviewed(str(db_path))
    except Exception as exc:
        if strict:
            raise
        _log_workspace_failure(
            "ui.workspace.tags_db_read_failed",
            exc,
            extra={"slug": slug or "", "path": str(db_path)},
        )
        return False
    tags = data.get("tags") if isinstance(data, dict) else None
    if not isinstance(tags, list):
        return False
    for item in tags:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        action = str(item.get("action") or "").strip().lower()
        if name and action == "keep":
            return True
    return False


def _tags_yaml_has_terms(yaml_path: Path, *, strict: bool = False, slug: Optional[str] = None) -> bool:
    try:
        data = _load_tags_yaml(yaml_path)
    except Exception as exc:
        if strict:
            raise
        _log_workspace_failure(
            "ui.workspace.tags_yaml_read_failed",
            exc,
            extra={"slug": slug or "", "path": str(yaml_path)},
        )
        return False
    result = _validate_tags_reviewed(data)
    if result.get("errors"):
        return False
    tags = data.get("tags") if isinstance(data, dict) else None
    if not isinstance(tags, list):
        return False
    return any(isinstance(item, dict) and str(item.get("name") or "").strip() for item in tags)
