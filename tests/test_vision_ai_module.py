# tests/test_vision_ai_module.py
from __future__ import annotations

import json
import logging
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

try:
    import fitz  # type: ignore
except ImportError:  # pragma: no cover - ambiente test minimal
    pytest.skip("PyMuPDF non disponibile: installa PyMuPDF/PyMuPDF wheels", allow_module_level=True)

from pipeline.context import ClientContext
from pipeline.exceptions import ConfigError
from semantic import vision_ai


def _make_pdf(path: Path, text: str) -> None:
    doc = fitz.open()
    try:
        page = doc.new_page()
        page.insert_text((72, 72), text)
        doc.save(path)
    finally:
        doc.close()


class FakeCompletions:
    def __init__(self, payload: dict[str, object], *, finish_reason: str = "stop", refusal: str | None = None) -> None:
        self._payload = payload
        self._finish_reason = finish_reason
        self._refusal = refusal
        self.last_kwargs: dict[str, object] | None = None

    def create(self, **kwargs) -> SimpleNamespace:
        self.last_kwargs = kwargs
        message = SimpleNamespace(content=json.dumps(self._payload), refusal=self._refusal)
        choice = SimpleNamespace(message=message, finish_reason=self._finish_reason)
        usage = SimpleNamespace(prompt_tokens=10, completion_tokens=20)
        return SimpleNamespace(choices=[choice], usage=usage)


class FakeClient:
    def __init__(self, completions: FakeCompletions) -> None:
        self.chat = SimpleNamespace(completions=completions)


def _make_context(tmp_path: Path, slug: str = "sample", *, pdf_text: str = "Visione aziendale") -> ClientContext:
    base_dir = tmp_path / "output" / f"timmy-kb-{slug}"
    (base_dir / "raw").mkdir(parents=True, exist_ok=True)
    (base_dir / "semantic").mkdir(parents=True, exist_ok=True)
    _make_pdf(base_dir / "raw" / "VisionStatement.pdf", pdf_text)
    return ClientContext(
        slug=slug,
        client_name=f"{slug.title()} Corp",
        base_dir=base_dir,
        repo_root_dir=tmp_path,
        settings={"client_name": f"{slug.title()} Corp"},
    )


def test_message_content_to_text_handles_mixed_blocks() -> None:
    content = [
        {"text": "uno"},
        SimpleNamespace(text="due"),
        {"ignored": "value"},
    ]
    assert vision_ai._message_content_to_text(content) == "unodue"
    assert vision_ai._message_content_to_text("  testo ") == "testo"


def test_json_to_yaml_valid_payload() -> None:
    data = {
        "context": {"slug": "sample", "client_name": "Sample Corp"},
        "areas": [
            {"key": "area-uno", "ambito": "Ambito", "descrizione": "Descrizione", "keywords": ["Doc"]},
            {"key": "area-due", "ambito": "Secondo", "descrizione": "Dettagli", "keywords": ["Doc2"]},
            {"key": "area-tre", "ambito": "Terzo", "descrizione": "Info", "keywords": ["Doc3"]},
        ],
        "synonyms": {"pa": ["pubblica amministrazione"]},
    }
    text = vision_ai._json_to_yaml(data)
    parsed = yaml.safe_load(text)
    assert parsed["context"]["slug"] == "sample"
    assert parsed["area-uno"]["ambito"] == "Ambito"
    assert parsed["synonyms"]["pa"] == ["pubblica amministrazione"]


def test_json_to_yaml_missing_area_field_raises() -> None:
    broken = {
        "context": {"slug": "demo", "client_name": "Demo"},
        "areas": [{"ambito": "Ambito", "descrizione": "Desc", "keywords": ["Doc"]}],
    }
    with pytest.raises(ConfigError):
        vision_ai._json_to_yaml(broken)


def test_json_to_yaml_missing_keywords_raises() -> None:
    data = {
        "context": {"slug": "demo", "client_name": "Demo"},
        "areas": [{"key": "demo", "ambito": "Ambito", "descrizione": "Desc"}],
    }
    with pytest.raises(ConfigError, match="keywords"):
        vision_ai._json_to_yaml(data)


def test_extract_pdf_text_returns_plain_text(tmp_path: Path) -> None:
    pdf_path = tmp_path / "vision.pdf"
    _make_pdf(pdf_path, "Contenuto Visione")
    extracted = vision_ai._extract_pdf_text(pdf_path)
    assert "Contenuto Visione" in extracted


