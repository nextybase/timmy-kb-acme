# SPDX-License-Identifier: GPL-3.0-only
# tools/kg_debug_dummy.py

from __future__ import annotations

import sys
from pathlib import Path

# --- bootstrap path (come gli altri tool) -------------------------------------
REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if SRC_DIR.exists():
    sys.path.insert(0, str(SRC_DIR))
sys.path.insert(0, str(REPO_ROOT))

from kg_builder import build_kg_for_workspace  # type: ignore[import]  # noqa: E402
from pipeline.env_utils import ensure_dotenv_loaded  # type: ignore[import]  # noqa: E402
from pipeline.exceptions import ConfigError  # type: ignore[import]  # noqa: E402
from pipeline.logging_utils import get_structured_logger  # type: ignore[import]  # noqa: E402

logger = get_structured_logger("tools.kg_debug_dummy")


def main() -> None:
    # 1) Carico .env esplicitamente
    ensure_dotenv_loaded()

    slug = "dummy"
    workspace_root = REPO_ROOT / f"output/timmy-kb-{slug}"

    print("=== KG debug dummy ===", flush=True)
    print(f"repo_root:      {REPO_ROOT}", flush=True)
    print(f"workspace_root: {workspace_root}", flush=True)

    if not workspace_root.exists():
        print(
            f"[ERRORE] Workspace inesistente: {workspace_root}\n"
            "         Genera prima il dummy tramite la UI o la CLI di onboarding.",
            flush=True,
        )
        raise SystemExit(1)

    semantic_dir = workspace_root / "semantic"
    tags_raw_path = semantic_dir / "tags_raw.json"

    if not tags_raw_path.exists():
        print(
            f"[ERRORE] semantic/tags_raw.json mancante nel workspace {workspace_root}\n"
            "         Esegui prima il tagging semantico / generazione tag.",
            flush=True,
        )
        raise SystemExit(1)

    print("[INFO] tags_raw.json trovato, avvio build_kg_for_workspace con assistant KGraph...", flush=True)

    try:
        kg = build_kg_for_workspace(workspace_root, namespace=slug)
    except ConfigError as exc:
        logger.error(
            "kg_debug_dummy.config_error",
            extra={"workspace": str(workspace_root), "error": str(exc)},
        )
        print("\n[ERRORE CONFIG] Tag KG Builder fallito con ConfigError:", flush=True)
        print(f"  {exc}", flush=True)
        raise SystemExit(1)
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "kg_debug_dummy.unexpected_error",
            extra={"workspace": str(workspace_root), "error": str(exc)},
        )
        print("\n[ERRORE] Tag KG Builder fallito con errore inatteso:", flush=True)
        print(f"  {exc!r}", flush=True)
        raise SystemExit(1)

    tags = getattr(kg, "tags", []) or []
    relations = getattr(kg, "relations", []) or []

    print("\n✔ Tag KG generato con successo (dialogo reale con l'assistant KGraph).", flush=True)
    print(f"namespace:       {getattr(kg, 'namespace', '')}", flush=True)
    print(f"schema_version:  {getattr(kg, 'schema_version', '')}", flush=True)
    print(f"tag count:       {len(tags)}", flush=True)
    print(f"relations count: {len(relations)}", flush=True)

    semantic_dir = workspace_root / "semantic"
    kg_json_path = semantic_dir / "kg.tags.json"
    kg_md_path = semantic_dir / "kg.tags.md"
    print(f"kg.tags.json:    {kg_json_path}", flush=True)
    print(f"kg.tags.md:      {kg_md_path}", flush=True)


if __name__ == "__main__":
    main()
