# tests/test_vision_ai.py
from __future__ import annotations

import json
import types
from pathlib import Path

import pytest
import yaml

# Import del modulo da testare (segue lo stesso bootstrap della UI che aggiunge src/ al sys.path)
from semantic.vision_ai import generate as gen_vision_yaml

# --- Helpers -----------------------------------------------------------------


class DummyCtx:
    def __init__(self, base_dir: Path):
        self.base_dir = str(base_dir)
        self.client_name = None
        self.settings: dict[str, str] | None = None


class FakeVSObj:
    def __init__(self, id_: str = "vs_123"):
        self.id = id_
        # mimiamo l'attributo usato dal polling: .file_counts.completed
        self.file_counts = types.SimpleNamespace(completed=1)


class FakeVectorStores:
    """Mock minimale di client.vector_stores con .create/.retrieve e sottostruttura .files.batch"""

    def __init__(self):
        self._obj = FakeVSObj()

    def create(self, name: str):
        return self._obj

    def retrieve(self, vs_id: str):
        assert vs_id == "vs_123"
        return self._obj

    @property
    def files(self):
        # esponiamo un oggetto con metodo .batch(...)
        class _Files:
            @staticmethod
            def batch(vector_store_id: str, file_ids: list[str]):
                assert vector_store_id == "vs_123"
                assert len(file_ids) == 1
                return {"ok": True}

        return _Files()


class FakeFiles:
    def create(self, file, purpose: str):
        # restituisce un oggetto con .id come fa l'SDK
        return types.SimpleNamespace(id="file_abc")


class FakeResponses:
    def __init__(self, output_parsed: dict):
        self._out = output_parsed

    def create(self, **kwargs):
        class _Resp:
            def __init__(self, data):
                self.output_parsed = data

        return _Resp(self._out)


class FakeChatCompletions:
    def __init__(self, output_parsed: dict):
        self._payload = output_parsed

    def create(self, **kwargs):
        message = types.SimpleNamespace(content=json.dumps(self._payload), refusal=None)
        choice = types.SimpleNamespace(message=message, finish_reason="stop")
        usage = types.SimpleNamespace(prompt_tokens=0, completion_tokens=0)
        return types.SimpleNamespace(choices=[choice], usage=usage)


class FakeOpenAI:
    """Client OpenAI finto con le tre superfici usate: vector_stores, files, responses."""

    def __init__(self, output_parsed: dict):
        self.vector_stores = FakeVectorStores()
        self.files = FakeFiles()
        self.responses = FakeResponses(output_parsed)
        self.chat = types.SimpleNamespace(completions=FakeChatCompletions(output_parsed))


class _NoopLogger:
    def info(self, *args, **kwargs): ...

    def error(self, *args, **kwargs): ...

    def exception(self, *args, **kwargs): ...


# --- Helpers dinamici --------------------------------------------------------


def _create_dummy_pdf(path: Path) -> None:
    try:
        import fitz
    except ImportError:
        pytest.skip("PyMuPDF non disponibile: test ignorato")

    doc = fitz.open()
    try:
        page = doc.new_page()
        page.insert_text((72, 72), "Dummy Vision")
        doc.save(path)
    finally:
        doc.close()


# --- Fixture workspace temporaneo -------------------------------------------


@pytest.fixture
def tmp_workspace(tmp_path: Path) -> Path:
    base = tmp_path / "output" / "timmy-kb-dummy"
    (base / "config").mkdir(parents=True, exist_ok=True)
    pdf_path = base / "config" / "VisionStatement.pdf"
    _create_dummy_pdf(pdf_path)
    (base / "semantic").mkdir(parents=True, exist_ok=True)
    return base


# --- Test --------------------------------------------------------------------


