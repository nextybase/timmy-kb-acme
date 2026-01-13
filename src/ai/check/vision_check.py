# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, Optional

import yaml

from ai.vision_config import resolve_vision_config, resolve_vision_retention_days
from pipeline.env_utils import ensure_dotenv_loaded
from pipeline.exceptions import ConfigError
from pipeline.logging_utils import get_structured_logger
from pipeline.path_utils import ensure_within_and_resolve, read_text_safe
from semantic.vision_provision import debug_analyze_vision_sections_from_yaml, provision_from_vision_with_config
from tools.dummy.bootstrap import ensure_dummy_vision_pdf

LOGGER = get_structured_logger("ai.check.vision")


def _load_workspace_config(workspace: Path) -> Dict[str, Any]:
    cfg_path = ensure_within_and_resolve(workspace, workspace / "config" / "config.yaml")
    if not cfg_path.exists():
        raise ConfigError(f"config.yaml non trovato: {cfg_path}", file_path=str(cfg_path))
    text = read_text_safe(cfg_path.parent, cfg_path, encoding="utf-8")
    data = yaml.safe_load(text) or {}
    return data


def _make_ctx(workspace: Path, cfg: Dict[str, Any]) -> Any:
    client_name = (
        cfg.get("client_name")
        or cfg.get("meta", {}).get("client_name")
        or cfg.get("meta", {}).get("client")
        or workspace.name
    )
    return SimpleNamespace(base_dir=workspace, client_name=str(client_name), settings=cfg.get("ai", {}))


def run_vision_dummy_check(
    *,
    workspace_slug: str,
    base_dir: Optional[str] = None,
    verbose: bool = False,
) -> Dict[str, Any]:
    """
    Esegue il flusso Vision in modalità diagnostica su uno workspace esistente.

    Ritorna un dict con percorsi output e configurazione risolta.
    """
    ensure_dotenv_loaded()
    # Root del repo: vision_check.py è in src/ai/check → saliamo di 3 livelli
    repo_root = Path(__file__).resolve().parents[3]
    workspace = Path(base_dir) if base_dir else repo_root / "output" / f"timmy-kb-{workspace_slug}"
    if not workspace.exists():
        raise ConfigError(f"Workspace non trovato: {workspace}", slug=workspace_slug, file_path=str(workspace))

    pdf_path = ensure_dummy_vision_pdf(workspace)

    cfg = _load_workspace_config(workspace)
    ctx = _make_ctx(workspace, cfg)

    resolved = resolve_vision_config(ctx, override_model=None)

    LOGGER.info(
        "ai.check.vision.config",
        extra={
            "slug": workspace_slug,
            "model": resolved.model,
            "use_kb": resolved.use_kb,
            "strict_output": resolved.strict_output,
        },
    )

    retention_days = resolve_vision_retention_days(ctx)
    result = provision_from_vision_with_config(
        ctx=ctx,
        logger=LOGGER,
        slug=workspace_slug,
        pdf_path=pdf_path,
        config=resolved,
        retention_days=retention_days,
        prepared_prompt=None,
    )

    output = {
        "status": "ok",
        "slug": workspace_slug,
        "model": resolved.model,
        "assistant_id": resolved.assistant_id,
        "use_kb": resolved.use_kb,
        "strict_output": resolved.strict_output,
        "mapping_path": result.get("mapping"),
        "cartelle_raw_path": result.get("cartelle_raw"),
    }
    if verbose:
        output["config"] = cfg
    return output


def debug_dummy_vision_sections(
    slug: str = "dummy",
    base_dir: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Carica visionstatement.yaml del dummy e ritorna un report sezioni (diagnostico, no ConfigError).
    """
    repo_root = Path(__file__).resolve().parents[3]
    workspace = Path(base_dir) if base_dir else repo_root / "output" / f"timmy-kb-{slug}"
    yaml_path = workspace / "config" / "visionstatement.yaml"
    vision_text, reports = debug_analyze_vision_sections_from_yaml(yaml_path)
    return {
        "yaml_path": str(yaml_path),
        "text_preview": vision_text[:400],
        "sections": [
            {
                "name": r.name,
                "status": r.status.value,
                "text_preview": (r.text or "")[:200],
            }
            for r in reports
        ],
    }
