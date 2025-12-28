# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import sys
from pathlib import Path

_TOOLS_DIR = next(p for p in Path(__file__).resolve().parents if p.name == "tools")
_REPO_ROOT = _TOOLS_DIR.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from tools._bootstrap import bootstrap_repo_src

# ENTRYPOINT BOOTSTRAP - consentito: abilita import pipeline.* in ambiente CI.
REPO_ROOT = bootstrap_repo_src()

from pipeline.logging_utils import get_structured_logger  # noqa: E402
from pipeline.oidc_utils import ensure_oidc_context  # noqa: E402
from pipeline.settings import Settings  # noqa: E402


def main() -> int:
    log = get_structured_logger("ci.oidc_probe")
    repo_root = REPO_ROOT
    settings = Settings.load(repo_root, logger=log, slug="ci")
    ctx = ensure_oidc_context(settings, logger=log)
    cfg = settings.as_dict() if hasattr(settings, "as_dict") else {}
    oidc_cfg = (cfg.get("security") or {}).get("oidc") or {}
    ci_required = bool(oidc_cfg.get("ci_required"))
    log.info(
        "ci.oidc_probe.done",
        extra={
            "enabled": ctx["enabled"],
            "provider": ctx["provider"],
            "has_token": ctx["has_token"],
            "ci_required": ci_required,
        },
    )
    if ci_required and not ctx["has_token"]:
        log.error(
            "ci.oidc_probe.missing_token",
            extra={"enabled": ctx["enabled"], "provider": ctx["provider"]},
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
