from __future__ import annotations

import logging
from pathlib import Path

import pytest
import yaml

fitz = pytest.importorskip("fitz", reason="PyMuPDF non disponibile: installa PyMuPDF")

import timmykb.semantic.vision_provision as S
from pipeline.exceptions import ConfigError


@pytest.fixture(autouse=True)
def _ensure_openai_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Uniforma l'ambiente OpenAI per i test Vision inline."""
    monkeypatch.delenv("OPENAI_API_KEY_FOLDER", raising=False)
    monkeypatch.delenv("OPENAI_FORCE_HTTPX", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "dummy-key")
    monkeypatch.setattr(S, "make_openai_client", lambda: object())


# ---- Helpers ---------------------------------------------------------------


def _write_pdf(path: Path, text: str | None) -> None:
    doc = fitz.open()
    doc.new_page()
    if text:
        doc[0].insert_text((72, 72), text)
    doc.save(path)
    doc.close()


class DummyCtx:
    def __init__(self, base_dir: Path):
        self.base_dir = str(base_dir)


class _NoopLogger:
    def info(self, *a, **k): ...
    def warning(self, *a, **k): ...
    def error(self, *a, **k): ...
    def exception(self, *a, **k): ...


# ---- Fixtures --------------------------------------------------------------


@pytest.fixture
def tmp_workspace(tmp_path: Path) -> Path:
    base = tmp_path / "output" / "timmy-kb-dummy"
    (base / "config").mkdir(parents=True, exist_ok=True)
    (base / "semantic").mkdir(parents=True, exist_ok=True)
    pdf = base / "config" / "VisionStatement.pdf"
    _write_pdf(
        pdf,
        "Vision\nA\nMission\nB\nGoal\nC\nFramework etico\nD\nDescrizione prodotto/azienda\nE\nDescrizione mercato\nF\n",
    )
    return base


# ---- Tests: estrazione PDF -------------------------------------------------


def test_extract_pdf_text_empty(tmp_path, caplog):
    pdf = tmp_path / "empty.pdf"
    _write_pdf(pdf, "")

    logger = logging.getLogger("test.extract")
    with caplog.at_level(logging.INFO):
        with pytest.raises(ConfigError, match="vuoto"):
            S._extract_pdf_text(pdf, slug="dummy", logger=logger)

    assert any(
        rec.message == "semantic.vision.extract_failed" and getattr(rec, "reason", None) == "empty"
        for rec in caplog.records
    )


def test_extract_pdf_text_corrupted(tmp_path, caplog):
    pdf = tmp_path / "corrupted.pdf"
    pdf.write_bytes(b"not-a-pdf")

    logger = logging.getLogger("test.extract")
    with caplog.at_level(logging.WARNING):
        with pytest.raises(ConfigError, match="illeggibile"):
            S._extract_pdf_text(pdf, slug="dummy", logger=logger)

    assert any(
        rec.message == "semantic.vision.extract_failed" and getattr(rec, "reason", None) == "corrupted"
        for rec in caplog.records
    )


def test_extract_pdf_text_success(tmp_path):
    pdf = tmp_path / "sample.pdf"
    _write_pdf(pdf, "Hello Vision")
    logger = logging.getLogger("test.extract")
    text_out = S._extract_pdf_text(pdf, slug="dummy", logger=logger)
    assert "Hello Vision" in text_out


# ---- Tests: flusso inline-only --------------------------------------------


def test_happy_path_inline(monkeypatch, tmp_workspace: Path):
    # Falsifica la chiamata all'assistente restituendo JSON conforme al contratto Fase 1
    output_parsed = {
        "version": "1.0-beta",
        "source": "vision",
        "status": "ok",
        "context": {"slug": "dummy", "client_name": "Dummy"},
        "areas": [
            {
                "key": "governance",
                "ambito": "governance",
                "descrizione_breve": "Organi e decisioni formali; per tracciabilità e conformità.",
                "descrizione_dettagliata": {
                    "include": ["verbale CdA", "delibera"],
                    "exclude": ["PRD"],
                    "artefatti_note": "Registro delibere",
                },
                "documents": ["verbale CdA", "delibera"],
                "artefatti": ["registro_delibere.md"],
            },
            {
                "key": "it-data",
                "ambito": "it-data",
                "descrizione_breve": "Infrastruttura, sicurezza e dati; per resilienza.",
                "descrizione_dettagliata": {
                    "include": ["architetture", "runbook incident"],
                    "exclude": ["contratti"],
                    "artefatti_note": "Playbook incident",
                },
                "documents": ["architetture", "runbook incident"],
                "artefatti": ["playbook_incident.md"],
            },
            {
                "key": "prodotto-servizio",
                "ambito": "prodotto-servizio",
                "descrizione_breve": "Requisiti e manuali; per rilascio prodotto.",
                "descrizione_dettagliata": {
                    "include": ["PRD", "manuale utente"],
                    "exclude": ["contratti"],
                    "artefatti_note": "Template PRD",
                },
                "documents": ["PRD", "manuale utente"],
                "artefatti": ["template_PRD.md"],
            },
        ],
        "system_folders": {
            "identity": {"documents": ["statuto", "visura camerale"]},
            "glossario": {"artefatti": ["glossario.yaml"], "terms_hint": ["SLA", "PRD"]},
        },
        "metadata_policy": {
            "chunk_length_tokens": {"target": 800, "overlap": 100},
            "mandatory_fields": [
                "slug",
                "area_key",
                "ambito",
                "doc_class",
                "doc_uid",
                "source_uri",
                "page_span",
                "chunk_id",
                "language",
                "version",
                "created_at",
                "sensitivity",
                "retention",
                "entities",
                "relations_hint",
            ],
        },
    }

    captured = {"user_messages": None}

    def _fake_call(client, *, assistant_id, user_messages, strict_output=True, run_instructions=None):
        captured["user_messages"] = user_messages
        return output_parsed

    monkeypatch.setattr(S, "_call_assistant_json", _fake_call)
    monkeypatch.setenv("OBNEXT_ASSISTANT_ID", "asst_dummy")

    ctx = DummyCtx(base_dir=tmp_workspace)
    pdf_path = tmp_workspace / "config" / "VisionStatement.pdf"
    result = S.provision_from_vision(ctx, _NoopLogger(), slug="dummy", pdf_path=pdf_path)

    # File creati
    mapping = Path(result["mapping"])
    cartelle = Path(result["cartelle_raw"])
    assert mapping.exists() and cartelle.exists()

    # YAML parsabili e consistenti (assert meno rigidi per compat con refactor)
    mdata = yaml.safe_load(mapping.read_text(encoding="utf-8"))
    cdata = yaml.safe_load(cartelle.read_text(encoding="utf-8"))
    assert isinstance(mdata, dict) and "context" in mdata
    assert "version" in cdata and isinstance(cdata.get("folders"), list)

    # Ha passato un unico messaggio utente coerente
    assert captured["user_messages"] and isinstance(captured["user_messages"][0]["content"], str)


