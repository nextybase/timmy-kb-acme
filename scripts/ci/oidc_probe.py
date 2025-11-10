# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from pathlib import Path
import sys

SRC_ROOT = (Path(__file__).resolve().parents[2] / "src").resolve()
if str(SRC_ROOT) not in sys.path:  # pragma: no cover - path setup
    sys.path.insert(0, str(SRC_ROOT))

from pipeline.logging_utils import get_structured_logger  # noqa: E402
from pipeline.oidc_utils import ensure_oidc_context  # noqa: E402
from pipeline.settings import Settings  # noqa: E402


def main() -> int:
    log = get_structured_logger("ci.oidc_probe")
    repo_root = Path(__file__).resolve().parents[2]
    settings = Settings.load(repo_root, logger=log, slug="ci")
    ctx = ensure_oidc_context(settings, logger=log)
    log.info(
        "ci.oidc_probe.done",
        extra={
            "enabled": ctx["enabled"],
            "provider": ctx["provider"],
            "has_token": ctx["has_token"],
        },
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
