# SPDX-License-Identifier: GPL-3.0-or-later
"""Control-plane tool per generare visionstatement.yaml a partire dal PDF."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

from pipeline.context import ClientContext
from pipeline.exceptions import ConfigError
from pipeline.logging_utils import get_structured_logger
from pipeline.path_utils import ensure_within_and_resolve
from pipeline.vision_paths import vision_yaml_workspace_path
from pipeline.workspace_layout import WorkspaceLayout
from semantic.core import compile_document_to_vision_yaml

from tools.control_plane_env import control_plane_env

LOG = get_structured_logger("tools.tuning_pdf_to_yaml")

DEFAULT_PAYLOAD = {
    "status": "error",
    "mode": "control_plane",
    "slug": "",
    "action": "pdf_to_yaml",
    "errors": [],
    "warnings": [],
    "artifacts": [],
    "returncode": 1,
    "timmy_beta_strict": "0",
}


def _build_payload(*, slug: str) -> Dict[str, Any]:
    payload = dict(DEFAULT_PAYLOAD)
    payload["slug"] = slug
    payload["action"] = "pdf_to_yaml"
    return payload


def _resolve_pdf_path(*, layout: WorkspaceLayout, repo_root: Path, override: Path | None) -> Path:
    if override is not None:
        candidate = ensure_within_and_resolve(repo_root, override)
    else:
        pdf_dir = layout.config_path.parent if layout.config_path else repo_root / "config"
        base_pdf = pdf_dir / "VisionStatement.pdf"
        candidate = ensure_within_and_resolve(repo_root, base_pdf)
    return candidate


def _run_conversion(*, pdf_path: Path, yaml_path: Path) -> Dict[str, Any]:
    compile_document_to_vision_yaml(pdf_path, yaml_path)
    return {
        "status": "ok",
        "warnings": [],
        "errors": [],
        "artifacts": [str(yaml_path)],
        "paths": {"vision_yaml": str(yaml_path)},
    }


def _dump(payload: Dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False))


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Tool control-plane: PDF -> visionstatement.yaml")
    parser.add_argument("--slug", default="dummy", help="Slug cliente (default: dummy)")
    parser.add_argument("--pdf-path", help="Percorso alternativo a VisionStatement.pdf")
    args = parser.parse_args(argv)

    payload = _build_payload(slug=args.slug)
    with control_plane_env(force_non_strict=True):
        try:
            ctx = ClientContext.load(slug=args.slug, require_drive_env=False)
            repo_root = ctx.repo_root_dir
            if repo_root is None:
                raise ConfigError("Repo root non determinato per lo slug", slug=args.slug)
            layout = WorkspaceLayout.from_context(ctx)
            pdf_override = Path(args.pdf_path).expanduser().resolve() if args.pdf_path else None
            pdf_path = _resolve_pdf_path(layout=layout, repo_root=repo_root, override=pdf_override)
            if not pdf_path.exists():
                raise ConfigError(f"PDF non trovato: {pdf_path}", slug=args.slug, file_path=str(pdf_path))
            yaml_path = vision_yaml_workspace_path(repo_root, pdf_path=pdf_path)
            result = _run_conversion(pdf_path=pdf_path, yaml_path=yaml_path)
            payload.update(result)
            payload["returncode"] = 0
            payload["status"] = result.get("status", "ok")
        except Exception as exc:
            LOG.warning("tools.tuning_pdf_to_yaml.failed", extra={"slug": args.slug, "error": str(exc)})
            payload["errors"].append(str(exc))
            payload["status"] = "error"
            payload["returncode"] = 1
        finally:
            _dump(payload)
    return payload["returncode"]


if __name__ == "__main__":
    raise SystemExit(main())
