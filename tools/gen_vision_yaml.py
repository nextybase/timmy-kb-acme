# SPDX-License-Identifier: GPL-3.0-only
# tools/gen_vision_yaml.py
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from pipeline.context import ClientContext
from pipeline.exceptions import ConfigError
from pipeline.logging_utils import get_structured_logger
from pipeline.vision_runner import HaltError, run_vision_with_gating


def main() -> int:
    """Genera gli artefatti Vision Statement richiedendo il modello AI."""
    parser = argparse.ArgumentParser("gen_vision_yaml")
    parser.add_argument("--slug", required=True, help="Slug cliente (kebab-case)")
    parser.add_argument("--pdf", required=True, help="Percorso al VisionStatement.pdf")
    parser.add_argument("--base", default="output", help="Root output (default: output)")
    args = parser.parse_args()

    log = get_structured_logger("tools.gen_vision_yaml")
    base_dir = Path(args.base) / f"timmy-kb-{args.slug}"
    base_dir.mkdir(parents=True, exist_ok=True)
    ctx = ClientContext(slug=args.slug, client_name=args.slug, repo_root_dir=base_dir)

    pdf_path = Path(args.pdf).resolve()
    if not pdf_path.is_file():
        log.error("vision_yaml.pdf_not_found", extra={"slug": args.slug, "file_path": str(pdf_path)})
        return 1

    try:
        result = run_vision_with_gating(
            ctx,
            logger=log,
            slug=args.slug,
            pdf_path=pdf_path,
        )
        if result.get("skipped"):
            log.info(
                "vision_yaml_skipped",
                extra={"slug": args.slug, "mode": result.get("mode", "SMOKE")},
            )
            return 0
        log.info("vision_yaml_generated", extra={"slug": args.slug, **result})
        return 0
    except HaltError as err:
        log.error("vision_yaml_halt", extra={"slug": args.slug, "error": str(err)})
        sys.stderr.write(f"HaltError: {err}\n")
        return 2
    except ConfigError as err:
        log.error("vision_yaml_config_error", extra={"slug": args.slug, "error": str(err)})
        sys.stderr.write(f"ConfigError: {err}\n")
        return 1
    except Exception as exc:
        log.exception("vision_yaml_failed", extra={"slug": args.slug, "error": str(exc)})
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
