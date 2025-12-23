#!/usr/bin/env python3

"""
Smoke test per il gating della pagina Semantica.
- Scenario A: workspace dummy SENZA PDF -> Semantica nascosta.
- Scenario B: workspace dummy CON PDF minimo -> Semantica visibile.
Il test usa tools/ci_dump_nav.py per interrogare la navigazione effettiva.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Iterable, Mapping

from pipeline.file_utils import safe_write_bytes
from pipeline.path_utils import ensure_within_and_resolve
from pipeline.workspace_bootstrap import bootstrap_dummy_workspace


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _cleanup(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path, ignore_errors=True)
    else:
        try:
            path.unlink()
        except FileNotFoundError:
            pass


def _ci_dump_nav(env: Mapping[str, str]) -> dict:
    repo_root = _repo_root()
    script = repo_root / "tools" / "ci_dump_nav.py"
    merged_env = os.environ.copy()
    merged_env.update(env)
    result = subprocess.run(  # noqa: S603 - invocazione controllata di script repo
        [sys.executable, str(script)],
        text=True,
        cwd=repo_root,
        env=merged_env,
        check=True,
        capture_output=True,
    )
    output = result.stdout
    start = output.find("{")
    if start < 0:
        raise RuntimeError("Output JSON non trovato in tools/ci_dump_nav.py")
    return json.loads(output[start:])


def _has_semantics(nav: dict) -> bool:
    groups = nav.get("navigation", {})
    for specs in groups.values():
        for spec in specs:
            if spec.get("path") == "src/ui/pages/semantics.py":
                return True
    return False


def run_smoke(verbose: bool = False) -> None:
    repo_root = _repo_root()
    clients_dir = repo_root / "clients_db" / "semantics_smoke"
    workspace_root = repo_root / "output"

    slug_a = "semantics-smoke-a"
    slug_b = "semantics-smoke-b"
    paths_to_cleanup = [
        clients_dir,
        workspace_root / f"timmy-kb-{slug_a}",
        workspace_root / f"timmy-kb-{slug_b}",
    ]
    for path in paths_to_cleanup:
        _cleanup(path)

    clients_dir.mkdir(parents=True, exist_ok=True)

    env_base = {
        "CLIENTS_DB_DIR": "clients_db/semantics_smoke",
        "CLIENTS_DB_FILE": "clients.yaml",
    }

    def _write_ui_state(slug: str) -> None:
        payload = {"active_slug": slug}
        (clients_dir / "ui_state.json").write_text(json.dumps(payload), encoding="utf-8")

    try:
        # Scenario A: workspace SENZA PDF
        layout_a = bootstrap_dummy_workspace(slug_a)
        _write_ui_state(slug_a)
        nav_without = _ci_dump_nav(env_base)
        if verbose:
            print("Scenario A (senza PDF):")
            print(json.dumps(nav_without, indent=2))
        if _has_semantics(nav_without):
            raise RuntimeError("Semantica non dovrebbe essere visibile senza PDF in raw/")

        # Scenario B: workspace CON PDF
        layout_b = bootstrap_dummy_workspace(slug_b)
        pdf_path = ensure_within_and_resolve(layout_b.raw_dir, layout_b.raw_dir / "sample.pdf")
        safe_write_bytes(pdf_path, b"%PDF-1.4\n%%EOF\n", atomic=True)
        _write_ui_state(slug_b)
        nav_with = _ci_dump_nav(env_base)
        if verbose:
            print("Scenario B (con PDF):")
            print(json.dumps(nav_with, indent=2))
        if not _has_semantics(nav_with):
            raise RuntimeError("Semantica deve essere visibile quando raw/ contiene PDF")

        if verbose:
            print("Smoke semantics gating: OK")
    finally:
        for path in paths_to_cleanup:
            _cleanup(path)


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Smoke test per il gating della pagina Semantica.")
    parser.add_argument("--verbose", action="store_true", help="Stampa JSON intermedio.")
    args = parser.parse_args(argv)
    try:
        run_smoke(verbose=args.verbose)
    except Exception as exc:  # pragma: no cover
        print(f"[ERRORE] {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