def test_invalid_model_output_raises(monkeypatch, tmp_workspace: Path):
    bad_output = {"context": {"slug": "dummy", "client_name": "Dummy"}}  # manca areas

    monkeypatch.setattr(S, "_call_assistant_json", lambda **_: bad_output)
    monkeypatch.setenv("ASSISTANT_ID", "asst_dummy")

    ctx = DummyCtx(base_dir=tmp_workspace)
    with pytest.raises(ConfigError):
        S.provision_from_vision(
            ctx, _NoopLogger(), slug="dummy", pdf_path=tmp_workspace / "config" / "VisionStatement.pdf"
        )


def test_slug_mismatch_raises(monkeypatch, tmp_workspace: Path):
    # Payload con slug diverso → deve alzare ConfigError (qualsiasi messaggio)
    mismatched = {
        "version": "1.0-beta",
        "source": "vision",
        "status": "ok",
        "context": {"slug": "other", "client_name": "X"},
        "areas": [
            {
                "key": "governance",
                "ambito": "governance",
                "descrizione_breve": "x",
                "descrizione_dettagliata": {"include": [], "exclude": [], "artefatti_note": ""},
                "documents": [],
                "artefatti": [],
            },
            {
                "key": "it-data",
                "ambito": "it-data",
                "descrizione_breve": "y",
                "descrizione_dettagliata": {"include": [], "exclude": [], "artefatti_note": ""},
                "documents": [],
                "artefatti": [],
            },
            {
                "key": "prodotto-servizio",
                "ambito": "prodotto-servizio",
                "descrizione_breve": "z",
                "descrizione_dettagliata": {"include": [], "exclude": [], "artefatti_note": ""},
                "documents": [],
                "artefatti": [],
            },
        ],
        "system_folders": {"identity": {"documents": []}, "glossario": {"artefatti": ["glossario.yaml"]}},
        "metadata_policy": {"chunk_length_tokens": {"target": 800, "overlap": 100}, "mandatory_fields": []},
    }
    monkeypatch.setattr(S, "_call_assistant_json", lambda **_: mismatched)
    monkeypatch.setenv("ASSISTANT_ID", "asst_dummy")
    ctx = DummyCtx(base_dir=tmp_workspace)
    with pytest.raises(ConfigError):
        S.provision_from_vision(
            ctx, _NoopLogger(), slug="dummy", pdf_path=tmp_workspace / "config" / "VisionStatement.pdf"
        )


def test_missing_system_folders_raises(monkeypatch, tmp_workspace: Path):
    # Prima questo test verificava la mancanza di 'keywords' (Fase 2). Ora controlliamo un vincolo Fase 1.
    out = {
        "version": "1.0-beta",
        "source": "vision",
        "status": "ok",
        "context": {"slug": "dummy", "client_name": "Dummy"},
        "areas": [
            {
                "key": "a",
                "ambito": "x",
                "descrizione_breve": "d",
                "descrizione_dettagliata": {"include": [], "exclude": [], "artefatti_note": ""},
                "documents": [],
                "artefatti": [],
            },
            {
                "key": "b",
                "ambito": "y",
                "descrizione_breve": "d",
                "descrizione_dettagliata": {"include": [], "exclude": [], "artefatti_note": ""},
                "documents": [],
                "artefatti": [],
            },
            {
                "key": "c",
                "ambito": "z",
                "descrizione_breve": "d",
                "descrizione_dettagliata": {"include": [], "exclude": [], "artefatti_note": ""},
                "documents": [],
                "artefatti": [],
            },
        ],
        # <-- system_folders mancante di proposito
        "metadata_policy": {"chunk_length_tokens": {"target": 800, "overlap": 100}, "mandatory_fields": []},
    }
    monkeypatch.setattr(S, "_call_assistant_json", lambda **_: out)
    monkeypatch.setenv("ASSISTANT_ID", "asst_dummy")
    ctx = DummyCtx(base_dir=tmp_workspace)
    with pytest.raises((ConfigError, ValueError)):
        S.provision_from_vision(
            ctx, _NoopLogger(), slug="dummy", pdf_path=tmp_workspace / "config" / "VisionStatement.pdf"
        )
