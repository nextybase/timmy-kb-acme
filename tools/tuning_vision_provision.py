# SPDX-License-Identifier: GPL-3.0-or-later
"""Tool control-plane per il provisioning Vision deterministico."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict

from pipeline.context import ClientContext
from pipeline.exceptions import ConfigError
from pipeline.logging_utils import get_structured_logger
from pipeline.path_utils import ensure_within_and_resolve
from pipeline.vision_paths import vision_yaml_workspace_path
from pipeline.workspace_layout import WorkspaceLayout
from ui.config_store import get_vision_model
from ui.fine_tuning.yaml_io import build_prompt_from_yaml, load_workspace_yaml
from ui.services.vision_provision import provision_from_vision_with_config

from tools.control_plane_env import control_plane_env

LOG = get_structured_logger("tools.tuning_vision_provision")

DEFAULT_PAYLOAD: Dict[str, Any] = {
    "status": "error",
    "mode": "control_plane",
    "slug": "",
    "action": "vision_provision",
    "errors": [],
    "warnings": [],
    "artifacts": [],
    "paths": {},
    "returncode": 1,
    "timmy_beta_strict": "0",
}


def _clone_defaults() -> Dict[str, Any]:
    clone: Dict[str, Any] = {}
    for key, value in DEFAULT_PAYLOAD.items():
        if isinstance(value, dict):
            clone[key] = dict(value)
        elif isinstance(value, list):
            clone[key] = list(value)
        else:
            clone[key] = value
    return clone


def _build_payload(*, slug: str) -> Dict[str, Any]:
    payload = _clone_defaults()
    payload["slug"] = slug
    return payload


def _resolve_pdf_path(
    *,
    layout: WorkspaceLayout,
    repo_root: Path,
    override: Path | None,
) -> Path:
    if override is not None:
        candidate = ensure_within_and_resolve(repo_root, override)
    else:
        pdf_dir = layout.config_path.parent if layout.config_path else repo_root / "config"
        base_pdf = pdf_dir / "VisionStatement.pdf"
        candidate = ensure_within_and_resolve(repo_root, base_pdf)
    if not candidate.exists():
        raise ConfigError("VisionStatement.pdf mancante nel workspace.", file_path=str(candidate))
    return candidate


def _extract_mapping_path(result: Dict[str, Any]) -> Path | None:
    if isinstance(result.get("mapping"), str) and result.get("mapping"):
        return Path(result["mapping"])
    parsed = result.get("yaml_paths")
    if isinstance(parsed, dict):
        mapping = parsed.get("mapping")
        if isinstance(mapping, str) and mapping:
            return Path(mapping)
    return None


def _paths_dict(pdf: Path, yaml_path: Path, mapping: Path | None) -> Dict[str, str]:
    paths: Dict[str, str] = {
        "pdf": str(pdf),
        "vision_yaml": str(yaml_path),
    }
    if mapping is not None:
        paths["mapping"] = str(mapping)
    return paths


def _dump(payload: Dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False))
    sys.stdout.write("\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Control-plane tool: provisioning Vision")
    parser.add_argument("--slug", default="dummy", help="Slug cliente (default: dummy)")
    parser.add_argument("--repo-root", help="Override esplicito della root workspace canonical")
    parser.add_argument("--pdf-path", help="Override della VisionStatement.pdf (per test/diagnostica)")
    parser.add_argument(
        "--model",
        help="Modello Vision (default da config globale UI)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Forza l'esecuzione anche se hash invariato",
    )
    args = parser.parse_args(argv)

    payload = _build_payload(slug=args.slug)
    repo_override = Path(args.repo_root).expanduser().resolve() if args.repo_root else None
    try:
        with control_plane_env(force_non_strict=True):
            ctx = ClientContext.load(
                slug=args.slug,
                require_drive_env=False,
                repo_root_dir=repo_override,
            )
            repo_root = ctx.repo_root_dir
            if repo_root is None:
                raise ConfigError("Repo root non determinato per lo slug.", slug=args.slug)
            layout = WorkspaceLayout.from_context(ctx)
            pdf_override = Path(args.pdf_path).expanduser().resolve() if args.pdf_path else None
            pdf_path = _resolve_pdf_path(layout=layout, repo_root=repo_root, override=pdf_override)
            yaml_path = vision_yaml_workspace_path(repo_root, pdf_path=pdf_path)
            data = load_workspace_yaml(args.slug)
            client_name = getattr(ctx, "client_name", None)
            prompt = build_prompt_from_yaml(
                data,
                slug=args.slug,
                client_name=client_name,
            )
            model = args.model or get_vision_model()
            result = provision_from_vision_with_config(
                ctx,
                LOG,
                slug=args.slug,
                pdf_path=pdf_path,
                force=args.force,
                model=model,
                prepared_prompt=prompt,
            )
            mapping_path = _extract_mapping_path(result)
            payload.update(result)
            payload.setdefault("artifacts", [])
            if mapping_path:
                payload["artifacts"].append(str(mapping_path))
            payload["paths"] = _paths_dict(pdf_path, yaml_path, mapping_path)
            if mapping_path:
                payload["mapping"] = str(mapping_path)
            payload["status"] = result.get("status", "ok")
            payload["returncode"] = 0
    except Exception as exc:  # pragma: no cover - guardrail
        LOG.warning(
            "tools.tuning_vision_provision.failed",
            extra={"slug": args.slug, "error": str(exc)},
        )
        payload["errors"].append(str(exc))
        payload["status"] = "error"
        payload["returncode"] = 1
        mapping_path = None
        payload["paths"] = {}
    finally:
        _dump(payload)
    return payload["returncode"]


if __name__ == "__main__":
    raise SystemExit(main())
