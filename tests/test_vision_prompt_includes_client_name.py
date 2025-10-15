from __future__ import annotations

from pathlib import Path

import pytest

import src.semantic.vision_provision as S

fitz = pytest.importorskip("fitz", reason="PyMuPDF non disponibile: installa PyMuPDF")


class DummyCtx:
    def __init__(self, base_dir: Path, client_name: str | None = None):
        self.base_dir = str(base_dir)
        self.client_name = client_name


class _NoopLogger:
    def info(self, *a, **k): ...
    def warning(self, *a, **k): ...
    def error(self, *a, **k): ...
    def exception(self, *a, **k): ...


def _write_pdf(path: Path, txt: str):
    doc = fitz.open()
    doc.new_page()
    doc[0].insert_text((72, 72), txt)
    doc.save(path)
    doc.close()


@pytest.fixture
def tmp_ws(tmp_path: Path) -> Path:
    base = tmp_path / "output" / "timmy-kb-acme"
    (base / "config").mkdir(parents=True, exist_ok=True)
    (base / "semantic").mkdir(parents=True, exist_ok=True)
    pdf = base / "config" / "VisionStatement.pdf"
    _write_pdf(
        pdf,
        "Vision\nA\nMission\nB\nGoal\nC\nFramework etico\nD\nDescrizione prodotto/azienda\nE\nDescrizione mercato\nF\n",
    )
    return base


def test_prompt_contains_client_name(monkeypatch, tmp_ws: Path):
    slug = "acme"
    ctx = DummyCtx(base_dir=tmp_ws, client_name="ACME S.p.A.")
    seen = {"user_messages": None}

    def _fake_call(client, *, assistant_id, user_messages, **kwargs):
        seen["user_messages"] = user_messages
        return {
            "context": {"slug": slug, "client_name": ctx.client_name},
            "areas": [{"key": "core", "ambito": "A", "descrizione": "D", "keywords": ["x"]}],
        }

    monkeypatch.setenv("OBNEXT_ASSISTANT_ID", "asst_dummy")
    monkeypatch.setattr(S, "_call_assistant_json", _fake_call)

    S.provision_from_vision(
        ctx, S.logging.getLogger("noop"), slug=slug, pdf_path=tmp_ws / "config" / "VisionStatement.pdf"
    )

    msg = seen["user_messages"][0]["content"]
    assert "client_name: ACME S.p.A." in msg
