# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

from pipeline.exceptions import ConfigError, PipelineError
from pipeline.logging_utils import get_structured_logger
from pipeline.path_utils import ensure_within_and_resolve
from pipeline.yaml_utils import clear_yaml_cache
from semantic.api import build_tags_csv
from semantic.tags_io import write_tagging_readme, write_tags_review_stub_from_csv
from storage import decision_ledger
from ui.utils.context_cache import get_client_context
from ui.utils.workspace import get_ui_workspace_layout

if TYPE_CHECKING:  # pragma: no cover
    from pipeline.context import ClientContext
else:  # pragma: no cover
    from typing import Any

    ClientContext = Any  # type: ignore[misc]

try:
    import streamlit as st
except Exception:  # pragma: no cover
    st = None


def _require_streamlit() -> None:
    if st is None:
        raise ConfigError("Streamlit non disponibile per l'adapter Estrai Tags.")


def _resolve_paths(ctx: ClientContext, slug: str) -> tuple[Path, Path, Path]:
    layout = get_ui_workspace_layout(slug, require_drive_env=False)
    repo_root_dir = layout.repo_root_dir
    if repo_root_dir is None:
        raise ConfigError(
            "Layout workspace invalido: non riuscito a determinare repo_root_dir dal layout.",
            slug=slug,
        )

    normalized_dir = layout.normalized_dir
    semantic_dir = layout.semantic_dir

    normalized_path = ensure_within_and_resolve(repo_root_dir, Path(normalized_dir))
    normalized_path.mkdir(parents=True, exist_ok=True)
    semantic_path = ensure_within_and_resolve(repo_root_dir, Path(semantic_dir))
    semantic_path.mkdir(parents=True, exist_ok=True)

    return repo_root_dir, normalized_path, semantic_path


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _rel(repo_root: Path, p: Path) -> str:
    try:
        return str(p.resolve().relative_to(repo_root.resolve()))
    except Exception:
        return str(p)


def run_tags_update(slug: str, logger: Optional[logging.Logger] = None) -> None:
    """Genera/aggiorna tags_reviewed in-process mostrando l'avanzamento nella UI."""
    _require_streamlit()
    svc_logger = logger or get_structured_logger("ui.services.tags_adapter")
    conn: Any | None = None

    try:
        with st.spinner("Preparazione contesto..."):
            ctx = get_client_context(slug, require_drive_env=False)
            repo_root, _normalized_dir, semantic_dir = _resolve_paths(ctx, slug)

        # Audit trail canonico (ledger events)
        layout = get_ui_workspace_layout(slug, require_drive_env=False)
        conn = decision_ledger.open_ledger(layout)
        decision_ledger.record_event(
            conn,
            event_id=uuid.uuid4().hex,
            run_id=None,
            slug=slug,
            event_name="ui.tags_update.started",
            actor="ui.services.tags_adapter",
            occurred_at=_utc_now_iso(),
            payload={
                "backend": (os.getenv("TAGS_NLP_BACKEND", "spacy").strip().lower() or "spacy"),
                "semantic_dir": _rel(repo_root, semantic_dir),
                "normalized_dir": _rel(repo_root, _normalized_dir),
            },
        )

        with st.spinner("Generazione tags_raw.csv (SpaCy/euristica)..."):
            csv_path = build_tags_csv(ctx, svc_logger, slug=slug)
            write_tagging_readme(semantic_dir, svc_logger)
            write_tags_review_stub_from_csv(semantic_dir, csv_path, svc_logger)

        # Niente scrittura automatica dello YAML: l'utente pubblica esplicitamente dalla UI.
        clear_yaml_cache()
        st.success("Estrai Tags completato (SpaCy/euristica). Usa 'Pubblica tag revisionati' per generare lo YAML.")
        backend = os.getenv("TAGS_NLP_BACKEND", "spacy").strip().lower() or "spacy"
        entities_written = getattr(ctx, "last_entities_written", None)

        # Audit trail: completed
        stub_db = semantic_dir / "tags.db"
        readme = semantic_dir / "README.md"
        decision_ledger.record_event(
            conn,
            event_id=uuid.uuid4().hex,
            run_id=None,
            slug=slug,
            event_name="ui.tags_update.completed",
            actor="ui.services.tags_adapter",
            occurred_at=_utc_now_iso(),
            payload={
                "backend": backend,
                "entities_written": entities_written,
                "artifacts": {
                    "tags_raw_csv": _rel(repo_root, Path(csv_path)),
                    "stub_db": _rel(repo_root, stub_db) if stub_db.exists() else None,
                    "tagging_readme": _rel(repo_root, readme) if readme.exists() else None,
                    "tags_reviewed_yaml": _rel(repo_root, semantic_dir / "tags_reviewed.yaml"),
                },
                "note": "yaml_not_written_automatically",
            },
        )
        svc_logger.info(
            "ui.tags_adapter.completed",
            extra={
                "slug": slug,
                "yaml": str(semantic_dir / "tags_reviewed.yaml"),
                "source": backend,
                "entities_written": entities_written,
            },
        )
    except (ConfigError, PipelineError) as exc:
        message = str(exc)
        st.error(f"Estrazione tag non riuscita: {message}")
        try:
            # Best effort: se conn/layout non disponibili, evitiamo cascade failure in UI
            layout = get_ui_workspace_layout(slug, require_drive_env=False)
            conn = decision_ledger.open_ledger(layout)
            decision_ledger.record_event(
                conn,
                event_id=uuid.uuid4().hex,
                run_id=None,
                slug=slug,
                event_name="ui.tags_update.failed",
                actor="ui.services.tags_adapter",
                occurred_at=_utc_now_iso(),
                payload={
                    "error_class": type(exc).__name__,
                    "error_code": getattr(exc, "code", None),
                    "component": getattr(exc, "component", None),
                },
            )
        except Exception:
            pass
        svc_logger.error("ui.tags_adapter.failed", extra={"slug": slug, "error": message})
    except Exception:  # pragma: no cover
        st.error("Errore inatteso durante l'estrazione dei tag. Consulta i log.")
        try:
            layout = get_ui_workspace_layout(slug, require_drive_env=False)
            conn = decision_ledger.open_ledger(layout)
            decision_ledger.record_event(
                conn,
                event_id=uuid.uuid4().hex,
                run_id=None,
                slug=slug,
                event_name="ui.tags_update.failed",
                actor="ui.services.tags_adapter",
                occurred_at=_utc_now_iso(),
                payload={"error_class": "UnexpectedError"},
            )
        except Exception:
            pass
        svc_logger.exception("ui.tags_adapter.failed", extra={"slug": slug})
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
