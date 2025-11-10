#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from pathlib import Path

import yaml

from pipeline.oidc_utils import OIDCError, ensure_oidc


def main() -> int:
    config_path = Path("config/config.yaml")
    cfg = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    try:
        env = ensure_oidc(cfg)
        printable = {k: v for k, v in env.items() if k != "OIDC_ID_TOKEN"}
        if printable:
            print(printable)
        return 0
    except OIDCError as exc:
        print(f"[OIDC ERROR] {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
