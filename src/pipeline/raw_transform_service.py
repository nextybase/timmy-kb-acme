# SPDX-License-Identifier: GPL-3.0-only
"""Raw Transform Service: RAW -> normalized (plain Markdown).

Contratto minimo:
- input: file path + metadata di base
- output: OK -> .md testo puro; SKIP -> formato non supportato; FAIL -> errore
- metadata obbligatori: transformer_name/version/ruleset_hash
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from pipeline.exceptions import PipelineError
from pipeline.file_utils import safe_write_text
from pipeline.path_utils import ensure_within_and_resolve

STATUS_OK = "OK"
STATUS_SKIP = "SKIP"
STATUS_FAIL = "FAIL"


@dataclass(frozen=True)
class RawTransformResult:
    status: str
    output_path: Path | None
    transformer_name: str
    transformer_version: str
    ruleset_hash: str
    error: str | None = None


class RawTransformService(Protocol):
    def transform(self, *, input_path: Path, output_path: Path) -> RawTransformResult: ...


def _normalize_text(text: str) -> str:
    cleaned = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if cleaned:
        return cleaned + "\n"
    return ""


def _extract_pdf_text(pdf_path: Path) -> str:
    try:
        from nlp.nlp_keywords import extract_text_from_pdf
    except Exception as exc:  # pragma: no cover
        raise PipelineError(
            "PDF extractor dependency missing: nlp.nlp_keywords.extract_text_from_pdf not available.",
            file_path=str(pdf_path),
        ) from exc

    try:
        raw_text = extract_text_from_pdf(str(pdf_path))
    except Exception as exc:
        raise PipelineError(
            "PDF text extraction failed.",
            file_path=str(pdf_path),
        ) from exc

    normalized = _normalize_text(raw_text or "")
    if not normalized:
        raise PipelineError(
            "PDF text extraction returned empty content.",
            file_path=str(pdf_path),
        )
    return normalized


class PdfTextTransformService:
    transformer_name = "pdf_text_v1"
    transformer_version = "1.0.0"
    ruleset_hash = hashlib.sha256(f"{transformer_name}:{transformer_version}".encode("utf-8")).hexdigest()

    def transform(self, *, input_path: Path, output_path: Path) -> RawTransformResult:
        if input_path.suffix.lower() != ".pdf":
            return RawTransformResult(
                status=STATUS_SKIP,
                output_path=None,
                transformer_name=self.transformer_name,
                transformer_version=self.transformer_version,
                ruleset_hash=self.ruleset_hash,
                error="unsupported_format",
            )

        text = _extract_pdf_text(input_path)
        safe_out = ensure_within_and_resolve(output_path.parent, output_path)
        safe_out.parent.mkdir(parents=True, exist_ok=True)
        safe_write_text(safe_out, text, encoding="utf-8", atomic=True)
        return RawTransformResult(
            status=STATUS_OK,
            output_path=safe_out,
            transformer_name=self.transformer_name,
            transformer_version=self.transformer_version,
            ruleset_hash=self.ruleset_hash,
            error=None,
        )


def get_default_raw_transform_service() -> RawTransformService:
    return PdfTextTransformService()


__all__ = [
    "STATUS_OK",
    "STATUS_SKIP",
    "STATUS_FAIL",
    "RawTransformResult",
    "RawTransformService",
    "PdfTextTransformService",
    "get_default_raw_transform_service",
]
