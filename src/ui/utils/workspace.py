# SPDX-License-Identifier: GPL-3.0-or-later
# src/ui/utils/workspace.py
from __future__ import annotations

import logging
import sys
import time
from pathlib import Path
from typing import Any, Iterator, Optional, Tuple

from pipeline.exceptions import ConfigError
from pipeline.logging_utils import get_structured_logger, tail_path
from pipeline.path_utils import clear_iter_safe_pdfs_cache, iter_safe_paths, iter_safe_pdfs, validate_slug
from pipeline.workspace_layout import WorkspaceLayout
from semantic.tags_validator import load_yaml as _load_tags_yaml
from semantic.tags_validator import validate_tags_reviewed as _validate_tags_reviewed
from storage.tags_store import load_tags_reviewed as _load_tags_reviewed
from ui.utils.config import get_tags_env_config
from ui.utils.context_cache import get_client_context, invalidate_client_context

_log = get_structured_logger("ui.workspace")
_LAYOUT_CACHE: dict[str, WorkspaceLayout] = {}
_UI_RAW_CACHE_TTL = 3.0  # secondi, garantisce feedback rapido in UI


def _get_streamlit_session_state() -> Any | None:
    if "streamlit" not in sys.modules:
        return None
    from ui.utils.stubs import get_streamlit

    st_module = get_streamlit()
    return getattr(st_module, "session_state", None)


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
    ctx = get_client_context(slug_key, require_drive_env=False)
    layout = WorkspaceLayout.from_context(ctx)
    _LAYOUT_CACHE[slug_key] = layout
    return layout


