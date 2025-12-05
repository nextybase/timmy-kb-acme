#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-3.0-only
"""
Smoke runner end-to-end (headless):

- Carica il contesto locale per uno slug
- (Opzionale) Scarica PDF da Drive in raw/
- Verifica il gating semantico (raw/ contiene PDF validi)
- Esegue la pipeline semantica standard (run_semantic_pipeline)

Questo script NON tocca la UI Streamlit e non modifica il DB knowledge base.
Serve solo come smoke test operativo del flusso:
Drive → RAW → gating Semantica → pipeline semantica.
"""

from __future__ import annotations

import argparse
import os
import sys
import uuid
from pathlib import Path
from typing import Any, Callable

# Aggancia src/ al PYTHONPATH se lanciato da root repo
SRC_ROOT = Path(__file__).resolve().parents[1] / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from pipeline.context import ClientContext  # type: ignore[import]
from pipeline.exceptions import ConfigError, PipelineError, exit_code_for  # type: ignore[import]
from pipeline.logging_utils import get_structured_logger, phase_scope  # type: ignore[import]
from pipeline.observability_config import get_observability_settings  # type: ignore[import]

from semantic.api import run_semantic_pipeline  # type: ignore[import]

from ui.utils import workspace as ws  # type: ignore[import]
from ui.services import drive_runner  # type: ignore[import]


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Smoke: Drive → RAW → Semantica (headless)")
    p.add_argument(
        "--slug",
        required=True,
        help="Slug cliente (es. acme)",
    )
    p.add_argument(
        "--skip-drive",
        action="store_true",
        help="Non eseguire il download da Drive (usa solo RAW locale)",
    )
    p.add_argument(
        "--base-root",
        type=Path,
        default=None,
        help="Root workspaces (default = OUTPUT_DIR_NAME). Solo per debug/sandbox.",
    )
    p.add_argument(
        "--non-interactive",
        action="store_true",
        help="Carica il contesto in modalità non interattiva (come le CLI).",
    )
    return p.parse_args()


def _print_progress(msg: str, **extra: Any) -> None:
    # Callback best-effort usata da drive_runner.*_with_progress
    payload = " ".join(f"{k}={v}" for k, v in extra.items()) if extra else ""
    if payload:
        print(f"[drive] {msg} {payload}")
    else:
        print(f"[drive] {msg}")


def _ensure_raw_from_drive(
    slug: str,
    *,
    base_root: Path | None,
    logger,
) -> None:
    """
    Esegue (best-effort) il download da Drive in raw/ e invalida le cache RAW.
    Se il download fallisce, lascia propagare l'eccezione (il smoke deve fallire).
    """
    # workspace_root è risolto internamente da drive_runner; base_root è opzionale
    drive_runner.download_raw_from_drive_with_progress(
        slug=slug,
        base_root=str(base_root) if base_root is not None else None,
        require_env=False,  # smoke: non vogliamo esplodere per env opzionali
        overwrite=False,
        logger=logger,
        on_progress=_print_progress,
    )

    # Dopo il download, invalida le cache RAW/gating per evitare inconsistenze
    # (es. cache RAW non aggiornata che blocca la Semantica)
    ws.reset_workspace_cache(slug=slug, base_root=base_root)


def _check_semantic_gating(slug: str, *, base_root: Path | None, logger) -> bool:
    """
    Verifica che il gating Semantica sia soddisfatto:
    - workspace esistente
    - presenza di PDF validi in raw/ per lo slug
    """
    # has_raw_pdfs applica già path-safety e cache LRU sui risultati positivi
    raw_ready = ws.has_raw_pdfs(slug=slug)
    if not raw_ready:
        logger.info("ui.gating.sem_hidden", extra={"slug": slug, "raw_ready": False})
        return False
    logger.info("ui.gating.sem_visible", extra={"slug": slug, "raw_ready": True})
    return True


def main() -> int:
    args = _parse_args()
    slug: str = args.slug
    non_interactive: bool = bool(args.non_interactive)
    base_root: Path | None = args.base_root

    run_id = uuid.uuid4().hex
    settings = get_observability_settings()
    logger = get_structured_logger(
        "smoke.semantic_from_drive",
        run_id=run_id,
        level=settings.log_level,
        redact_logs=settings.redact_logs,
        enable_tracing=settings.tracing_enabled,
    )

    env = os.getenv("TIMMY_ENV", "dev")
    logger.info(
        "smoke.semantic_from_drive.started",
        extra={"slug": slug, "env": env, "run_id": run_id},
    )

    # Prepara contesto semantico locale (come semantic_onboarding CLI)
    ctx = ClientContext.load(
        slug=slug,
        interactive=not non_interactive,
        require_env=False,
        run_id=run_id,
    )

    try:
        with phase_scope(logger, stage="smoke.drive_to_raw", customer=slug) as m_drive:
            if not args.skip_drive:
                _ensure_raw_from_drive(slug, base_root=base_root, logger=logger)
            else:
                logger.info("smoke.semantic_from_drive.skip_drive", extra={"slug": slug})
            # Piccolo artefact: segnala almeno 1 come step drive completato
            m_drive.set_artifacts(1)

        with phase_scope(logger, stage="smoke.semantic_gating", customer=slug) as m_gate:
            if not _check_semantic_gating(slug, base_root=base_root, logger=logger):
                # Se il gating fallisce, falliamo con ConfigError (contratto UX: manca RAW)
                raise ConfigError(
                    "Gating Semantica fallito: nessun PDF valido in raw/ per lo slug.",
                    slug=slug,
                )
            m_gate.set_artifacts(1)

        def _wrap(stage_name: str, fn: Callable[[], Any]) -> Any:
            # Stage wrapper leggero per riutilizzare gli stessi event code del CLI
            with phase_scope(logger, stage=f"smoke.{stage_name}", customer=slug) as m:
                result = fn()
                try:
                    # Allineiamo le metriche base con semantic_onboarding
                    if stage_name in {"convert_markdown", "enrich_frontmatter"} and hasattr(
                        result, "__len__"
                    ):
                        m.set_artifacts(len(result))  # type: ignore[arg-type]
                except Exception:
                    m.set_artifacts(None)
                return result

        with phase_scope(logger, stage="smoke.semantic_pipeline", customer=slug) as m_sem:
            base_dir, mds, enriched = run_semantic_pipeline(
                ctx,
                logger,
                slug=slug,
                stage_wrapper=_wrap,
            )
            # artefact complessivo = markdown di contenuto prodotti
            try:
                m_sem.set_artifacts(len(mds))
            except Exception:
                m_sem.set_artifacts(None)

        logger.info(
            "smoke.semantic_from_drive.completed",
            extra={
                "slug": slug,
                "base_dir": str(getattr(ctx, "base_dir", "")),
                "markdown": len(mds),
                "enriched": len(enriched),
            },
        )
        return 0

    except (ConfigError, PipelineError) as exc:
        # Errori "previsti" (config/pipeline) → exit code deterministico
        code = int(exit_code_for(exc))
        logger.error(
            "smoke.semantic_from_drive.failed",
            extra={"slug": slug, "error": str(exc), "exit_code": code},
        )
        return code
    except Exception as exc:  # pragma: no cover - puro smoke best-effort
        logger.exception(
            "smoke.semantic_from_drive.unexpected_error",
            extra={"slug": slug, "error": str(exc)},
        )
        return 99


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130)
