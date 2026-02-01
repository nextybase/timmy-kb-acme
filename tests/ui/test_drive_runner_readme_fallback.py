# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations


def test_render_readme_payload_requires_reportlab(monkeypatch):
    import pytest

    import ui.services.drive_runner as dr

    def _raise_import_error(*_args, **_kwargs):
        raise ImportError("reportlab missing")

    monkeypatch.setattr(dr, "_render_readme_pdf_bytes", _raise_import_error)

    with pytest.raises(ImportError):
        dr._render_readme_payload(
            title="Test README",
            descr="Descrizione",
            examples=["a", "b"],
        )


def test_render_readme_payload_returns_pdf(monkeypatch):
    import ui.services.drive_runner as dr

    monkeypatch.setattr(dr, "_render_readme_pdf_bytes", lambda *_a, **_k: b"%PDF-1.4")

    data, mime = dr._render_readme_payload(
        title="Test README",
        descr="Descrizione",
        examples=["a", "b"],
    )

    assert data.startswith(b"%PDF")
    assert mime == "application/pdf"
