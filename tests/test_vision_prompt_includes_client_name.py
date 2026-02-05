# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from pathlib import Path

from tests._helpers.workspace_paths import local_workspace_dir

import pytest

import semantic.vision_provision as S
from ai.vision_config import resolve_vision_config, resolve_vision_retention_days

fitz = pytest.importorskip("fitz", reason="PyMuPDF non disponibile: installa PyMuPDF")


class DummyCtx:
    def __init__(self, repo_root_dir: Path, client_name: str | None = None):
        self.repo_root_dir = str(repo_root_dir)
        self.client_name = client_name
        self.settings = {"ai": {"vision": {"assistant_id_env": "OBNEXT_ASSISTANT_ID", "snapshot_retention_days": 30}}}


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
    base = local_workspace_dir(tmp_path / "output", "dummy")
    (base / "config").mkdir(parents=True, exist_ok=True)
    (base / "semantic").mkdir(parents=True, exist_ok=True)
    pdf = base / "config" / "VisionStatement.pdf"
    # PDF con le 6 sezioni obbligatorie (intestazioni a inizio riga)
    _write_pdf(
        pdf,
        "Vision\nA\nMission\nB\nGoal\nC\nFramework etico\nD\nContesto Operativo\nE\n",
    )
    return base


def test_prompt_contains_client_name(monkeypatch, tmp_ws: Path):
    slug = "dummy"
    ctx = DummyCtx(repo_root_dir=tmp_ws, client_name="Dummy S.p.A.")
    seen = {"user_messages": None}

    # Finto assistant: payload conforme al contratto (≥3 aree + system_folders + metadata_policy)
    def _fake_call(client, *, assistant_id, model, user_messages, **kwargs):
        seen["user_messages"] = user_messages
        return {
            "version": "1.0-beta",
            "source": "vision",
            "status": "ok",
            "context": {"slug": slug, "client_name": ctx.client_name},
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

    monkeypatch.setenv("OBNEXT_ASSISTANT_ID", "asst_dummy")
    monkeypatch.delenv("OPENAI_FORCE_HTTPX", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "dummy-key")
    monkeypatch.setattr(S, "make_openai_client", lambda: object())
    # Non patchiamo _extract_pdf_text: il fixture ha generato un PDF valido con le 6 sezioni
    monkeypatch.setattr(S, "_call_assistant_json", _fake_call)

    config = resolve_vision_config(ctx, override_model="test-model")
    retention_days = resolve_vision_retention_days(ctx)
    S.provision_from_vision_with_config(
        ctx,
        S.logging.getLogger("noop"),
        slug=slug,
        pdf_path=tmp_ws / "config" / "VisionStatement.pdf",
        config=config,
        retention_days=retention_days,
    )

    # Verifica che il client_name sia stato incluso nel prompt inviato all'assistente
    msgs = seen["user_messages"] or []
    assert any("client_name: Dummy S.p.A." in (m.get("content") or "") for m in msgs)
