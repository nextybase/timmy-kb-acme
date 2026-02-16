# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import subprocess
import sys
import textwrap


def test_semantic_headless_unexpected_returns_99_without_traceback() -> None:
    code = textwrap.dedent("""
        import timmy_kb.cli.semantic_headless as sh

        sh.ensure_strict_runtime = lambda **_: (_ for _ in ()).throw(RuntimeError("boom"))
        raise SystemExit(sh.main())
        """)
    proc = subprocess.run(
        [sys.executable, "-c", code],
        check=False,
        capture_output=True,
        text=True,
    )

    assert proc.returncode == 99
    assert "Traceback" not in proc.stdout
    assert "Traceback" not in proc.stderr