def test_generate_happy_path(monkeypatch, tmp_workspace: Path):
    # output JSON gia conforme allo schema atteso da vision_ai
    output_parsed = {
        "context": {"slug": "dummy", "client_name": "Dummy"},
        "areas": [
            {
                "key": "artefatti-operativi",
                "ambito": "operativo",
                "descrizione": "Documenti e modelli operativi.",
                "esempio": ["SOP", "template", "checklist"],
            },
            {
                "key": "governance",
                "ambito": "strategico",
                "descrizione": "Regole e responsabilita.",
                "esempio": ["policy", "ruoli"],
            },
        ],
        "synonyms": {"pa": ["pubblica amministrazione"]},
    }

    # mock del factory per restituire un FakeOpenAI
    import semantic.vision_ai as vision_ai

    monkeypatch.setattr(
        vision_ai,
        "make_openai_client",
        lambda: FakeOpenAI(output_parsed),
    )

    ctx = DummyCtx(base_dir=tmp_workspace)
    out = gen_vision_yaml(ctx, logger=_NoopLogger(), slug="dummy")
    out_path = Path(out)
    assert out_path.exists(), "YAML non scritto"
    data = yaml.safe_load(out_path.read_text(encoding="utf-8"))
    # chiavi attese in YAML
    assert "context" in data
    assert "artefatti-operativi" in data
    assert "governance" in data
    assert data["context"]["slug"] == "dummy"


def test_generate_pair_crea_due_yaml(monkeypatch, tmp_workspace: Path):
    output_parsed = {
        "context": {"slug": "dummy", "client_name": "Dummy"},
        "areas": [
            {
                "key": "artefatti-operativi",
                "ambito": "operativo",
                "descrizione": "Documenti e modelli operativi.",
                "esempio": ["SOP", "template", "checklist"],
            },
            {
                "key": "governance",
                "ambito": "strategico",
                "descrizione": "Regole e responsabilita.",
                "esempio": ["policy", "ruoli"],
            },
        ],
    }

    import semantic.vision_ai as vision_ai

    monkeypatch.setattr(
        vision_ai,
        "make_openai_client",
        lambda: FakeOpenAI(output_parsed),
    )

    ctx = DummyCtx(base_dir=tmp_workspace)
    result = vision_ai.generate_pair(ctx, logger=_NoopLogger(), slug="dummy")

    vision_path = Path(result["vision_yaml"])
    cartelle_path = Path(result["cartelle_raw_yaml"])
    assert vision_path.exists()
    assert cartelle_path.exists()

    vision_yaml = yaml.safe_load(vision_path.read_text(encoding="utf-8"))
    cartelle_yaml = yaml.safe_load(cartelle_path.read_text(encoding="utf-8"))

    assert vision_yaml["context"]["slug"] == "dummy"
    assert cartelle_yaml["context"]["slug"] == "dummy"
    assert isinstance(cartelle_yaml.get("folders"), list) and cartelle_yaml["folders"]


def test_missing_pdf_raises(monkeypatch, tmp_path: Path):
    # workspace senza PDF
    base = tmp_path / "output" / "timmy-kb-dummy"
    (base / "config").mkdir(parents=True, exist_ok=True)
    (base / "semantic").mkdir(parents=True, exist_ok=True)

    import semantic.vision_ai as vision_ai

    # client mock (non sara usato perche falliamo prima della chiamata API)
    monkeypatch.setattr(
        vision_ai,
        "make_openai_client",
        lambda: FakeOpenAI({}),
    )

    ctx = DummyCtx(base_dir=base)
    with pytest.raises(vision_ai.ConfigError):
        gen_vision_yaml(ctx, logger=_NoopLogger(), slug="dummy")


def test_invalid_model_output(monkeypatch, tmp_workspace: Path):
    # output privo di "areas" -> deve fallire durante la conversione JSON->YAML
    bad_output = {
        "context": {"slug": "dummy", "client_name": "Dummy"},
        # "areas" mancante
    }

    import semantic.vision_ai as vision_ai

    monkeypatch.setattr(
        vision_ai,
        "make_openai_client",
        lambda: FakeOpenAI(bad_output),
    )

    ctx = DummyCtx(base_dir=tmp_workspace)
    with pytest.raises(Exception):
        gen_vision_yaml(ctx, logger=_NoopLogger(), slug="dummy")
