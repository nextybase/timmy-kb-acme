# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import yaml

from semantic.document_ingest import DocumentContent, read_document

try:
    # Usato per scrittura atomica e sicura, coerente con gli altri moduli.
    from pipeline.file_utils import safe_write_text
except Exception:  # pragma: no cover - fallback se l'import fallisce in ambienti limitati
    safe_write_text = None  # type: ignore[misc]


def _build_payload(source_path: Path, pages: list[str], sha256: str) -> Dict[str, Any]:
    return {
        "version": 1,
        "metadata": {
            "source_pdf_path": str(source_path),
            "source_pdf_sha256": sha256,
        },
        "content": {
            "pages": pages,
            "full_text": "\n\n".join(pages),
        },
    }


def compile_document_to_vision_yaml(source_path: Path, yaml_path: Path) -> None:
    """
    Legge un documento sorgente e scrive un visionstatement.yaml strutturato (schema v1).

    - Usa read_document(...) -> DocumentContent.
    - Mappa DocumentContent verso payload YAML v1.
    - Solleva eccezioni se il documento non è leggibile o il formato non è supportato.
    """
    source_path = Path(source_path)
    output_yaml = Path(yaml_path)

    doc: DocumentContent = read_document(source_path)
    payload = _build_payload(
        Path(doc.metadata.get("source_path", source_path)),
        doc.text_blocks,
        doc.metadata.get("sha256", ""),
    )

    yaml_str = yaml.safe_dump(payload, allow_unicode=True, sort_keys=False)
    output_yaml.parent.mkdir(parents=True, exist_ok=True)

    if safe_write_text is None:  # pragma: no cover - safety gate
        raise RuntimeError("safe_write_text non disponibile per scrivere visionstatement.yaml")
    safe_write_text(output_yaml, yaml_str)


def compile_pdf_to_yaml(pdf_path: Path, yaml_path: Path) -> None:
    """
    Thin wrapper per compatibilità: delega a compile_document_to_vision_yaml.
    """
    return compile_document_to_vision_yaml(pdf_path, yaml_path)