def get_ui_workspace_layout(slug: str, *, require_drive_env: bool = False) -> WorkspaceLayout:
    """Helper UI: restituisce sempre il layout canonico per lo slug dato."""
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
    Helper UI: non è più consentito ricavare manualmente il raw dir.
    """
    raise ConfigError(
        "DEPRECATO: `resolve_raw_dir` è stato disabilitato. Risolvi il workspace via WorkspaceLayout "
        "e, se serve, chiama pipeline.workspace_bootstrap.bootstrap_client_workspace o "
        "bootstrap_dummy_workspace.",
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
    Helper UI: non è più consentito derivare manualmente la root.
    """
    raise ConfigError(
        "DEPRECATO: `workspace_root` è stato disabilitato. Risolvi il workspace tramite WorkspaceLayout "
        "e lancia la logica di bootstrap (`pipeline.workspace_bootstrap.*`).",
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


def iter_markdown_safe(root: Path) -> Iterator[Path]:
    """Itera i Markdown sotto `root` senza seguire symlink."""
    yield from iter_safe_paths(root, include_dirs=False, include_files=True, suffixes=(".md",))


def count_markdown_safe(root: Path) -> int:
    """Conta i Markdown in modo sicuro usando iter_markdown_safe."""
    return sum(1 for _ in iter_markdown_safe(root))


def _dir_mtime(p: Path) -> float:
    try:
        return float(p.stat().st_mtime)
    except Exception:  # pragma: no cover
        return 0.0


def has_normalized_markdown(slug: Optional[str], *, strict: bool = False) -> Tuple[bool, Optional[Path]]:
    """
    Verifica se esistono Markdown entro normalized/ per lo slug dato.
    - TTL cache breve (3s) su risultati POSITIVI (evita caching negativo).
    - Path-safety su ogni file incontrato durante la scansione.
    - In caso di errore I/O/logico, non cache-izza il risultato e registra un warning.
    """
    slug_value = (slug or "").strip().lower()
    if not slug_value:
        return False, None

    validate_slug(slug_value)

    normalized_dir = get_ui_workspace_layout(slug_value, require_drive_env=False).normalized_dir
    if not normalized_dir.is_dir():
        return False, normalized_dir

    # Cache opzionale in session_state (se Streamlit presente)
    cache_key = f"_normalized_has_md::{normalized_dir}"
    now = time.time()
    ttl_seconds = 3.0  # TTL breve per evitare staleness percettibile in UI
    current_mtime: float | None = None
    session_state = _get_streamlit_session_state()
    if session_state is not None:
        cached = session_state.get(cache_key)
        if isinstance(cached, dict):
            cached_ts = float(cached.get("ts", 0))
            cached_mtime = float(cached.get("mtime", 0))
            current_mtime = _dir_mtime(normalized_dir)
            if (now - cached_ts) <= ttl_seconds and abs(cached_mtime - current_mtime) < 1e-6:
                has_pdf_cached = bool(cached.get("has_pdf", False))
                return has_pdf_cached, normalized_dir

    # Scansione robusta utilizzando l'helper condiviso
    try:
        # basta verificare l'esistenza del primo elemento
        first = next(iter_markdown_safe(normalized_dir), None)
        has_pdf = first is not None
    except Exception as e:
        if strict:
            raise
        # Non scrivere cache negative su errore: segnala e rientra
        try:
            _log.warning(
                "ui.workspace.scan_normalized_failed",
                extra={"error": str(e), "normalized_dir": tail_path(normalized_dir)},
            )
        except Exception:
            pass
        return False, normalized_dir

    if session_state is not None:
        if has_pdf:
            if current_mtime is None:
                current_mtime = _dir_mtime(normalized_dir)
            session_state[cache_key] = {
                "has_pdf": True,
                "mtime": current_mtime,
                "ts": now,
            }
        else:
            # Evita negative-caching: rimuovi eventuale cache precedente
            try:
                if cache_key in session_state:
                    del session_state[cache_key]
            except Exception:
                pass

    return has_pdf, normalized_dir


def normalized_ready(slug: Optional[str], *, strict: bool = False) -> tuple[bool, Optional[Path]]:
    """
    Predicate canonico per normalized_ready: richiede layout/config validi e almeno un Markdown in normalized/.
    Ritorna (ready, normalized_dir) per logging/gating.
    """
    slug_value = (slug or "").strip().lower()
    if not slug_value:
        # NOT_APPLICABLE: niente slug => niente gating su normalized
        return True, None
    try:
        layout = get_ui_workspace_layout(slug_value, require_drive_env=False)
    except Exception as exc:
        if strict:
            if isinstance(exc, ConfigError):
                return True, None
            if slug_value == "dummy":
                return False, None
            raise
        # Drastico ma non bug-friendly:
        # - se il layout non si pu? risolvere perch? manca il contesto/slug, non bloccare la UI
        # - per errori reali (config/permessi/altro), non dichiarare ready
        if isinstance(exc, ConfigError):
            return True, None
        return False, None

    # Vision gating: normalized/ non ? semanticamente rilevante finch? la Vision non ? completata
    vision_hash = layout.semantic_dir / ".vision_hash"
    if not vision_hash.exists():
        # NOT_APPLICABLE: evita warning e check prematuri su normalized/
        return True, None

    ready, normalized_dir = has_normalized_markdown(slug_value, strict=strict)
    # `has_normalized_markdown` gi? verifica slug/layout; il controllo su config/layout ? quindi implicito.
    if not ready:
        return False, normalized_dir or layout.normalized_dir
    return True, normalized_dir or layout.normalized_dir


def tagging_ready(slug: Optional[str], *, strict: bool = False) -> tuple[bool, Optional[Path]]:
    """
    Predicate canonico per tagging_ready:
    - richiede normalized_ready
    - richiede semantic/tags.db presente
    - richiede semantic/tags_reviewed.yaml presente e non vuoto
    Ritorna (ready, semantic_dir) per logging/gating.
    """
    if get_tags_env_config().is_stub:
        return False, None
    normalized_ok, normalized_dir = normalized_ready(slug, strict=strict)
    if not normalized_ok:
        return False, normalized_dir
    try:
        layout = get_ui_workspace_layout(slug or "", require_drive_env=False)
    except Exception as exc:
        if strict:
            if isinstance(exc, ConfigError):
                return False, None
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
