# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import List

import pytest
import yaml

from semantic.core import compile_document_to_vision_yaml, compile_pdf_to_yaml
from semantic.pdf_utils import PdfExtractError


def _make_text_pdf(path: Path, text: str = "Hello Vision") -> None:
    """
    Genera un PDF minimale con testo estratto da pypdf.
    Costruzione manuale per evitare dipendenze extra.
    """
    text_safe = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    content_stream = f"BT /F1 12 Tf 72 720 Td ({text_safe}) Tj ET\n".encode("latin-1")

    objects: List[bytes] = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Count 1 /Kids [3 0 R] >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 144] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"".join(
            [
                f"<< /Length {len(content_stream)} >>\nstream\n".encode("latin-1"),
                content_stream,
                b"\nendstream",
            ]
        ),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]

    buffer = bytearray()
    buffer.extend(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets: List[int] = []

    for idx, body in enumerate(objects, start=1):
        offsets.append(len(buffer))
        buffer.extend(f"{idx} 0 obj\n".encode("latin-1"))
        buffer.extend(body)
        buffer.extend(b"\nendobj\n")

    xref_offset = len(buffer)
    xref_lines = ["xref", "0 6", "0000000000 65535 f "]
    xref_lines.extend(f"{off:010d} 00000 n " for off in offsets)
    buffer.extend("\n".join(xref_lines).encode("latin-1"))
    buffer.extend(b"\n")

    trailer = f"trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n"
    buffer.extend(trailer.encode("latin-1"))

    path.write_bytes(buffer)


def test_compile_pdf_to_yaml_creates_yaml_file(tmp_path: Path) -> None:
    cfg_dir = tmp_path / "config"
    cfg_dir.mkdir()
    pdf_path = cfg_dir / "VisionStatement.pdf"
    yaml_path = cfg_dir / "visionstatement.yaml"
    _make_text_pdf(pdf_path, text="Vision content")

    compile_pdf_to_yaml(pdf_path, yaml_path)

    assert yaml_path.is_file()
    parsed = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    expected_sha = hashlib.sha256(pdf_path.read_bytes()).hexdigest()

    assert parsed["version"] == 1
    assert parsed["metadata"]["source_pdf_path"] == str(pdf_path)
    assert parsed["metadata"]["source_pdf_sha256"] == expected_sha
    assert parsed["content"]["pages"]
    assert "Vision content" in parsed["content"]["full_text"]


def test_compile_pdf_to_yaml_raises_on_missing_pdf(tmp_path: Path) -> None:
    cfg_dir = tmp_path / "config"
    cfg_dir.mkdir()
    pdf_path = cfg_dir / "missing.pdf"
    yaml_path = cfg_dir / "visionstatement.yaml"

    with pytest.raises(PdfExtractError):
        compile_pdf_to_yaml(pdf_path, yaml_path)


def test_compile_document_to_vision_yaml_creates_yaml_file(tmp_path: Path) -> None:
    cfg_dir = tmp_path / "config"
    cfg_dir.mkdir()
    pdf_path = cfg_dir / "VisionStatement.pdf"
    yaml_path = cfg_dir / "visionstatement.yaml"
    _make_text_pdf(pdf_path, text="Doc content")

    compile_document_to_vision_yaml(pdf_path, yaml_path)

    assert yaml_path.is_file()
    parsed = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    expected_sha = hashlib.sha256(pdf_path.read_bytes()).hexdigest()

    assert parsed["version"] == 1
    assert parsed["metadata"]["source_pdf_path"] == str(pdf_path)
    assert parsed["metadata"]["source_pdf_sha256"] == expected_sha
    assert parsed["content"]["pages"]
    assert "Doc content" in parsed["content"]["full_text"]
