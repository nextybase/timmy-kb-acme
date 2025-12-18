# SPDX-License-Identifier: GPL-3.0-only
# tools/smoke_e2e.py
from __future__ import annotations

import argparse
import os
import sys
import tempfile
from pathlib import Path

from pipeline.file_utils import safe_write_text
from pipeline.path_utils import ensure_within_and_resolve


def _add_paths() -> None:
    """Rende importabili sia `src.*` sia i moduli sotto `src/` (es. `pipeline.*`)."""
    root = Path(__file__).resolve().parents[1]
    src = root / "src"
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))


def _tiny_pdf_bytes() -> bytes:
    # PDF minimale sufficiente per test I/O (non per rendering)
    return (
        b"%PDF-1.4\n"
        b"1 0 obj\n<< /Type /Catalog >>\nendobj\n"
        b"xref\n0 2\n0000000000 65535 f \n0000000010 00000 n \n"
        b"trailer\n<< /Root 1 0 R >>\nstartxref\n9\n%%EOF\n"
    )


def _disable_github_push() -> None:
    """Disabilita ogni tentativo di push su GitHub nello smoke test."""
    for k in ("GITHUB_TOKEN", "GH_TOKEN", "GIT_TOKEN", "GITHUB_PAT", "ACTIONS_RUNTIME_TOKEN"):
        os.environ.pop(k, None)
    os.environ["TIMMY_NO_GITHUB"] = "1"
    os.environ["SKIP_GITHUB_PUSH"] = "1"


def main() -> int:
    _add_paths()

    import importlib
    from typing import Any, Dict
    from timmy_kb.cli import pre_onboarding
    onboarding_full = importlib.import_module("onboarding_full")
    finance_api = importlib.import_module("finance.api")
    pipeline_context = importlib.import_module("pipeline.context")

    parser = argparse.ArgumentParser(description="Smoke E2E: REPO_ROOT_DIR + orchestratore + finanza")
    parser.add_argument("--slug", default="dummy", help="Slug cliente per il test (default: dummy)")
    parser.add_argument(
        "--repo-root",
        default="",
        help="Cartella per REPO_ROOT_DIR; se non fornita usa una temp dir",
    )
    args = parser.parse_args()

    # 1) REPO_ROOT_DIR isolato
    repo_root = Path(args.repo_root) if args.repo_root else Path(tempfile.mkdtemp(prefix="next-smoke-"))
    os.environ["REPO_ROOT_DIR"] = str(repo_root)

    slug = args.slug
    client_name = f"{slug}-client"

    print(f"[1/4] REPO_ROOT_DIR = {repo_root}")
    repo_root.mkdir(parents=True, exist_ok=True)

    # 2) Workspace minimo via pre_onboarding.ensure_local_workspace_for_ui
    print("[2/4] Creo workspace locale minimoâ€¦")
    pdf_bytes = _tiny_pdf_bytes()
    _ = pre_onboarding.ensure_local_workspace_for_ui(slug=slug, client_name=client_name, vision_statement_pdf=pdf_bytes)

    # Conferma base_dir dal ClientContext (SSoT dei path)
    ctx: Any = pipeline_context.ClientContext.load(slug=slug, interactive=False, require_env=False, run_id="smoke")
    base_dir = getattr(ctx, "base_dir", None)
    if not isinstance(base_dir, Path):
        raw_dir = getattr(ctx, "raw_dir", None)
        base_dir = raw_dir.parent if isinstance(raw_dir, Path) else None
    if not isinstance(base_dir, Path):
        raise AssertionError("base_dir non disponibile nel ClientContext")

    raw_dir = base_dir / "raw"
    sem_dir = base_dir / "semantic"
    raw_dir.mkdir(parents=True, exist_ok=True)
    sem_dir.mkdir(parents=True, exist_ok=True)

    print(f"      base_dir: {base_dir}")

    # 3) Import CSV finanza â†’ semantic/finance.db
    print("[3/4] Import CSV finanza in semantic/finance.dbâ€¦")
    csv_path = sem_dir / "smoke.csv"
    safe_csv_path = ensure_within_and_resolve(base_dir, csv_path)
    safe_write_text(safe_csv_path, "metric,period,value\nrevenue,2023,1234\n", encoding="utf-8", atomic=True)
    csv_path = safe_csv_path

    res: Dict[str, Any] = finance_api.import_csv(base_dir, csv_path)
    rows = int(res.get("rows", 0) or 0)
    db_path_raw = res.get("db", sem_dir / "finance.db")
    db_path = Path(str(db_path_raw))

    if rows < 1:
        raise AssertionError("import_csv non ha importato righe")
    if not db_path.exists():
        raise AssertionError("finance.db non creato")

    print(f"      OK: {rows} righe importate in {db_path}")

    # 4) Esegui orchestratore e verifica output base (senza GitHub obbligatorio)
    print("[4/4] Eseguo orchestratore onboarding_full_mainâ€¦")
    _disable_github_push()
    try:
        onboarding_full.onboarding_full_main(slug=slug, non_interactive=True, run_id="smoke")
    except Exception as e:
        msg = str(e).lower()
        if "github" in msg or "git push" in msg or "personal access token" in msg:
            print(f"⚠️ GitHub disabilitato nello smoke: {e}")
        else:
            raise

    # Log opzionali: non rendere blocking lâ€™assenza del file specifico
    logs_dir = base_dir / "logs"
    log_candidates = []
    if logs_dir.exists() and logs_dir.is_dir():
        try:
            log_candidates = sorted(
                logs_dir.glob("*.log"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
        except Exception:
            log_candidates = []

    if log_candidates:
        print(f"      OK: log creato â†’ {log_candidates[0]}")
    else:
        print("      ⚠️ Nessun *.log trovato in logs/ (non bloccante per lo smoke).")

    print("\nâœ… Smoke test completato con successo.")
    print(f"   Workspace: {base_dir}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as e:
        print(f"\n❌ Smoke test fallito: {e}", file=sys.stderr)
        raise SystemExit(1)
    except Exception as e:
        print(f"\n❌ Errore inaspettato: {e}", file=sys.stderr)
        raise SystemExit(2)
