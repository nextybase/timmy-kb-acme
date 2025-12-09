# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, Optional

from ai.kgraph import invoke_kgraph_messages
from pipeline.exceptions import ConfigError

LOGGER = logging.getLogger("ai.check.kgraph")


def run_kgraph_dummy_check(
    *,
    workspace_slug: str,
    base_dir: Optional[str] = None,
    verbose: bool = False,
) -> Dict[str, Any]:
    """
    Esegue il flusso KGraph in modalità diagnostica su uno workspace.
    """
    repo_root = Path(__file__).resolve().parents[3]
    workspace = Path(base_dir) if base_dir else repo_root / f"output/timmy-kb-{workspace_slug}"
    if not workspace.exists():
        raise ConfigError(f"Workspace inesistente: {workspace}", slug=workspace_slug, file_path=str(workspace))

    semantic_dir = workspace / "semantic"
    tags_raw_path = semantic_dir / "tags_raw.json"
    if not tags_raw_path.exists():
        raise ConfigError(
            "tags_raw.json mancante; esegui prima il tagging semantico.",
            slug=workspace_slug,
            file_path=str(tags_raw_path),
        )

    from kg_builder import _prepare_input, call_openai_tag_kg_assistant

    payload = _prepare_input(workspace_slug, semantic_dir)

    LOGGER.info("ai.check.kgraph.prepare", extra={"slug": workspace_slug, "tags": len(payload.tags)})

    kg_dict = invoke_kgraph_messages(payload.to_messages(), settings=None, assistant_env=None, redact_logs=not verbose)
    kg = call_openai_tag_kg_assistant(payload) if not verbose else None  # optional detailed graph

    summary = {
        "status": "ok",
        "slug": workspace_slug,
        "tags_count": len(kg_dict.get("tags") or []),
        "relations_count": len(kg_dict.get("relations") or []),
    }
    if verbose and kg:
        summary["kg"] = kg
    return summary
