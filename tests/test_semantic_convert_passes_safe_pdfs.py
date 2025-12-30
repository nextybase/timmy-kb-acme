# SPDX-License-Identifier: GPL-3.0-only
# tests/test_semantic_convert_passes_safe_pdfs.py
import logging

from semantic import api as sapi
from semantic import convert_service
from tests.support.contexts import TestClientCtx


def test_convert_markdown_passes_safe_pdfs_when_supported(tmp_path, monkeypatch, caplog):
    base = tmp_path / "kb"
    raw = base / "raw"
    book = base / "book"
    raw.mkdir(parents=True)
    book.mkdir(parents=True)
    (base / "config").mkdir(parents=True, exist_ok=True)
    (base / "config" / "config.yaml").write_text("meta:\n  client_name: test\n", encoding="utf-8")
    (base / "logs").mkdir(parents=True, exist_ok=True)
    (base / "semantic").mkdir(parents=True, exist_ok=True)
    (base / "semantic" / "semantic_mapping.yaml").write_text("{}", encoding="utf-8")
    (book / "README.md").write_text("# KB\n", encoding="utf-8")
    (book / "SUMMARY.md").write_text("# Summary\n", encoding="utf-8")
    pdf = raw / "doc.pdf"
    pdf.write_text("fake-pdf", encoding="utf-8")

    ctx = TestClientCtx(
        slug="dummy",
        base_dir=base,
        repo_root_dir=base,
        raw_dir=raw,
        md_dir=book,
        semantic_dir=base / "semantic",
        config_dir=base / "config",
    )

    # Forziamo la discovery sicura: ritorna il PDF trovato
    monkeypatch.setattr(convert_service, "_collect_safe_pdfs", lambda *a, **k: ([pdf], 0))

    called = {"ok": False, "safe_pdfs_len": -1}

    # Converter *compatibile* con safe_pdfs
    def _convert_md_stub(_ctx, *, md_dir=None, safe_pdfs=None):
        called["ok"] = True
        called["safe_pdfs_len"] = len(safe_pdfs or [])
        # non scriviamo su disco: simuliamo contenuti disponibili
        return None

    # list_content_markdown finge che il converter abbia prodotto 1 file
    monkeypatch.setattr(
        convert_service,
        "list_content_markdown",
        lambda bd: [book / "content.md"],
        raising=True,
    )
    # sostituisci il converter reale con lo stub
    monkeypatch.setattr(convert_service, "_convert_md", _convert_md_stub)

    caplog.set_level(logging.INFO)
    out = sapi.convert_markdown(ctx, logging.getLogger("test"), slug="dummy")

    assert called["ok"] is True
    assert called["safe_pdfs_len"] == 1
    assert out == [book / "content.md"]
