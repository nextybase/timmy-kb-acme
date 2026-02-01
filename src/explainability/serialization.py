# SPDX-License-Identifier: GPL-3.0-or-later
"""Utility di serializzazione per il manifest di risposta."""

from __future__ import annotations

import json
from pathlib import Path

from explainability.manifest import ResponseManifest
from pipeline.file_utils import safe_write_text
from pipeline.path_utils import ensure_within_and_resolve


def safe_write_manifest(manifest: ResponseManifest, *, output_dir: Path, response_id: str) -> Path:
    """Scrive il manifest in JSON in modo atomico e path-safe.

    Args:
        manifest: manifest per-risposta da serializzare.
        output_dir: directory base dove salvare il file.
        response_id: identificativo che diventa il nome file (<response_id>.json).

    Returns:
        Path del file scritto.
    """
    target_dir = ensure_within_and_resolve(output_dir, output_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = ensure_within_and_resolve(target_dir, target_dir / f"{response_id}.json")
    content = json.dumps(manifest, ensure_ascii=False, separators=(",", ":"))
    safe_write_text(target_path, content, encoding="utf-8", atomic=True)
    return target_path


__all__ = ["safe_write_manifest"]
