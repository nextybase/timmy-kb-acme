# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, cast

from pipeline.file_utils import safe_write_text
from pipeline.path_utils import ensure_within_and_resolve, read_text_safe
from ui.utils.repo_root import get_repo_root

try:
    import yaml
except Exception:  # pragma: no cover
    yaml = None  # type: ignore

SECTION_ORDER = ["Vision", "Mission", "Framework Etico", "Goal", "Contesto Operativo"]


def repo_root() -> Path:
    return get_repo_root(allow_env=True)


def root_yaml_path() -> Path:
    repo = repo_root()
    return cast(Path, ensure_within_and_resolve(repo, repo / "config" / "vision_statement.yaml"))


def load_root_yaml() -> Dict[str, Any]:
    ypath = root_yaml_path()
    if not ypath.exists():
        raise FileNotFoundError(f"File YAML non trovato: {ypath}")
    if yaml is None:
        raise RuntimeError("PyYAML non disponibile")
    raw = read_text_safe(repo_root(), ypath)
    data = yaml.safe_load(raw) or {}
    if not isinstance(data, dict):
        raise RuntimeError("YAML malformato")
    data.setdefault("sections", {})
    return data


def save_root_yaml(data: Dict[str, Any]) -> Path:
    if yaml is None:
        raise RuntimeError("PyYAML non disponibile")
    ypath = root_yaml_path()
    payload = yaml.safe_dump(data, allow_unicode=True, sort_keys=False)
    safe_write_text(ypath, payload, encoding="utf-8", atomic=True)
    return ypath


def build_prompt_from_yaml(data: Dict[str, Any]) -> str:
    client = data.get("client") or {}
    slug = str(client.get("slug") or "dummy").strip()
    client_name = str(client.get("client_name") or "Dummy").strip()

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
        f"- slug: {slug}",
        f"- client_name: {client_name}",
        "",
        "Vision Statement (usa SOLO i blocchi sottostanti):",
    ]
    for tag in SECTION_ORDER:
        val = tag_map.get(tag, "")
        if val:
            lines += [f"[{tag}]", val, f"[/{tag}]"]
    return "\n".join(lines).strip() + "\n"
