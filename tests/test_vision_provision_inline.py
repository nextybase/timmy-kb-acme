# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import logging
from pathlib import Path

import pytest
import yaml  # type: ignore

from tests._helpers.workspace_paths import local_workspace_dir

fitz = pytest.importorskip("fitz", reason="PyMuPDF non disponibile: installa PyMuPDF")

import semantic.vision_provision as S
from ai.types import AssistantConfig
from ai.vision_config import resolve_vision_config, resolve_vision_retention_days
from pipeline.exceptions import ConfigError
from pipeline.settings import Settings


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
    def __init__(self, repo_root_dir: Path, settings: Settings):
        self.repo_root_dir = str(repo_root_dir)
        self.settings = settings


class _NoopLogger:
    def info(self, *a, **k): ...
    def warning(self, *a, **k): ...
    def error(self, *a, **k): ...
    def exception(self, *a, **k): ...


def _vision_config_for(ctx: DummyCtx) -> AssistantConfig:
    return resolve_vision_config(ctx, override_model="test-model")


def _vision_retention_for(ctx: DummyCtx) -> int:
    return resolve_vision_retention_days(ctx)


def _write_min_config(ws: Path) -> Settings:
    cfg = ws / "config" / "config.yaml"
    cfg.write_text(
        "ai:\n"
        "  vision:\n"
        "    assistant_id_env: OBNEXT_ASSISTANT_ID\n"
        "    snapshot_retention_days: 30\n"
        "    use_kb: false\n"
        "    model: test-model\n",
        encoding="utf-8",
    )
    return Settings.load(ws)


# ---- Fixtures --------------------------------------------------------------


