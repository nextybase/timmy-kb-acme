# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import sys
from importlib import metadata
from typing import Any

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


def _safe_get_distribution_version(dist_name: str) -> str | None:
    try:
        return metadata.version(dist_name)
    except Exception:
        return None


def _best_effort_git_sha() -> str | None:
    """
    Best-effort: ritorna l'HEAD SHA se disponibile.
    Non deve mai causare failure (policy: evidence, non enforcement).
    """
    try:
        import subprocess

        res = subprocess.run(  # noqa: S603
            ["git", "rev-parse", "HEAD"],  # noqa: S607
            check=False,
            capture_output=True,
            text=True,
        )
        if res.returncode == 0:
            sha = (res.stdout or "").strip()
            return sha or None
    except Exception as log_exc:
        try:
            sys.stderr.write(f"versioning._best_effort_git_sha logging_failure: {log_exc!r}\n")
        except OSError:
            pass
    return None


def build_env_fingerprint() -> dict[str, Any]:
    """
    Fingerprint ambiente (best-effort (non influenza artefatti/gate/ledger/exit code), no hard deps).
    Usato per auditabilita': NON deve influenzare flusso o determinismo.
    """
    import os
    import platform
    import sys

    fp: dict[str, Any] = {
        "git_sha": _best_effort_git_sha(),
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "timmy_env": os.getenv("TIMMY_ENV"),
        "timmy_beta_strict": os.getenv("TIMMY_BETA_STRICT"),
        "tags_nlp_backend": os.getenv("TAGS_NLP_BACKEND"),
        "spacy_model": os.getenv("SPACY_MODEL"),
        # distribuzioni "soft" (se installate)
        "streamlit_version": _safe_get_distribution_version("streamlit"),
        "spacy_version": _safe_get_distribution_version("spacy"),
        "sentence_transformers_version": _safe_get_distribution_version("sentence-transformers"),
        "pymupdf_version": _safe_get_distribution_version("PyMuPDF"),
        "reportlab_version": _safe_get_distribution_version("reportlab"),
        "google_api_client_version": _safe_get_distribution_version("google-api-python-client"),
        "pypdf_version": _safe_get_distribution_version("pypdf"),
    }
    return fp
