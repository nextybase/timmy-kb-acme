# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import logging
import uuid
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Iterator, Optional

from pipeline.logging_utils import get_structured_logger
from pipeline.workspace_layout import WorkspaceLayout
from storage import decision_ledger

_ALLOWED_STEPS = {"vision_enrichment", "prompt_tuning", "pdf_to_yaml_tuning"}
_LOGGER = get_structured_logger("tools.non_strict_step")


def _open_layout(slug: str | None, base_dir: Path | None) -> Optional[WorkspaceLayout]:
    if not slug or base_dir is None:
        return None
    try:
        return WorkspaceLayout.from_workspace(workspace=base_dir, slug=slug)
    except Exception as exc:  # pragma: no cover - best-effort audit
        _LOGGER.debug("non_strict_step.layout_unavailable", extra={"slug": slug, "error": str(exc)})
        return None


def _audit_step(
    *,
    layout: WorkspaceLayout | None,
    slug: str,
    step_name: str,
    status: str,
) -> None:
    if layout is None:
        _LOGGER.info(
            "non_strict_step.no_ledger",
            extra={"slug": slug, "step": step_name, "status": status},
        )
        return
    conn = decision_ledger.open_ledger(layout)
    try:
        decision_ledger.record_event(
            conn,
            event_id=uuid.uuid4().hex,
            slug=slug,
            event_name="non_strict_step",
            actor="non_strict_step",
            occurred_at=datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
            payload={
                "step": step_name,
                "reason_code": step_name,
                "strict_output": False,
                "status": status,
            },
        )
    finally:
        conn.close()


@contextmanager
def non_strict_step(
    step_name: str,
    *,
    logger: logging.Logger,
    slug: str | None = None,
    base_dir: Path | None = None,
) -> Iterator[None]:
    if step_name not in _ALLOWED_STEPS:
        raise RuntimeError(f"step non-strict non autorizzato: {step_name}")
    layout = _open_layout(slug, base_dir)
    logger.info(
        "non_strict_step.start",
        extra={"slug": slug, "step": step_name, "reason_code": step_name, "strict_output": False},
    )
    status = "pass"
    try:
        yield
    except Exception:
        status = "error"
        raise
    finally:
        logger.info(
            "non_strict_step.complete",
            extra={
                "slug": slug,
                "step": step_name,
                "reason_code": step_name,
                "strict_output": False,
                "status": status,
            },
        )
        if slug:
            _audit_step(layout=layout, slug=slug, step_name=step_name, status=status)
