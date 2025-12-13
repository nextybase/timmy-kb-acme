#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

"""Shim compatibile che mantiene `src/semantic_onboarding.py` come entrypoint."""

import sys
from importlib import import_module

_cli_module = import_module("timmy_kb.cli.semantic_onboarding")

if __name__ != "__main__":
    sys.modules[__name__] = _cli_module
else:
    try:
        raise SystemExit(_cli_module.main())
    except KeyboardInterrupt:
        raise SystemExit(130)
