# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

from pipeline.exceptions import ConfigError
from pipeline.path_utils import ensure_within_and_resolve, open_for_read_bytes_selfguard
from semantic.pdf_utils import extract_text_from_pdf


@dataclass
class DocumentContent:
    text_blocks: List[str]
    full_text: str
    metadata: Dict[str, Any]


def read_document(path: Path) -> DocumentContent:
    """
    Legge un documento sorgente e restituisce un DocumentContent normalizzato.

    - Oggi supporta solo i PDF (.pdf).
    - Usa extract_text_from_pdf come backend per l'estrazione.
    - Calcola sha256 del file sorgente.
    - Popola metadata di base (source_path, source_type, sha256, pipeline_version).
    """
    doc_path = Path(path)
    suffix = doc_path.suffix.lower()

    if suffix != ".pdf":
        raise ConfigError(
            f"Formato non supportato per read_document: {suffix}",
            file_path=str(doc_path),
        )

    safe_doc_path = ensure_within_and_resolve(doc_path.parent, doc_path)
    text_blocks = extract_text_from_pdf(safe_doc_path)
    full_text = "\n\n".join(text_blocks)
    with open_for_read_bytes_selfguard(safe_doc_path) as handle:
        sha256_hex = hashlib.sha256(handle.read()).hexdigest()

    metadata: Dict[str, Any] = {
        "source_path": str(doc_path),
        "source_type": "pdf",
        "sha256": sha256_hex,
        "pipeline_version": "1.0",
    }

    return DocumentContent(text_blocks=text_blocks, full_text=full_text, metadata=metadata)
