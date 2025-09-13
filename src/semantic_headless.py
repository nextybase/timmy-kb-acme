#!/usr/bin/env python3
from __future__ import annotations

import argparse
import logging
import sys

from pipeline.context import ClientContext  # type: ignore
from semantic.api import (
    convert_markdown,
    enrich_frontmatter,  # type: ignore
    get_paths,
    write_summary_and_readme,
)
from semantic.vocab_loader import load_reviewed_vocab  # type: ignore

# from pathlib import Path


def main() -> int:
    p = argparse.ArgumentParser(
        description="Semantic headless via semantic.api (convert/enrich/write)"
    )
    p.add_argument("--slug", required=True)
    p.add_argument("--no-preview", action="store_true", help="Ignorato (compat)")
    p.add_argument("--non-interactive", action="store_true", help="Ignorato (compat)")
    args = p.parse_args()

    slug = args.slug.strip()
    ctx = ClientContext.load(slug=slug, interactive=False, require_env=False, run_id=None)
    log = logging.getLogger("semantic.headless")

    convert_markdown(ctx, log, slug=slug)
    base = get_paths(slug)["base"]
    vocab = load_reviewed_vocab(base, log) or {}
    enrich_frontmatter(ctx, log, vocab, slug=slug)
    write_summary_and_readme(ctx, log, slug=slug)
    return 0


if __name__ == "__main__":
    sys.exit(main())
