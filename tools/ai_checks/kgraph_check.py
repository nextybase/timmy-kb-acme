# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from ai.kgraph import invoke_kgraph_messages
from kg_models import TagKnowledgeGraph
from pipeline.exceptions import ConfigError
from pipeline.logging_utils import get_structured_logger
from pipeline.env_constants import WORKSPACE_ROOT_ENV
from pipeline.env_utils import get_env_var

LOGGER = get_structured_logger("ai.check.kgraph")


def _resolve_kgraph_workspace(workspace_slug: str, base_dir: Optional[str]) -> Path:
    expected = f"timmy-kb-{workspace_slug}"
    if base_dir:
        candidate = Path(base_dir).expanduser().resolve()
    else:
        try:
            raw = get_env_var(WORKSPACE_ROOT_ENV, required=True)
        except ConfigError as exc:
            raise ConfigError(
                f"{WORKSPACE_ROOT_ENV} obbligatorio: {exc}",
                slug=workspace_slug,
                code="workspace.root.invalid",
                component="ai.check.kgraph",
            ) from exc
        if "<slug>" in raw:
            raw = raw.replace("<slug>", workspace_slug)
        try:
            candidate = Path(raw).expanduser().resolve()
        except Exception as exc:
            raise ConfigError(
                f"{WORKSPACE_ROOT_ENV} non valido: {raw}",
                slug=workspace_slug,
                code="workspace.root.invalid",
                component="ai.check.kgraph",
            ) from exc
    if candidate.name != expected:
        raise ConfigError(
            f"La workspace root deve terminare con '{expected}' (trovato {candidate})",
            slug=workspace_slug,
            code="workspace.root.invalid",
            component="ai.check.kgraph",
        )
    return candidate


def run_kgraph_dummy_check(
    *,
    workspace_slug: str,
    base_dir: Optional[str] = None,
    verbose: bool = False,
) -> Dict[str, Any]:
    """
    Esegue il flusso KGraph in modalità diagnostica su uno workspace.
    """
    workspace = _resolve_kgraph_workspace(workspace_slug, base_dir)
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

    from timmy_kb.cli.kg_builder import _prepare_input

    payload = _prepare_input(workspace_slug, semantic_dir)

    LOGGER.info("ai.check.kgraph.prepare", extra={"slug": workspace_slug, "tags": len(payload.tags)})

    kg_dict = invoke_kgraph_messages(payload.to_messages(), settings=None, assistant_env=None, redact_logs=not verbose)
    kg = TagKnowledgeGraph.from_dict(kg_dict) if verbose else None  # optional detailed graph

    summary = {
        "status": "ok",
        "slug": workspace_slug,
        "tags_count": len(kg_dict.get("tags") or []),
        "relations_count": len(kg_dict.get("relations") or []),
    }
    if verbose and kg:
        summary["kg"] = kg
    return summary
