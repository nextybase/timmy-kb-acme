# SPDX-License-Identifier: GPL-3.0-or-later
"""
Shim di compatibilità per `tools.gen_vision_yaml`.

La logica risiede in `src.tools.gen_vision_yaml`; qui la riesponiamo per
consentire import e invocazioni da CLI come `python tools/gen_vision_yaml.py`.
"""

from __future__ import annotations

from src.tools.gen_vision_yaml import *  # noqa: F401,F403


def main() -> int:  # pragma: no cover - delega pura
    from src.tools.gen_vision_yaml import main as _main

    return _main()


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
