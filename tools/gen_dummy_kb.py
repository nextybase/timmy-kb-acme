# SPDX-License-Identifier: GPL-3.0-or-later
"""
Shim di compatibilità per `tools.gen_dummy_kb`.

La logica vive in `src.tools.gen_dummy_kb`; qui re-esponiamo le funzioni
per mantenere invariati gli import nei test e negli script.
"""

from __future__ import annotations

from src.tools.gen_dummy_kb import *  # noqa: F401,F403


def main(argv: list[str] | None = None) -> int:  # pragma: no cover - delega pura
    from src.tools.gen_dummy_kb import main as _main

    return _main(argv)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
