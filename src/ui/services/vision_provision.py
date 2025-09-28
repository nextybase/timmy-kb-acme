"""Bridge module per riutilizzare semantic.vision_provision nella UI.

Responsabilità UI: gate di idempotenza su `semantic/.vision_hash` (hash PDF + modello).
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, cast

from pipeline.exceptions import ConfigError
from pipeline.file_utils import safe_write_text
from pipeline.path_utils import ensure_within_and_resolve, open_for_read_bytes_selfguard, read_text_safe
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

    - Path-safety del PDF lato UI.
    - Idempotenza: gate su `semantic/.vision_hash` (hash PDF + modello).
    - Normalizza il ritorno in {'yaml_paths': {...}} per compat con la UI attuale.
    """
    base_dir = getattr(ctx, "base_dir", None)
    if not base_dir:
        raise ConfigError("Context privo di base_dir per Vision onboarding.", slug=slug)

    # a) Path-safety del PDF lato UI
    safe_pdf = ensure_within_and_resolve(base_dir, pdf_path)

    # b) SHA256 streaming del PDF
    import hashlib

    h = hashlib.sha256()
    with open_for_read_bytes_selfguard(safe_pdf) as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    pdf_hash = h.hexdigest()

    # c) Modello effettivo
    model_env = os.getenv("VISION_MODEL")
    effective_model = model_env or model or "gpt-4.1-mini"

    # Percorsi del gate
    semantic_dir = ensure_within_and_resolve(base_dir, Path(base_dir) / "semantic")
    vision_hash_path = ensure_within_and_resolve(semantic_dir, semantic_dir / ".vision_hash")

    # d) Lettura gate e possibile blocco
    gate_hit = False
    try:
        if vision_hash_path.exists():
            raw = read_text_safe(Path(base_dir), vision_hash_path, encoding="utf-8")
            data = json.loads(raw or "{}")
            if isinstance(data, dict) and data.get("hash") == pdf_hash and data.get("model") == effective_model:
                gate_hit = True
    except Exception:
        gate_hit = False

    logger.info(
        "ui.vision.gate",
        extra={"slug": slug, "file_path": str(safe_pdf), "model": effective_model, "hit": gate_hit, "force": force},
    )

    if gate_hit and not force:
        raise ConfigError(
            "Già elaborato con lo stesso modello; usa force=True o sostituisci il PDF.",
            slug=slug,
            file_path=str(vision_hash_path),
        )

    # Invocazione semantica (passando PDF sicuro e modello effettivo)
    result = _provision_from_vision(ctx, logger, slug=slug, pdf_path=safe_pdf, model=effective_model, force=force)

    # e) Aggiornamento del gate dopo la generazione
    try:
        payload = json.dumps({"hash": pdf_hash, "model": effective_model}, ensure_ascii=False)
        safe_write_text(vision_hash_path, payload, atomic=True)
        logger.info(
            "ui.vision.update_hash",
            extra={"slug": slug, "file_path": str(vision_hash_path), "model": effective_model},
        )
    except Exception:
        # Non blocca il flusso UI se l'aggiornamento fallisce
        pass
    if isinstance(result, dict):
        if "yaml_paths" in result and isinstance(result.get("yaml_paths"), dict):
            return cast(Dict[str, Any], result)
        if "mapping" in result and "cartelle_raw" in result:
            return {"yaml_paths": {"mapping": result["mapping"], "cartelle_raw": result["cartelle_raw"]}}
    return {"yaml_paths": {}}
