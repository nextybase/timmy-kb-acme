# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

from importlib import metadata

from pipeline.logging_utils import get_structured_logger

LOGGER = get_structured_logger("timmy_kb.versioning")

UI_RELEASE = "1.0-beta"
_CACHED_PACKAGE_VERSION: str | None = None


def get_package_version() -> str:
    global _CACHED_PACKAGE_VERSION
    if _CACHED_PACKAGE_VERSION is not None:
        return _CACHED_PACKAGE_VERSION
    try:
        _CACHED_PACKAGE_VERSION = metadata.version("timmy-kb")
        return _CACHED_PACKAGE_VERSION
    except metadata.PackageNotFoundError as exc:
        LOGGER.error("versioning.package_missing", extra={"error": str(exc)})
        raise RuntimeError("Pacchetto 'timmy-kb' non installato: impossibile risolvere la versione") from exc
    except Exception as exc:  # pragma: no cover - difesa esplicita
        LOGGER.error("versioning.package_version_error", extra={"error": repr(exc)})
        raise RuntimeError("Impossibile risolvere la versione del pacchetto 'timmy-kb'") from exc


def build_identity() -> dict[str, str]:
    return {"ui_release": UI_RELEASE, "package_version": get_package_version()}
