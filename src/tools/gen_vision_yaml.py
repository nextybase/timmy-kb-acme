# src/tools/gen_vision_yaml.py
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

# Bootstrap identico alla UI: aggiungi SRC al sys.path
ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from pipeline.context import ClientContext
from pipeline.env_utils import ensure_dotenv_loaded
from semantic import vision_ai


def main() -> int:
    ap = argparse.ArgumentParser("gen_vision_yaml")
    ap.add_argument("--slug", required=True, help="ID cliente (kebab-case)")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO)
    log = logging.getLogger("tools.gen_vision_yaml")

    try:
        ensure_dotenv_loaded()
        ctx = ClientContext.load(slug=args.slug, interactive=False, require_env=False, run_id=None)
        out = vision_ai.generate(ctx, log, slug=args.slug)
        log.info("Completato", extra={"out": out})
        print(out)
        return 0
    except vision_ai.ConfigError as e:
        log.error("ConfigError: %s", e, extra={"slug": args.slug})
        print(f"ConfigError: {e}", file=sys.stderr)
        return 2
    except Exception:
        log.exception("Errore inatteso")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
