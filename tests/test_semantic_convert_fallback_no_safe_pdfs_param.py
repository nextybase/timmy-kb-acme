# SPDX-License-Identifier: GPL-3.0-only
# tests/test_semantic_convert_fallback_no_safe_pdfs_param.py
import logging

from semantic import api as sapi
from semantic import convert_service
from tests.support.contexts import TestClientCtx


def test_convert_markdown_legacy_converter_without_safe_pdfs(tmp_path, monkeypatch, caplog):
    base = tmp_path / "kb"
    raw = base / "raw"
    book = base / "book"
    raw.mkdir(parents=True)
    book.mkdir(parents=True)
    pdf = raw / "x.pdf"
    pdf.write_text("fake", encoding="utf-8")

    ctx = TestClientCtx(slug="dummy", base_dir=base, raw_dir=raw, md_dir=book)

    # Discovery sicura → c'è un PDF valido
    monkeypatch.setattr(convert_service, "_collect_safe_pdfs", lambda *a, **k: ([pdf], 0))

    called = {"ok": False}

    # Converter *legacy* (nessun parametro safe_pdfs nella firma)
    def _legacy_convert_md(_ctx, *, md_dir=None):
        called["ok"] = True
        return None

    monkeypatch.setattr(convert_service, "_convert_md", _legacy_convert_md)
    # Simula contenuti prodotti
    monkeypatch.setattr(
        convert_service,
        "list_content_markdown",
        lambda bd: [book / "A.md", book / "B.md"],
        raising=True,
    )

    caplog.set_level(logging.INFO)
    out = sapi.convert_markdown(ctx, logging.getLogger("test"), slug="dummy")

    # Deve funzionare senza TypeError e senza passare safe_pdfs
    assert called["ok"] is True
    assert out == [book / "A.md", book / "B.md"]
