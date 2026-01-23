# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import importlib.util
from dataclasses import dataclass
from pathlib import Path
from typing import List

from pipeline.file_utils import safe_write_text


@dataclass
class CheckItem:
    name: str
    ok: bool
    message: str


@dataclass
class SystemCheckReport:
    ok: bool
    items: List[CheckItem]


def _check_pypdf() -> CheckItem:
    present = importlib.util.find_spec("pypdf") is not None
    return CheckItem(
        name="pypdf",
        ok=present,
        message="dipendenza pypdf installata" if present else "dipendenza pypdf non installata",
    )


def _check_config(repo_root_dir: Path) -> CheckItem:
    cfg = repo_root_dir / "config" / "config.yaml"
    exists = cfg.is_file()
    return CheckItem(
        name="config",
        ok=exists,
        message=f"config.yaml presente in {cfg}" if exists else f"config.yaml mancante: {cfg}",
    )


def _check_output_writable(repo_root_dir: Path) -> CheckItem:
    # repo_root_dir here is REPO_ROOT_DIR (system repo root), not workspace root.
    # Do not copy this pattern into workspace-scoped runtime code.
    output_dir = repo_root_dir / "output"
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        probe = output_dir / ".selfcheck_tmp"
        safe_write_text(probe, "ok", encoding="utf-8", atomic=True)
        try:
            probe.unlink()
        except Exception:
            pass
        return CheckItem(name="output_write", ok=True, message=f"output scrivibile: {output_dir}")
    except Exception as exc:  # pragma: no cover - dipende dal FS
        return CheckItem(
            name="output_write",
            ok=False,
            message=f"output non scrivibile: {exc}",
        )


def _check_semantic_ingest(repo_root_dir: Path) -> List[CheckItem]:
    items: List[CheckItem] = []
    doc_ingest = repo_root_dir / "src" / "semantic" / "document_ingest.py"
    semantic_core = repo_root_dir / "src" / "semantic" / "core.py"
    for path, name in ((doc_ingest, "document_ingest"), (semantic_core, "semantic_core")):
        exists = path.is_file()
        items.append(
            CheckItem(
                name=name,
                ok=exists,
                message=f"{name} presente: {path}" if exists else f"{name} mancante: {path}",
            )
        )
    return items


def run_system_self_check(repo_root_dir: Path | None = None) -> SystemCheckReport:
    """
    Esegue una serie di controlli sull'ambiente di esecuzione.

    - Se repo_root_dir è None, deduce la root del repo a partire da questo file.
    - Verifica:
      - dipendenza pypdf installata,
      - presenza di config/config.yaml,
      - scrivibilità di output/ (o directory configurata),
      - presenza di moduli semantic di ingest.
    Ritorna un SystemCheckReport con la lista dei CheckItem e ok=all(item.ok).
    """

    if repo_root_dir is None:
        repo_root_dir = Path(__file__).resolve().parents[2]
    repo_root_dir = repo_root_dir.resolve()

    items: List[CheckItem] = []
    items.append(_check_pypdf())
    items.append(_check_config(repo_root_dir))
    items.append(_check_output_writable(repo_root_dir))
    items.extend(_check_semantic_ingest(repo_root_dir))

    overall_ok = all(item.ok for item in items)
    return SystemCheckReport(ok=overall_ok, items=items)
