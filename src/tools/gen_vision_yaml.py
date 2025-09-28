# src/tools/gen_vision_yaml.py
from __future__ import annotations

import argparse
import sys
from importlib import import_module
from pathlib import Path

# Bootstrap identico alla UI: aggiungi SRC al sys.path
ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

# Import dinamici per rispettare E402 mantenendo il bootstrap di sys.path
ClientContext = import_module("pipeline.context").ClientContext
ensure_dotenv_loaded = import_module("pipeline.env_utils").ensure_dotenv_loaded
get_structured_logger = import_module("pipeline.logging_utils").get_structured_logger
vision_ai = import_module("semantic.vision_ai")


def main() -> int:
    """Genera gli artefatti Vision Statement richiedendo il modello AI."""
    ap = argparse.ArgumentParser("gen_vision_yaml")
    ap.add_argument("--slug", required=True, help="ID cliente (kebab-case)")
    args = ap.parse_args()

    log = get_structured_logger("tools.gen_vision_yaml")

    try:
        ensure_dotenv_loaded()
        ctx = ClientContext.load(slug=args.slug, interactive=False, require_env=False, run_id=None)
        out = vision_ai.generate(ctx, log, slug=args.slug)
        log.info("vision_yaml_generated", extra={"slug": args.slug, "output": str(out)})
        sys.stdout.write(f"{out}\n")
        return 0
    except vision_ai.ConfigError as err:
        log.error("vision_yaml_config_error", extra={"slug": args.slug, "error": str(err)})
        sys.stderr.write(f"ConfigError: {err}\n")
        return 2
    except Exception as exc:
        log.exception("vision_yaml_failed", extra={"slug": args.slug, "error": str(exc)})
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