@pytest.fixture
def tmp_workspace(tmp_path: Path) -> Path:
    base = local_workspace_dir(tmp_path / "output", "dummy")
    (base / "config").mkdir(parents=True, exist_ok=True)
    (base / "semantic").mkdir(parents=True, exist_ok=True)
    pdf = base / "config" / "VisionStatement.pdf"
    _write_pdf(
        pdf,
        "Vision\nA\nMission\nB\nGoal\nC\nFramework etico\nD\nContesto Operativo\nE\n",
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

    def _fake_call(
        client,
        *,
        assistant_id,
        model,
        user_messages,
        strict_output=True,
        run_instructions=None,
        **kwargs,
    ):
        captured["user_messages"] = user_messages
        return output_parsed

    sample_entities = [
        {
            "id": "progetto",
            "label": "Progetto",
            "category": "operativo",
            "document_code": "PRJ-",
            "examples": ["progetto CRM"],
        }
    ]

    monkeypatch.setattr(S, "_call_assistant_json", _fake_call)
    monkeypatch.setattr(S.ontology, "get_all_entities", lambda: sample_entities)
    monkeypatch.setenv("OBNEXT_ASSISTANT_ID", "asst_dummy")

    settings = _write_min_config(tmp_workspace)
    ctx = DummyCtx(repo_root_dir=tmp_workspace, settings=settings)
    pdf_path = tmp_workspace / "config" / "VisionStatement.pdf"
    config = _vision_config_for(ctx)
    retention_days = _vision_retention_for(ctx)
    result = S.provision_from_vision_with_config(
        ctx=ctx,
        logger=_NoopLogger(),
        slug="dummy",
        pdf_path=pdf_path,
        config=config,
        retention_days=retention_days,
    )

    # File creati
    mapping = Path(result["mapping"])
    assert mapping.exists()

    # YAML parsabili e consistenti (assert meno rigidi per compat con refactor)
    mdata = yaml.safe_load(mapping.read_text(encoding="utf-8"))
    assert isinstance(mdata, dict) and "context" in mdata

    # Ha passato un unico messaggio utente coerente
    assert captured["user_messages"] and isinstance(captured["user_messages"][0]["content"], str)
    prompt = captured["user_messages"][0]["content"]
    assert "[GlobalEntities]" in prompt and "[/GlobalEntities]" in prompt
    assert '"progetto"' in prompt and "document_code" in prompt
    assert "non inventare nuove entità" in prompt


def test_invalid_model_output_raises(monkeypatch, tmp_workspace: Path):
    bad_output = {"context": {"slug": "dummy", "client_name": "Dummy"}}  # manca areas

    monkeypatch.setattr(S, "_call_assistant_json", lambda **_: bad_output)
    monkeypatch.setenv("OBNEXT_ASSISTANT_ID", "asst_dummy")

    settings = _write_min_config(tmp_workspace)
    ctx = DummyCtx(repo_root_dir=tmp_workspace, settings=settings)
    config = _vision_config_for(ctx)
    retention_days = _vision_retention_for(ctx)
    with pytest.raises(ConfigError):
        S.provision_from_vision_with_config(
            ctx=ctx,
            logger=_NoopLogger(),
            slug="dummy",
            pdf_path=tmp_workspace / "config" / "VisionStatement.pdf",
            config=config,
            retention_days=retention_days,
        )


def test_slug_mismatch_raises(monkeypatch, tmp_workspace: Path):
    # Payload con slug diverso -> deve alzare ConfigError (qualsiasi messaggio)
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
                "documents": ["verbale CdA"],
                "artefatti": [],
            },
            {
                "key": "it-data",
                "ambito": "it-data",
                "descrizione_breve": "y",
                "descrizione_dettagliata": {"include": [], "exclude": [], "artefatti_note": ""},
                "documents": ["policy sicurezza"],
                "artefatti": [],
            },
            {
                "key": "prodotto-servizio",
                "ambito": "prodotto-servizio",
                "descrizione_breve": "z",
                "descrizione_dettagliata": {"include": [], "exclude": [], "artefatti_note": ""},
                "documents": ["manuale prodotto"],
                "artefatti": [],
            },
        ],
        "system_folders": {
            "identity": {"documents": ["statuto", "visura camerale"]},
            "glossario": {"artefatti": ["glossario.yaml"]},
        },
        "metadata_policy": {"chunk_length_tokens": {"target": 800, "overlap": 100}, "mandatory_fields": []},
    }
    monkeypatch.setattr(S, "_call_assistant_json", lambda **_: mismatched)
    monkeypatch.setenv("OBNEXT_ASSISTANT_ID", "asst_dummy")
    settings = _write_min_config(tmp_workspace)
    ctx = DummyCtx(repo_root_dir=tmp_workspace, settings=settings)
    config = _vision_config_for(ctx)
    retention_days = _vision_retention_for(ctx)
    with pytest.raises(ConfigError):
        S.provision_from_vision_with_config(
            ctx=ctx,
            logger=_NoopLogger(),
            slug="dummy",
            pdf_path=tmp_workspace / "config" / "VisionStatement.pdf",
            config=config,
            retention_days=retention_days,
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
                "documents": ["report strategico"],
                "artefatti": [],
            },
            {
                "key": "b",
                "ambito": "y",
                "descrizione_breve": "d",
                "descrizione_dettagliata": {"include": [], "exclude": [], "artefatti_note": ""},
                "documents": ["piano operativo"],
                "artefatti": [],
            },
            {
                "key": "c",
                "ambito": "z",
                "descrizione_breve": "d",
                "descrizione_dettagliata": {"include": [], "exclude": [], "artefatti_note": ""},
                "documents": ["linee guida"],
                "artefatti": [],
            },
        ],
        # <-- system_folders mancante di proposito
        "metadata_policy": {"chunk_length_tokens": {"target": 800, "overlap": 100}, "mandatory_fields": []},
    }
    monkeypatch.setattr(S, "_call_assistant_json", lambda **_: out)
    monkeypatch.setenv("OBNEXT_ASSISTANT_ID", "asst_dummy")
    settings = _write_min_config(tmp_workspace)
    ctx = DummyCtx(repo_root_dir=tmp_workspace, settings=settings)
    config = _vision_config_for(ctx)
    retention_days = _vision_retention_for(ctx)
    with pytest.raises((ConfigError, ValueError)):
        S.provision_from_vision_with_config(
            ctx=ctx,
            logger=_NoopLogger(),
            slug="dummy",
            pdf_path=tmp_workspace / "config" / "VisionStatement.pdf",
            config=config,
            retention_days=retention_days,
        )
