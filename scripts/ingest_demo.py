"""Esempio di ingest per Timmy KB.

Uso:
  python scripts/ingest_demo.py \
      --project evagrin \
      --scope Timmy \
      --glob "docs/**/*.md" \
      --version v1 \
      --meta "{\"source\": \"docs\"}"

Nota: richiede OPENAI_API_KEY_CODEX in ambiente (usa .env se presente).
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from typing import Dict

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from pipeline.env_utils import get_env_var

# Optional: carica .env
try:  # pragma: no cover - optional dependency
    from dotenv import load_dotenv  # type: ignore

    load_dotenv()
except Exception:
    pass

from timmykb.ingest import ingest_folder


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True)
    ap.add_argument("--scope", required=True, choices=["Timmy", "ClasScrum", "Zeno"])
    ap.add_argument("--glob", required=True)
    ap.add_argument("--version", required=True)
    ap.add_argument("--meta", default="{}", help="JSON meta o percorso file JSON")
    args = ap.parse_args()

    meta_str = args.meta
    meta: Dict
    try:
        if os.path.isfile(meta_str):
            with open(meta_str, "r", encoding="utf-8") as f:
                meta = json.load(f)
        else:
            meta = json.loads(meta_str)
    except Exception:
        meta = {}

    logging.basicConfig(level=logging.INFO)

    if not get_env_var("OPENAI_API_KEY_CODEX", default=None):
        raise SystemExit("OPENAI_API_KEY_CODEX mancante. Impostalo nell'ambiente o in un file .env.")

    summary = ingest_folder(
        project_slug=args.project,
        scope=args.scope,
        folder_glob=args.glob,
        version=args.version,
        meta=meta,
    )
    print(summary)


if __name__ == "__main__":
    main()
