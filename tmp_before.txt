"""Bridge module per riutilizzare semantic.vision_provision nella UI."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, cast

from semantic.types import ClientContextProtocol
from semantic.vision_provision import provision_from_vision as _provision_from_vision

__all__ = ["provision_from_vision"]


def provision_from_vision(
    ctx: ClientContextProtocol,
    logger: logging.Logger,
    *,
    slug: str,
    pdf_path: Path,
    model: str = "gpt-4.1-mini",
    force: bool = False,
) -> Dict[str, Any]:
    """Proxy UI-friendly verso semantic.vision_provision.provision_from_vision.

    Normalizza il ritorno in {'yaml_paths': {...}} per compat con la UI attuale.
    """
    result = _provision_from_vision(ctx, logger, slug=slug, pdf_path=pdf_path, model=model, force=force)
    if isinstance(result, dict):
        if "yaml_paths" in result and isinstance(result.get("yaml_paths"), dict):
            return cast(Dict[str, Any], result)
        if "mapping" in result and "cartelle_raw" in result:
            return {"yaml_paths": {"mapping": result["mapping"], "cartelle_raw": result["cartelle_raw"]}}
    return {"yaml_paths": {}}
