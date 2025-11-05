#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Fail if UI services hardcode Vision model names (gpt-...)."""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Iterable


def check_files(files: Iterable[str]) -> int:
    offending: list[Path] = []
    for name in files:
        path = Path(name)
        try:
            text = path.read_text(encoding="utf-8")
        except Exception:
            continue
        if "gpt-" in text:
            offending.append(path)
    if offending:
        for path in offending:
            print(
                f"[vision-model-check] {path}: hardcoded Vision model rilevato. "
                "Usa get_vision_model() o un parametro esplicito."
            )
        return 1
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("files", nargs="*")
    args = parser.parse_args()
    return check_files(args.files)


if __name__ == "__main__":
    raise SystemExit(main())
