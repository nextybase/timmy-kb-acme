# SPDX-License-Identifier: GPL-3.0-only
"\"\"\"Skeptic gate per proteggere change di dominio critici (usato in CI).\"\"\""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Iterable


SENSITIVE_PATHS: tuple[str, ...] = (
    "src/pipeline/exceptions.py",
    "src/ai/resolution.py",
    "src/ai/assistant_registry.py",
    "src/ai/vision_config.py",
    "src/ai/client_factory.py",
    "src/ai/responses.py",
    "src/ai/providers/",
    ".codex/",
    "tools/gen_vision_yaml.py",
)


def _git_diff(base: str, head: str) -> tuple[list[str], list[str]]:
    name_only = subprocess.check_output(
        ["git", "diff", "--name-only", f"{base}..{head}"], text=True
    )
    patch = subprocess.check_output(["git", "diff", f"{base}..{head}"], text=True)
    return name_only.splitlines(), patch.splitlines()


def _match_sensitive(files: Iterable[str]) -> list[str]:
    hits = []
    for path in files:
        for sensitive in SENSITIVE_PATHS:
            if path == sensitive or path.startswith(sensitive):
                hits.append(path)
                break
    return hits


def _pattern_hits(patch_lines: Iterable[str]) -> list[str]:
    hits = []
    for line in patch_lines:
        if not (line.startswith("+") or line.startswith("-")):
            continue
        text = line[1:].strip()
        if (
            "-> Optional[" in text
            or "return None" in text
            or '""' in text and "None" in text
            or "ConfigError(" in text
            or "raise ConfigError" in text
        ):
            hits.append(line)
    return hits


def _acknowledged(changed_files: Iterable[str]) -> bool:
    for path in changed_files:
        if path.startswith("tests/"):
            return True
        if path == "SKEPTIC_ACK.md":
            return True
    return False


def main() -> int:
    base = os.environ.get("GITHUB_BASE_SHA") or os.environ.get("GITHUB_EVENT_BEFORE")
    head = os.environ.get("GITHUB_SHA")
    if not base or not head:
        print("Skeptic Gate skipped (no diff context).")
        return 0

    files, patch = _git_diff(base, head)
    sensitive = _match_sensitive(files)
    patterns = _pattern_hits(patch)
    ack = _acknowledged(files)

    trigger = bool(sensitive or patterns)
    if trigger and not ack:
        print("Skeptic Gate FAILED")
        if sensitive:
            print("-- sensitive files touched:")
            for path in sensitive[:20]:
                print(f"   - {path}")
        if patterns:
            print("-- pattern hits (limit 10):")
            for line in patterns[:10]:
                print(f"   {line}")
        print(
            "Add/modify a test under tests/** OR update SKEPTIC_ACK.md with a reason to acknowledge."
        )
        return 1

    summary = "Skeptic Gate PASS"
    if sensitive:
        ack_label = "ack via tests" if ack else "no ack required"
        summary += f" ({ack_label}, sensitive touched)"
    elif patterns:
        summary += " (patterns detected but acked)"
    else:
        summary += " (no sensitive changes)"
    print(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
