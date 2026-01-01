#!/usr/bin/env python3
from __future__ import annotations

import os
import subprocess
import sys
from typing import Sequence


ENTRYPOINT_PREFIXES = (
    "src/ui/",
    "src/timmy_kb/cli/",
    "tools/",
    "src/api/",
)

SEPARATION_DOC = ".codex/USER_DEV_SEPARATION.md"
ACK_FILE = "SEPARATION_ACK.md"


def _run_git_diff(base: str, head: str) -> Sequence[str]:
    result = subprocess.run(
        ["git", "diff", "--name-only", f"{base}..{head}"],
        check=True,
        capture_output=True,
        text=True,
    )
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def main() -> int:
    base_sha = os.environ.get("GITHUB_BASE_SHA")
    head_sha = os.environ.get("GITHUB_SHA")
    if not (base_sha and head_sha):
        print("Entrypoint guard: no diff context (missing base/head SHA), skipping.")
        return 0

    try:
        changed = _run_git_diff(base_sha, head_sha)
    except subprocess.CalledProcessError as exc:
        print(f"Entrypoint guard: git diff failed ({exc}).")
        return 1

    sensitive = [
        path
        for path in changed
        if any(path.startswith(prefix) for prefix in ENTRYPOINT_PREFIXES)
    ]
    if not sensitive:
        print("Entrypoint guard: no public entrypoint paths changed.")
        return 0

    ack_included = any(path == SEPARATION_DOC for path in changed)
    ack_included = ack_included or any(path == ACK_FILE for path in changed)

    if ack_included:
        print(
            "Entrypoint guard: entrypoint change detected, but separation acknowledgement updated."
        )
        return 0

    print("Entrypoint guard: public entrypoints changed without updated governance.")
    print(f"    Changed paths: {', '.join(sensitive)}")
    print(
        "Please update .codex/USER_DEV_SEPARATION.md or add/modify SEPARATION_ACK.md describing WHY, "
        "IMPACT, RISK, and TESTS RUN."
    )
    return 1


if __name__ == "__main__":
    code = main()
    sys.exit(code)
