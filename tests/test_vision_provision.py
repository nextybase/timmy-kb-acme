# =========================
# File: tests/test_vision_provision.py
# =========================
from __future__ import annotations

import json
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
    assert result.get("regenerated") is True

    # Verifiche di esito
    assert "yaml_paths" in result
    v_path = Path(result["yaml_paths"]["vision"])
    c_path = Path(result["yaml_paths"]["cartelle_raw"])
    assert v_path.exists(), "vision_statement.yaml non creato"
    assert c_path.exists(), "cartelle_raw.yaml non creato"

    # YAML parsabili e contenenti chiavi attese
    v_yaml = yaml.safe_load(v_path.read_text(encoding="utf-8"))
    c_yaml = yaml.safe_load(c_path.read_text(encoding="utf-8"))
    assert "context" in v_yaml and "artefatti-operativi" in v_yaml
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
        provision_from_vision(ctx, _NoopLogger(), slug="dummy", pdf_path=base / "config" / "VisionStatement.pdf")


def test_invalid_model_output_raises(monkeypatch, tmp_workspace: Path):
    # JSON invalido: manca "areas"
    bad_output = {"context": {"slug": "dummy", "client_name": "Dummy"}}

    import semantic.vision_provision as S

    monkeypatch.setattr(S, "make_openai_client", lambda: FakeOpenAI(bad_output))

    ctx = DummyCtx(base_dir=tmp_workspace)
    pdf_path = tmp_workspace / "config" / "VisionStatement.pdf"
    with pytest.raises(ConfigError):
        provision_from_vision(ctx, _NoopLogger(), slug="dummy", pdf_path=pdf_path)


def test_idempotenza_hash_salta_rigenerazione(monkeypatch, tmp_workspace: Path):
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

    result_first = provision_from_vision(ctx, _NoopLogger(), slug="dummy", pdf_path=pdf_path)
    assert result_first.get("regenerated") is True
    assert calls["count"] == 1

    vision_yaml = Path(result_first["yaml_paths"]["vision"])
    cartelle_yaml = Path(result_first["yaml_paths"]["cartelle_raw"])
    vision_mtime = vision_yaml.stat().st_mtime
    cartelle_mtime = cartelle_yaml.stat().st_mtime

    hash_file = tmp_workspace / "semantic" / ".vision_hash"
    assert hash_file.exists()

    log_path = tmp_workspace / "logs" / "vision_provision.log"
    assert log_path.exists()
    first_lines = log_path.read_text(encoding="utf-8").strip().splitlines()
    assert first_lines

    def _fail_client():
        raise AssertionError("OpenAI non dovrebbe essere invocato con hash invariato")

    monkeypatch.setattr(S, "make_openai_client", _fail_client)

    result_second = provision_from_vision(ctx, _NoopLogger(), slug="dummy", pdf_path=pdf_path)
    assert result_second.get("regenerated") is False
    assert result_second["yaml_paths"] == result_first["yaml_paths"]
    assert vision_yaml.stat().st_mtime == vision_mtime
    assert cartelle_yaml.stat().st_mtime == cartelle_mtime

    lines = log_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == len(first_lines) + 1
    last_record = json.loads(lines[-1])
    assert last_record["pdf_hash"] == result_second["pdf_hash"]
    assert last_record["regenerated"] is False
