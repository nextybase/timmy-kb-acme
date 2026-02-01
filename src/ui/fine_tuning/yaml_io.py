# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from pipeline.file_utils import safe_write_text
from pipeline.path_utils import read_text_safe
from pipeline.vision_paths import vision_yaml_workspace_path
from pipeline.workspace_layout import WorkspaceLayout
from ui.utils.context_cache import get_client_context

try:
    import yaml
except Exception:  # pragma: no cover
    yaml = None  # type: ignore

SECTION_ORDER = ["Vision", "Mission", "Framework Etico", "Goal", "Contesto Operativo"]


def _workspace_layout(slug: str) -> WorkspaceLayout:
    ctx = get_client_context(slug, require_drive_env=False)
    return WorkspaceLayout.from_context(ctx)


def load_workspace_yaml(slug: str) -> Dict[str, Any]:
    layout = _workspace_layout(slug)
    ypath = vision_yaml_workspace_path(layout.repo_root_dir, pdf_path=layout.vision_pdf)
    if not ypath.exists():
        raise FileNotFoundError(f"visionstatement.yaml nel workspace non trovato: {ypath}")
    if yaml is None:
        raise RuntimeError("PyYAML non disponibile")
    raw = read_text_safe(layout.repo_root_dir, ypath)
    data = yaml.safe_load(raw) or {}
    if not isinstance(data, dict):
        raise RuntimeError("YAML malformato")
    data.setdefault("sections", {})
    return data


def save_workspace_yaml(slug: str, data: Dict[str, Any]) -> Path:
    layout = _workspace_layout(slug)
    ypath = vision_yaml_workspace_path(layout.repo_root_dir, pdf_path=layout.vision_pdf)
    if not ypath.exists():
        raise FileNotFoundError(f"visionstatement.yaml nel workspace non trovato: {ypath}")
    if yaml is None:
        raise RuntimeError("PyYAML non disponibile")
    payload = yaml.safe_dump(data, allow_unicode=True, sort_keys=False)
    safe_write_text(ypath, payload, encoding="utf-8", atomic=True)
    return ypath


def build_prompt_from_yaml(
    data: Dict[str, Any],
    *,
    slug: str | None = None,
    client_name: str | None = None,
) -> str:
    client = data.get("client") or {}
    slug_value = str(slug or client.get("slug") or "").strip()
    if not slug_value:
        slug_value = "dummy"
    client_name_value = str(client_name or client.get("client_name") or "").strip()
    if not client_name_value:
        client_name_value = "Dummy"

    sections = data.get("sections") or {}

    def _sec(key: str) -> str:
        return str(sections.get(key, "") or "").strip()

    tag_map = {
        "Vision": _sec("vision"),
        "Mission": _sec("mission"),
        "Framework Etico": _sec("framework_etico"),
        "Goal": _sec("goal"),
        "Contesto Operativo": _sec("contesto_operativo"),
    }

    lines = [
        "Contesto cliente:",
        f"- slug: {slug_value}",
        f"- client_name: {client_name_value}",
        "",
        "Vision Statement (usa SOLO i blocchi sottostanti):",
    ]
    for tag in SECTION_ORDER:
        val = tag_map.get(tag, "")
        if val:
            lines += [f"[{tag}]", val, f"[/{tag}]"]
    return "\n".join(lines).strip() + "\n"
