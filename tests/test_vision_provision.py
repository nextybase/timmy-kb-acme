# =========================
# File: tests/test_vision_provision.py
# =========================
from __future__ import annotations

import types
from pathlib import Path

import pytest
import yaml

from pipeline.exceptions import ConfigError

# Import modulo sotto test
from semantic.vision_provision import provision_from_vision

# ---- Fakes OpenAI -----------------------------------------------------------


class FakeVSObj:
    def __init__(self, id_: str = "vs_123"):
        self.id = id_
        self.file_counts = types.SimpleNamespace(completed=1)


class FakeVectorStores:
    def __init__(self):
        self._obj = FakeVSObj()

    def create(self, name: str):
        return self._obj

    def retrieve(self, vs_id: str):
        assert vs_id == "vs_123"
        return self._obj

    @property
    def files(self):
        class _Files:
            @staticmethod
            def batch(vector_store_id: str, file_ids: list[str]):
                assert vector_store_id == "vs_123"
                assert len(file_ids) == 1
                return {"ok": True}

        return _Files()


class FakeFiles:
    def create(self, file, purpose: str):
        return types.SimpleNamespace(id="file_abc")


class FakeResponses:
    def __init__(self, output_parsed: dict):
        self._out = output_parsed

    def create(self, **kwargs):
        class _Resp:
            def __init__(self, data):
                self.output_parsed = data

        return _Resp(self._out)


class FakeOpenAI:
    def __init__(self, output_parsed: dict):
        self.vector_stores = FakeVectorStores()
        self.files = FakeFiles()
        self.responses = FakeResponses(output_parsed)


class _NoopLogger:
    def info(self, *args, **kwargs): ...

    def error(self, *args, **kwargs): ...

    def exception(self, *args, **kwargs): ...


class DummyCtx:
    def __init__(self, base_dir: Path):
        self.base_dir = str(base_dir)


# ---- Fixtures ----------------------------------------------------------------


@pytest.fixture
def tmp_workspace(tmp_path: Path) -> Path:
    base = tmp_path / "output" / "timmy-kb-dummy"
    (base / "config").mkdir(parents=True, exist_ok=True)
    (base / "semantic").mkdir(parents=True, exist_ok=True)
    pdf = base / "config" / "VisionStatement.pdf"
    pdf.write_bytes(b"%PDF dummy")
    return base


# ---- Tests -------------------------------------------------------------------


def test_happy_path(monkeypatch, tmp_workspace: Path):
    # Output JSON valido e minimo
    output_parsed = {
        "context": {"slug": "dummy", "client_name": "Dummy"},
        "areas": [
            {
                "key": "artefatti-operativi",
                "ambito": "operativo",
                "descrizione": "Documenti e modelli operativi.",
                "esempio": ["SOP", "template"],
            },
            {
                "key": "governance",
                "ambito": "strategico",
                "descrizione": "Regole e responsabilità.",
                "esempio": ["policy", "ruoli"],
            },
        ],
        "synonyms": {"pa": ["pubblica amministrazione"]},
    }

    # Mock del factory che restituisce il FakeOpenAI
    import semantic.vision_provision as S

    monkeypatch.setattr(S, "make_openai_client", lambda: FakeOpenAI(output_parsed))

    ctx = DummyCtx(base_dir=tmp_workspace)
    pdf_path = tmp_workspace / "config" / "VisionStatement.pdf"
    result = provision_from_vision(ctx, _NoopLogger(), slug="dummy", pdf_path=pdf_path)
    # La funzione ora ritorna direttamente i path attesi
    mapping_path = Path(result["mapping"])
    c_path = Path(result["cartelle_raw"])
    assert mapping_path.exists(), "semantic_mapping.yaml non creato"
    assert c_path.exists(), "cartelle_raw.yaml non creato"

    # YAML parsabili e contenenti chiavi attese
    mapping_yaml_data = yaml.safe_load(mapping_path.read_text(encoding="utf-8"))
    c_yaml = yaml.safe_load(c_path.read_text(encoding="utf-8"))
    assert "context" in mapping_yaml_data and "artefatti-operativi" in mapping_yaml_data
    assert c_yaml.get("version") == 1
    assert isinstance(c_yaml.get("folders"), list)


def test_missing_pdf_raises(monkeypatch, tmp_path: Path):
    base = tmp_path / "output" / "timmy-kb-dummy"
    (base / "config").mkdir(parents=True, exist_ok=True)
    (base / "semantic").mkdir(parents=True, exist_ok=True)

    import semantic.vision_provision as S

    # Client mock (non usato perché falliamo prima)
    monkeypatch.setattr(S, "make_openai_client", lambda: FakeOpenAI({}))

    ctx = DummyCtx(base_dir=base)
    with pytest.raises(ConfigError):
        provision_from_vision(
            ctx,
            _NoopLogger(),
            slug="dummy",
            pdf_path=base / "config" / "VisionStatement.pdf",
        )


def test_invalid_model_output_raises(monkeypatch, tmp_workspace: Path):
    # JSON invalido: manca "areas"
    bad_output = {"context": {"slug": "dummy", "client_name": "Dummy"}}

    import semantic.vision_provision as S

    monkeypatch.setattr(S, "make_openai_client", lambda: FakeOpenAI(bad_output))

    ctx = DummyCtx(base_dir=tmp_workspace)
    pdf_path = tmp_workspace / "config" / "VisionStatement.pdf"
    with pytest.raises(ConfigError):
        provision_from_vision(ctx, _NoopLogger(), slug="dummy", pdf_path=pdf_path)


def test_generation_creates_only_two_yaml(monkeypatch, tmp_workspace: Path):
    output_parsed = {
        "context": {"slug": "dummy", "client_name": "Dummy"},
        "areas": [
            {
                "key": "artefatti-operativi",
                "ambito": "operativo",
                "descrizione": "Documenti e modelli operativi.",
                "esempio": ["SOP", "template"],
            },
            {
                "key": "governance",
                "ambito": "strategico",
                "descrizione": "Regole e responsabilità.",
                "esempio": ["policy", "ruoli"],
            },
        ],
    }

    import semantic.vision_provision as S

    calls = {"count": 0}

    def _fake_client():
        calls["count"] += 1
        return FakeOpenAI(output_parsed)

    monkeypatch.setattr(S, "make_openai_client", _fake_client)

    ctx = DummyCtx(base_dir=tmp_workspace)
    pdf_path = tmp_workspace / "config" / "VisionStatement.pdf"

    # Prima esecuzione: generazione YAML
    provision_from_vision(ctx, _NoopLogger(), slug="dummy", pdf_path=pdf_path)
    assert calls["count"] == 1

    # Nessun artefatto legacy creato
    assert not (tmp_workspace / "semantic" / ".vision_hash").exists()
    assert not (tmp_workspace / "semantic" / "vision_statement.txt").exists()

    # In semantic/ devono esistere solo i due YAML richiesti.
    # Gli eventuali altri file fuori perimetro non sono considerati in questo test.
    semantic_files = {p.name for p in (tmp_workspace / "semantic").glob("*")}
    assert {"semantic_mapping.yaml", "cartelle_raw.yaml"}.issubset(semantic_files)

    # Seconda esecuzione: il client viene richiamato nuovamente e i file restano validi
    result_second = provision_from_vision(ctx, _NoopLogger(), slug="dummy", pdf_path=pdf_path)
    assert calls["count"] == 2
    assert Path(result_second["mapping"]).exists()
    assert Path(result_second["cartelle_raw"]).exists()