def test_generate_creates_yaml_and_snapshot(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ctx = _make_context(tmp_path, slug="dummy", pdf_text="Missione e Visione")
    payload = {
        "context": {"slug": "dummy", "client_name": "Dummy Corp"},
        "areas": [
            {"key": "area-uno", "ambito": "Ambito", "descrizione": "Desc", "keywords": ["Doc"]},
            {"key": "area-due", "ambito": "Secondo", "descrizione": "Dettagli", "keywords": ["Doc2"]},
            {"key": "area-tre", "ambito": "Terzo", "descrizione": "Info", "keywords": ["Doc3"]},
        ],
        "synonyms": {"pa": ["pubblica amministrazione"]},
    }
    completions = FakeCompletions(payload)
    fake_client = FakeClient(completions)
    monkeypatch.setattr(vision_ai, "make_openai_client", lambda: fake_client)

    out_path = Path(vision_ai.generate(ctx, logging.getLogger("test"), slug="dummy"))

    assert out_path.exists()
    yaml_loaded = yaml.safe_load(out_path.read_text(encoding="utf-8"))
    assert yaml_loaded["context"]["client_name"] == "Dummy Corp"
    assert (ctx.base_dir / "semantic" / vision_ai._TEXT_SNAPSHOT_NAME).exists()
    assert completions.last_kwargs is not None
    assert completions.last_kwargs["model"] == vision_ai._MODEL


def test_snapshot_content_is_redacted(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pii_text = "Codice RSSMRA85T10A562S e contatto persona@example.com"
    ctx = _make_context(tmp_path, slug="pii", pdf_text=pii_text)
    payload = {
        "context": {"slug": "pii", "client_name": "PII Corp"},
        "areas": [
            {"key": "area-uno", "ambito": "Ambito", "descrizione": "Desc", "keywords": ["Doc"]},
            {"key": "area-due", "ambito": "Secondo", "descrizione": "Dettagli", "keywords": ["Doc2"]},
            {"key": "area-tre", "ambito": "Terzo", "descrizione": "Info", "keywords": ["Doc3"]},
        ],
    }
    completions = FakeCompletions(payload)
    fake_client = FakeClient(completions)
    monkeypatch.setattr(vision_ai, "make_openai_client", lambda: fake_client)

    vision_ai.generate(ctx, logging.getLogger("test"), slug="pii")

    snapshot_path = ctx.base_dir / "semantic" / vision_ai._TEXT_SNAPSHOT_NAME
    content = snapshot_path.read_text(encoding="utf-8")
    assert "[[REDACTED:CF]]" in content
    assert "[[REDACTED:EMAIL]]" in content
    assert "RSSMRA85T10A562S" not in content
    assert "persona@example.com" not in content


def test_snapshot_skipped_when_flag_disabled(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ctx = _make_context(tmp_path, slug="nosnap", pdf_text="Missione e Visione")
    ctx.env["VISION_SAVE_SNAPSHOT"] = "false"
    ctx.env["_VISION_SAVE_SNAPSHOT_BOOL"] = False
    payload = {
        "context": {"slug": "nosnap", "client_name": "No Snap Corp"},
        "areas": [
            {"key": "area-uno", "ambito": "Ambito", "descrizione": "Desc", "keywords": ["Doc"]},
            {"key": "area-due", "ambito": "Secondo", "descrizione": "Dettagli", "keywords": ["Doc2"]},
            {"key": "area-tre", "ambito": "Terzo", "descrizione": "Info", "keywords": ["Doc3"]},
        ],
    }
    completions = FakeCompletions(payload)
    fake_client = FakeClient(completions)
    monkeypatch.setattr(vision_ai, "make_openai_client", lambda: fake_client)

    vision_ai.generate(ctx, logging.getLogger("test"), slug="nosnap")

    snapshot_path = ctx.base_dir / "semantic" / vision_ai._TEXT_SNAPSHOT_NAME
    assert not snapshot_path.exists()


def test_generate_raises_on_finish_reason_length(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ctx = _make_context(tmp_path, slug="overflow")
    payload = {
        "context": {"slug": "overflow", "client_name": "Overflow Corp"},
        "areas": [
            {"key": "area-uno", "ambito": "Ambito", "descrizione": "Desc", "keywords": ["Doc"]},
            {"key": "area-due", "ambito": "Secondo", "descrizione": "Dettagli", "keywords": ["Doc2"]},
            {"key": "area-tre", "ambito": "Terzo", "descrizione": "Info", "keywords": ["Doc3"]},
        ],
    }
    completions = FakeCompletions(payload, finish_reason="length")
    fake_client = FakeClient(completions)
    monkeypatch.setattr(vision_ai, "make_openai_client", lambda: fake_client)

    with pytest.raises(ConfigError, match="lunghezza"):
        vision_ai.generate(ctx, logging.getLogger("test"), slug="overflow")
