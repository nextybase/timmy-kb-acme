"""Esempio di ingest per Timmy KB.

Uso:
  python tools/ingest_demo.py \
      --project evagrin \
      --scope Timmy \
      --glob "docs/**/*.md" \
      --version v1 \
      --meta "{\"source\": \"docs\"}"

Nota: richiede OPENAI_API_KEY in ambiente (usa .env se presente).
"""

from __future__ import annotations

import argparse
import json
import logging
import os
from typing import Dict

# Optional: carica .env
try:  # pragma: no cover - optional dependency
    from dotenv import load_dotenv  # type: ignore

    load_dotenv()
except Exception:
    pass

from src.ingest import ingest_folder


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

    if not os.getenv("OPENAI_API_KEY"):
        raise SystemExit("OPENAI_API_KEY mancante. Impostalo nell'ambiente o in un file .env.")

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
