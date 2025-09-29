# tests/test_semantic_convert_passes_safe_pdfs.py
import logging
from types import SimpleNamespace

import src.semantic.api as api


def test_convert_markdown_passes_safe_pdfs_when_supported(tmp_path, monkeypatch, caplog):
    base = tmp_path / "kb"
    raw = base / "raw"
    book = base / "book"
    raw.mkdir(parents=True)
    book.mkdir(parents=True)
    pdf = raw / "doc.pdf"
    pdf.write_text("fake-pdf", encoding="utf-8")

    ctx = SimpleNamespace(base_dir=base, raw_dir=raw, md_dir=book)

    # Forziamo la discovery sicura: ritorna il PDF trovato
    monkeypatch.setattr(api, "_collect_safe_pdfs", lambda *a, **k: ([pdf], 0))

    called = {"ok": False, "safe_pdfs_len": -1}

    # Converter *compatibile* con safe_pdfs
    def _convert_md_stub(_ctx, *, md_dir=None, safe_pdfs=None):
        called["ok"] = True
        called["safe_pdfs_len"] = len(safe_pdfs or [])
        # non scriviamo su disco: simuliamo contenuti disponibili
        return None

    # list_content_markdown finge che il converter abbia prodotto 1 file
    monkeypatch.setattr(api, "list_content_markdown", lambda bd: [book / "content.md"])
    # sostituisci il converter reale con lo stub
    monkeypatch.setattr(api, "_convert_md", _convert_md_stub)

    caplog.set_level(logging.INFO)
    out = api.convert_markdown(ctx, logging.getLogger("test"), slug="acme")

    assert called["ok"] is True
    assert called["safe_pdfs_len"] == 1
    assert out == [book / "content.md"]
