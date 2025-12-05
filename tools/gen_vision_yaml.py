# SPDX-License-Identifier: GPL-3.0-or-later
"""
Shim di compatibilità per `tools.gen_vision_yaml`.

La logica risiede in `src.tools.gen_vision_yaml`; qui la riesponiamo per
consentire import e invocazioni da CLI come `python tools/gen_vision_yaml.py`.
"""

from __future__ import annotations

import src.tools.gen_vision_yaml as _impl
from src.tools.gen_vision_yaml import *  # noqa: F401,F403


def main(argv: list[str] | None = None) -> int:  # pragma: no cover - delega pura
    # Mantiene eventuali monkeypatch su provision_from_vision fatti nel modulo shim.
    if provision_from_vision is not _impl.provision_from_vision:
        _impl.provision_from_vision = provision_from_vision  # type: ignore[assignment]
    _main = getattr(_impl, "main")
    if argv is None:
        return _main()
    import sys

    argv_bak = sys.argv[:]
    try:
        sys.argv = ["gen_vision_yaml.py", *argv]
        return _main()
    finally:
        sys.argv = argv_bak


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
