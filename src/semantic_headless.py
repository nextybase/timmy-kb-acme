# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

"""Shim compatibile per `semantic_headless`."""

import sys
from importlib import import_module

_cli_module = import_module("timmy_kb.cli.semantic_headless")

if __name__ != "__main__":
    sys.modules[__name__] = _cli_module
else:
    raise SystemExit(_cli_module.main())
