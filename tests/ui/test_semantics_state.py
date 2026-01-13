# SPDX-License-Identifier: GPL-3.0-or-later
# tests/ui/test_semantics_state.py

from __future__ import annotations

import contextlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from pipeline.exceptions import ConfigError


def _patch_streamlit_semantics(monkeypatch, sem) -> None:
    """Rende innocui gli side-effect UI in test."""

    @contextlib.contextmanager
    def _spinner(_msg: str):
        yield

    # patch dei metodi usati nei runner
    monkeypatch.setattr(sem.st, "spinner", _spinner, raising=False)
    monkeypatch.setattr(sem.st, "success", lambda *a, **k: None, raising=False)
    monkeypatch.setattr(sem.st, "button", lambda *a, **k: False, raising=False)


def _write_qa_evidence(path: Path, *, status: str = "pass") -> None:
    payload = {
        "schema_version": 1,
        "qa_status": status,
        "checks_executed": ["pre-commit run --all-files", "pytest -q"],
        "timestamp": "2025-01-01T00:00:00+00:00",
    }
    path.write_text(json.dumps(payload) + "\n", encoding="utf-8")


def _write_qa_payload(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload) + "\n", encoding="utf-8")


def _mk_semantics_ctx(monkeypatch, sem, *, tmp_path: Path, log_dir: Path) -> list[tuple[str, dict | None]]:
    _patch_streamlit_semantics(monkeypatch, sem)
    monkeypatch.setattr(sem.st, "error", lambda *a, **k: None, raising=False)
    monkeypatch.setattr(sem.st, "caption", lambda *a, **k: None, raising=False)
    monkeypatch.setattr(sem, "get_state", lambda slug: "arricchito")
    monkeypatch.setattr(sem, "raw_ready", lambda slug: (True, tmp_path / "raw"))
    monkeypatch.setattr(sem, "tagging_ready", lambda slug: (True, tmp_path / "semantic"))
    events: list[tuple[str, dict | None]] = []
    monkeypatch.setattr(
        sem,
        "log_gate_event",
        lambda logger, event_name, *, fields=None: events.append((event_name, fields)),
    )
    monkeypatch.setattr(
        sem,
        "_make_ctx_and_logger",
        lambda slug: (
            SimpleNamespace(base_dir=tmp_path),
            SimpleNamespace(set_step_status=lambda *a, **k: None),
            SimpleNamespace(base_dir=tmp_path, book_dir=tmp_path / "book", log_dir=log_dir),
        ),
    )
    return events


def test_semantic_constants_allow_entry_from_pronto():
    from ui.constants import SEMANTIC_ENTRY_STATES, SEMANTIC_READY_STATES

    assert "pronto" not in SEMANTIC_READY_STATES
    assert "pronto" in SEMANTIC_ENTRY_STATES


def test_semantic_constants_expected_membership():
    from ui.constants import KNOWN_CLIENT_STATES, SEMANTIC_ENTRY_STATES, SEMANTIC_READY_STATES

    assert SEMANTIC_READY_STATES == {"arricchito", "finito"}
    assert SEMANTIC_ENTRY_STATES == {"pronto", "arricchito", "finito"}
    assert SEMANTIC_ENTRY_STATES.issubset(KNOWN_CLIENT_STATES)
    assert "nuovo" in KNOWN_CLIENT_STATES and "nuovo" not in SEMANTIC_ENTRY_STATES


def test_semantics_page_uses_entry_states_for_allowed_states(monkeypatch):
    import importlib

    sem = importlib.import_module("ui.pages.semantics")
    from ui.constants import SEMANTIC_ENTRY_STATES

    assert getattr(sem, "ALLOWED_STATES", None) == SEMANTIC_ENTRY_STATES


def test_semantics_flow_convert_enrich_summary(monkeypatch, tmp_path):
    import ui.pages.semantics as sem

    _patch_streamlit_semantics(monkeypatch, sem)
    sem._ACTION_RUNS.clear()

    state_log: list[str] = []
    state = {"value": "pronto"}

    monkeypatch.setattr(sem, "get_state", lambda slug: state["value"])

    def _set_state(slug: str, value: str) -> None:
        state["value"] = value
        state_log.append(value)

    monkeypatch.setattr(sem, "set_state", _set_state)

    reset_calls: list[str] = []

    readiness = [True, True, False, True, True, True, True]
    ready_calls: list[bool] = []
    reset_flag = {"pending": False}

    def _raw_ready(slug: str):
        if not reset_flag["pending"] and ready_calls:
            raise AssertionError("raw_ready chiamato senza reset gating precedente")
        reset_flag["pending"] = False
        value = readiness.pop(0)
        ready_calls.append(value)
        return value, tmp_path / "raw"

    monkeypatch.setattr(sem, "raw_ready", _raw_ready)
    monkeypatch.setattr(sem, "tagging_ready", lambda slug: (True, tmp_path / "semantic"))

    log_records: list[tuple[str, dict]] = []

    def _logger_info(msg: str, **kwargs: object) -> None:
        log_records.append((msg, kwargs))

    def _logger_warning(*a: object, **k: object) -> None:
        pass

    def _convert(ctx, logger, slug=None):
        logger.info("convert", extra={"slug": slug})
        return ["a.md"]

    monkeypatch.setattr(sem, "convert_markdown", _convert)
    monkeypatch.setattr(sem, "get_paths", lambda slug: {"base": tmp_path})
    monkeypatch.setattr(sem, "require_reviewed_vocab", lambda base_dir, logger, *, slug: {"tag": True})

    def _enrich(ctx, logger, vocab, slug=None, **kwargs):
        logger.info("enrich", extra={"slug": slug})
        return ["a.md"]

    monkeypatch.setattr(sem, "enrich_frontmatter", _enrich)

    def _write_summary(ctx, logger, slug=None):
        logger.info("summary", extra={"slug": slug})

    monkeypatch.setattr(sem, "write_summary_and_readme", _write_summary)

    qa_dir = tmp_path / "logs"
    qa_dir.mkdir(parents=True, exist_ok=True)
    _write_qa_evidence(qa_dir / sem.QA_EVIDENCE_FILENAME)

    def _ctx_logger(_slug: str):
        logger = SimpleNamespace(info=_logger_info, warning=_logger_warning)
        layout = SimpleNamespace(base_dir=tmp_path, book_dir=tmp_path / "book", log_dir=qa_dir)
        return SimpleNamespace(base_dir=tmp_path), logger, layout

    monkeypatch.setattr(sem, "_make_ctx_and_logger", _ctx_logger)

    def _counting_reset(slug: str) -> None:
        reset_calls.append(slug)
        reset_flag["pending"] = True

    monkeypatch.setattr(sem, "_reset_gating_cache", _counting_reset)

    sem._client_state = "pronto"  # type: ignore[attr-defined]
    sem._raw_ready = True  # type: ignore[attr-defined]

    sem.raw_ready("dummy")

    for runner in (sem._run_convert, sem._run_enrich, sem._run_summary):
        reset_flag["pending"] = True
        runner("dummy")
        sem.raw_ready("dummy")

    assert state["value"] == "finito"
    assert reset_calls == ["dummy", "dummy", "dummy"]
    assert state_log == ["pronto", "arricchito", "finito"]
    assert ready_calls == [True, True, False, True, True, True, True]
    # Promozioni e azioni loggate
    assert {"convert", "enrich", "summary", "ui.semantics.state_promoted"} <= {msg for msg, _ in log_records}
    assert all(record[1].get("extra", {}).get("slug") == "dummy" for record in log_records if record[1].get("extra"))


def test_semantics_message_string_matches_docs():
    from pathlib import Path

    from ui.constants import SEMANTIC_GATING_MESSAGE

    repo_root = Path(__file__).resolve().parents[2]
    docs_text = (repo_root / "docs/developer/streamlit_ui.md").read_text(encoding="utf-8")
    assert SEMANTIC_GATING_MESSAGE in docs_text, SEMANTIC_GATING_MESSAGE


def test_semantic_gating_helper_blocks_without_raw(monkeypatch):
    import ui.pages.semantics as sem

    monkeypatch.setattr(sem, "get_state", lambda slug: "pronto")
    monkeypatch.setattr(sem, "raw_ready", lambda slug: (False, None))
    monkeypatch.setattr(sem, "tagging_ready", lambda slug: (True, None))

    with pytest.raises(ConfigError, match="Semantica non disponibile"):
        sem._require_semantic_gating("dummy")


def test_run_actions_honor_headless_gating(monkeypatch):
    import ui.pages.semantics as sem

    monkeypatch.setattr(sem, "get_state", lambda slug: "nuovo")
    monkeypatch.setattr(sem, "raw_ready", lambda slug: (False, None))
    monkeypatch.setattr(sem, "tagging_ready", lambda slug: (True, None))

    for runner in (sem._run_convert, sem._run_enrich, sem._run_summary):
        with pytest.raises(ConfigError, match="Semantica non disponibile"):
            runner("dummy")


def test_semantics_gating_uses_ssot_constants():
    """
    Il gating deve usare la costante SSoT `SEMANTIC_ENTRY_STATES`
    (non una whitelist hardcoded locale).
    """
    import ui.pages.semantics as sem
    from ui.constants import SEMANTIC_ENTRY_STATES

    # ALLOWED_STATES è valorizzata a livello modulo == SEMANTIC_ENTRY_STATES
    assert set(sem.ALLOWED_STATES) == set(SEMANTIC_ENTRY_STATES)
    # cache invalidata dopo il test per evitare side effect
    sem._GATE_CACHE.clear()


def test_gate_cache_reuses_result(monkeypatch):
    import ui.pages.semantics as sem

    calls = {"count": 0}

    def _raw_ready(slug: str):
        calls["count"] += 1
        return True, Path("raw")

    monkeypatch.setattr(sem, "get_state", lambda slug: "pronto")
    monkeypatch.setattr(sem, "raw_ready", _raw_ready)
    monkeypatch.setattr(sem, "tagging_ready", lambda slug: (True, Path("semantic")))
    sem._GATE_CACHE.clear()

    # First call should populate cache (calls==1)
    sem._require_semantic_gating("dummy")
    sem._require_semantic_gating("dummy", reuse_last=True)

    assert calls["count"] == 2
    sem._GATE_CACHE.clear()


def test_gate_cache_rechecks_raw_if_removed(monkeypatch, tmp_path):
    import ui.pages.semantics as sem

    states: list[tuple[bool, Path | None]] = [(True, tmp_path / "raw"), (False, None)]

    def _raw(slug: str):
        return states.pop(0)

    monkeypatch.setattr(sem, "get_state", lambda slug: "pronto")
    monkeypatch.setattr(sem, "raw_ready", _raw)
    monkeypatch.setattr(sem, "tagging_ready", lambda slug: (True, tmp_path / "semantic"))
    sem._GATE_CACHE.clear()

    sem._require_semantic_gating("dummy")
    with pytest.raises(ConfigError, match="Semantica non disponibile"):
        sem._require_semantic_gating("dummy", reuse_last=True)
    sem._GATE_CACHE.clear()


def test_gate_cache_updates_raw_path(monkeypatch, tmp_path):
    import ui.pages.semantics as sem

    responses: list[tuple[bool, Path | None]] = [
        (True, Path("raw")),
        (True, tmp_path / "raw-v2"),
    ]

    def _raw(slug: str):
        return responses.pop(0)

    monkeypatch.setattr(sem, "get_state", lambda slug: "pronto")
    monkeypatch.setattr(sem, "raw_ready", _raw)
    monkeypatch.setattr(sem, "tagging_ready", lambda slug: (True, tmp_path / "semantic"))
    sem._GATE_CACHE.clear()

    sem._require_semantic_gating("dummy")
    sem._require_semantic_gating("dummy", reuse_last=True)

    cache_key = "dummy"
    assert cache_key in sem._GATE_CACHE
    assert sem._GATE_CACHE[cache_key][3] == tmp_path / "raw-v2"
    sem._GATE_CACHE.clear()


def test_run_enrich_promotes_state_to_arricchito(monkeypatch, tmp_path):
    """
    Dopo l'azione 'Arricchisci frontmatter' lo stato cliente passa ad 'arricchito'.
    """
    import ui.pages.semantics as sem

    _patch_streamlit_semantics(monkeypatch, sem)

    # cattura delle promozioni di stato
    state_calls: list[tuple[str, str]] = []
    monkeypatch.setattr(sem, "set_state", lambda slug, s: state_calls.append((slug, s)))

    # gating helper
    monkeypatch.setattr(sem, "get_state", lambda slug: "pronto")
    monkeypatch.setattr(sem, "raw_ready", lambda slug: (True, tmp_path / "raw"))
    monkeypatch.setattr(sem, "tagging_ready", lambda slug: (True, tmp_path / "semantic"))

    # ctx/logger minimi
    def _mk_ctx_and_logger(slug: str):
        layout = SimpleNamespace(base_dir=tmp_path, book_dir=tmp_path / "book")
        return SimpleNamespace(base_dir=tmp_path), SimpleNamespace(name="test-logger"), layout

    monkeypatch.setattr(sem, "_make_ctx_and_logger", _mk_ctx_and_logger)

    # get_paths() deve restituire un dizionario con 'base'
    monkeypatch.setattr(sem, "get_paths", lambda slug: {"base": tmp_path})

    # vocabolario e arricchimento simulati
    monkeypatch.setattr(sem, "require_reviewed_vocab", lambda base_dir, logger, *, slug: {"ok": True})
    monkeypatch.setattr(
        sem,
        "enrich_frontmatter",
        lambda ctx, logger, vocab, slug, **kwargs: ["file1.md", "file2.md"],
    )

    sem._run_enrich("dummy-srl")

    assert state_calls, "set_state non è stato chiamato"
    assert state_calls[-1] == ("dummy-srl", "arricchito")


def test_run_enrich_errors_when_vocab_missing(monkeypatch, tmp_path):
    """La UI blocca l'arricchimento se il vocabolario canonico è assente."""
    import ui.pages.semantics as sem

    _patch_streamlit_semantics(monkeypatch, sem)

    errors: list[str] = []
    monkeypatch.setattr(
        sem.st,
        "error",
        lambda msg, **_: errors.append(msg),
        raising=False,
    )
    captions: list[str] = []
    monkeypatch.setattr(sem.st, "caption", lambda msg, **_: captions.append(msg), raising=False)
    links: list[tuple[str, dict[str, object]]] = []
    monkeypatch.setattr(
        sem.st,
        "page_link",
        lambda page, **kwargs: links.append((page, kwargs)),
        raising=False,
    )

    state_calls: list[tuple[str, str]] = []
    monkeypatch.setattr(sem, "set_state", lambda slug, s: state_calls.append((slug, s)))

    class _Logger:
        def __init__(self) -> None:
            self.warning_calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

        def warning(self, *args: object, **kwargs: object) -> None:
            self.warning_calls.append((args, kwargs))

        def info(self, *args: object, **kwargs: object) -> None:
            pass

    logger = _Logger()

    def _mk_ctx_and_logger(slug: str):
        layout = SimpleNamespace(base_dir=tmp_path, book_dir=tmp_path / "book")
        return SimpleNamespace(base_dir=tmp_path), logger, layout

    monkeypatch.setattr(sem, "_make_ctx_and_logger", _mk_ctx_and_logger)
    monkeypatch.setattr(sem, "get_paths", lambda slug: {"base": tmp_path})
    monkeypatch.setattr(sem, "get_state", lambda slug: "pronto")
    monkeypatch.setattr(sem, "raw_ready", lambda slug: (True, tmp_path / "raw"))
    monkeypatch.setattr(sem, "tagging_ready", lambda slug: (True, tmp_path / "semantic"))
    monkeypatch.setattr(
        sem,
        "require_reviewed_vocab",
        lambda base_dir, logger, *, slug: (_ for _ in ()).throw(
            ConfigError("Vocabolario canonico assente.", slug=slug)
        ),
    )

    sem._run_enrich("dummy-srl")

    assert errors and "vocabolario canonico assente" in errors[0].lower()
    assert captions and "estrazione tag" in captions[0].lower()
    assert state_calls == [("dummy-srl", "pronto")]
    assert links and links[-1][0] == sem.PagePaths.MANAGE


def test_run_summary_promotes_state_to_finito(monkeypatch, tmp_path):
    """
    Dopo 'Genera SUMMARY/README' lo stato cliente passa a 'finito'.
    """
    import ui.pages.semantics as sem

    _patch_streamlit_semantics(monkeypatch, sem)
    sem._ACTION_RUNS.clear()

    # cattura delle promozioni di stato
    state_calls: list[tuple[str, str]] = []
    monkeypatch.setattr(sem, "set_state", lambda slug, s: state_calls.append((slug, s)))

    # ctx/logger minimi
    qa_dir = tmp_path / "logs"
    qa_dir.mkdir(parents=True, exist_ok=True)
    _write_qa_evidence(qa_dir / sem.QA_EVIDENCE_FILENAME)

    def _mk_ctx_and_logger(slug: str):
        layout = SimpleNamespace(base_dir=tmp_path, book_dir=tmp_path / "book", log_dir=qa_dir)
        return SimpleNamespace(base_dir=tmp_path), SimpleNamespace(name="test-logger"), layout

    monkeypatch.setattr(sem, "_make_ctx_and_logger", _mk_ctx_and_logger)

    monkeypatch.setattr(sem, "get_state", lambda slug: "arricchito")
    monkeypatch.setattr(sem, "raw_ready", lambda slug: (True, tmp_path / "raw"))
    monkeypatch.setattr(sem, "tagging_ready", lambda slug: (True, tmp_path / "semantic"))

    # writer simulato
    monkeypatch.setattr(sem, "write_summary_and_readme", lambda ctx, logger, slug: None)

    sem._run_summary("dummy-srl")

    assert state_calls, "set_state non è stato chiamato"
    assert state_calls[-1] == ("dummy-srl", "finito")


def test_run_enrich_blocks_when_tagging_not_ready(monkeypatch, tmp_path):
    import ui.pages.semantics as sem

    _patch_streamlit_semantics(monkeypatch, sem)

    errors: list[str] = []
    captions: list[str] = []
    monkeypatch.setattr(sem.st, "error", lambda msg, **_: errors.append(msg), raising=False)
    monkeypatch.setattr(sem.st, "caption", lambda msg, **_: captions.append(msg), raising=False)
    state_calls: list[tuple[str, str]] = []
    monkeypatch.setattr(sem, "set_state", lambda slug, s: state_calls.append((slug, s)))

    monkeypatch.setattr(sem, "tagging_ready", lambda slug: (False, tmp_path / "semantic"))
    monkeypatch.setattr(sem, "raw_ready", lambda slug: (True, tmp_path / "raw"))
    monkeypatch.setattr(sem, "get_state", lambda slug: "pronto")

    sem._run_enrich("dummy")

    assert errors and "bloccato" in errors[0].lower()
    assert state_calls == []


def test_run_summary_blocks_without_prerequisites(monkeypatch, tmp_path):
    import ui.pages.semantics as sem

    _patch_streamlit_semantics(monkeypatch, sem)
    errors: list[str] = []
    captions: list[str] = []
    monkeypatch.setattr(sem.st, "error", lambda msg, **_: errors.append(msg), raising=False)
    monkeypatch.setattr(sem.st, "caption", lambda msg, **_: captions.append(msg), raising=False)
    state_calls: list[tuple[str, str]] = []
    monkeypatch.setattr(sem, "set_state", lambda slug, s: state_calls.append((slug, s)))

    monkeypatch.setattr(sem, "raw_ready", lambda slug: (False, tmp_path / "raw"))
    monkeypatch.setattr(sem, "tagging_ready", lambda slug: (False, tmp_path / "semantic"))
    monkeypatch.setattr(sem, "get_state", lambda slug: "arricchito")

    sem._run_summary("dummy")

    assert errors and "bloccata" in errors[0].lower()
    assert state_calls == []


def test_update_client_state_emits_pass_event(monkeypatch):
    import ui.pages.semantics as sem

    events: list[str] = []

    class _Logger:
        def info(self, msg: str, *, extra: dict | None = None) -> None:  # type: ignore[override]
            events.append(msg)

    monkeypatch.setattr(sem, "set_state", lambda slug, state: None)
    sem._update_client_state("dummy", "pronto", _Logger())

    assert "ui.semantics.state_promoted" in events


def test_run_summary_requires_qa_marker(monkeypatch, tmp_path):
    import ui.pages.semantics as sem

    _patch_streamlit_semantics(monkeypatch, sem)
    sem._ACTION_RUNS.clear()

    errors: list[str] = []
    captions: list[str] = []
    monkeypatch.setattr(sem.st, "error", lambda msg, **_: errors.append(msg), raising=False)
    monkeypatch.setattr(sem.st, "caption", lambda msg, **_: captions.append(msg), raising=False)

    state_calls: list[tuple[str, str]] = []
    monkeypatch.setattr(sem, "set_state", lambda slug, s: state_calls.append((slug, s)))

    qa_dir = tmp_path / "logs"
    qa_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(sem, "_qa_evidence_path", lambda layout: qa_dir / sem.QA_EVIDENCE_FILENAME)

    events: list[tuple[str, dict | None]] = []
    monkeypatch.setattr(
        sem, "log_gate_event", lambda logger, event_name, *, fields=None: events.append((event_name, fields))
    )

    def _mk_ctx(slug: str):
        layout = SimpleNamespace(base_dir=tmp_path, book_dir=tmp_path / "book", log_dir=qa_dir)
        return SimpleNamespace(base_dir=tmp_path), SimpleNamespace(set_step_status=lambda *a, **k: None), layout

    monkeypatch.setattr(sem, "_make_ctx_and_logger", _mk_ctx)
    monkeypatch.setattr(sem, "get_state", lambda slug: "arricchito")
    monkeypatch.setattr(sem, "raw_ready", lambda slug: (True, tmp_path / "raw"))
    monkeypatch.setattr(sem, "tagging_ready", lambda slug: (True, tmp_path / "semantic"))

    called: list[str] = []
    monkeypatch.setattr(sem, "write_summary_and_readme", lambda ctx, logger, slug: called.append(slug))

    sem._run_summary("dummy")

    assert called == []
    assert state_calls == []
    assert errors and "QA Gate" in errors[0]
    assert events and events[-1][0] == "qa_gate_failed"


def test_run_summary_blocks_when_qa_missing(monkeypatch, tmp_path):
    import ui.pages.semantics as sem

    qa_dir = tmp_path / "logs"
    qa_dir.mkdir(parents=True, exist_ok=True)
    events = _mk_semantics_ctx(monkeypatch, sem, tmp_path=tmp_path, log_dir=qa_dir)

    state_calls: list[tuple[str, str]] = []
    monkeypatch.setattr(sem, "set_state", lambda slug, s: state_calls.append((slug, s)))
    monkeypatch.setattr(sem, "write_summary_and_readme", lambda ctx, logger, slug: None)

    sem._run_summary("dummy")

    assert state_calls == []
    assert any(evt[0] == "qa_gate_failed" and evt[1].get("reason") == "qa_evidence_missing" for evt in events if evt[1])


def test_run_summary_blocks_when_qa_invalid_json(monkeypatch, tmp_path):
    import ui.pages.semantics as sem

    qa_dir = tmp_path / "logs"
    qa_dir.mkdir(parents=True, exist_ok=True)
    (qa_dir / sem.QA_EVIDENCE_FILENAME).write_text("{not-json", encoding="utf-8")
    events = _mk_semantics_ctx(monkeypatch, sem, tmp_path=tmp_path, log_dir=qa_dir)

    state_calls: list[tuple[str, str]] = []
    monkeypatch.setattr(sem, "set_state", lambda slug, s: state_calls.append((slug, s)))
    monkeypatch.setattr(sem, "write_summary_and_readme", lambda ctx, logger, slug: None)

    sem._run_summary("dummy")

    assert state_calls == []
    assert any(evt[0] == "qa_gate_failed" and evt[1].get("reason") == "qa_evidence_invalid" for evt in events if evt[1])


def test_run_summary_blocks_when_qa_status_fail(monkeypatch, tmp_path):
    import ui.pages.semantics as sem

    qa_dir = tmp_path / "logs"
    qa_dir.mkdir(parents=True, exist_ok=True)
    _write_qa_evidence(qa_dir / sem.QA_EVIDENCE_FILENAME, status="fail")
    events = _mk_semantics_ctx(monkeypatch, sem, tmp_path=tmp_path, log_dir=qa_dir)

    state_calls: list[tuple[str, str]] = []
    monkeypatch.setattr(sem, "set_state", lambda slug, s: state_calls.append((slug, s)))
    monkeypatch.setattr(sem, "write_summary_and_readme", lambda ctx, logger, slug: None)

    sem._run_summary("dummy")

    assert state_calls == []
    assert any(evt[0] == "qa_gate_failed" and evt[1].get("reason") == "qa_evidence_failed" for evt in events if evt[1])


def test_run_summary_blocks_on_schema_version_mismatch(monkeypatch, tmp_path):
    import ui.pages.semantics as sem

    qa_dir = tmp_path / "logs"
    qa_dir.mkdir(parents=True, exist_ok=True)
    _write_qa_payload(
        qa_dir / sem.QA_EVIDENCE_FILENAME,
        {
            "schema_version": 2,
            "qa_status": "pass",
            "checks_executed": ["pytest -q"],
            "timestamp": "2025-01-01T00:00:00+00:00",
        },
    )
    events = _mk_semantics_ctx(monkeypatch, sem, tmp_path=tmp_path, log_dir=qa_dir)

    state_calls: list[tuple[str, str]] = []
    monkeypatch.setattr(sem, "set_state", lambda slug, s: state_calls.append((slug, s)))
    monkeypatch.setattr(sem, "write_summary_and_readme", lambda ctx, logger, slug: None)

    sem._run_summary("dummy")

    assert state_calls == []
    assert any(evt[0] == "qa_gate_failed" and evt[1].get("reason") == "qa_evidence_invalid" for evt in events if evt[1])


def test_run_summary_blocks_on_empty_checks(monkeypatch, tmp_path):
    import ui.pages.semantics as sem

    qa_dir = tmp_path / "logs"
    qa_dir.mkdir(parents=True, exist_ok=True)
    _write_qa_payload(
        qa_dir / sem.QA_EVIDENCE_FILENAME,
        {
            "schema_version": 1,
            "qa_status": "pass",
            "checks_executed": [],
            "timestamp": "2025-01-01T00:00:00+00:00",
        },
    )
    events = _mk_semantics_ctx(monkeypatch, sem, tmp_path=tmp_path, log_dir=qa_dir)

    state_calls: list[tuple[str, str]] = []
    monkeypatch.setattr(sem, "set_state", lambda slug, s: state_calls.append((slug, s)))
    monkeypatch.setattr(sem, "write_summary_and_readme", lambda ctx, logger, slug: None)

    sem._run_summary("dummy")

    assert state_calls == []
    assert any(evt[0] == "qa_gate_failed" and evt[1].get("reason") == "qa_evidence_invalid" for evt in events if evt[1])


def test_retry_logged_and_gates_checked(monkeypatch, tmp_path):
    import ui.pages.semantics as sem

    _patch_streamlit_semantics(monkeypatch, sem)
    sem._ACTION_RUNS.clear()

    gate_calls = {"raw": 0}
    monkeypatch.setattr(sem, "get_state", lambda slug: "pronto")

    def _raw_ready(slug: str):
        gate_calls["raw"] += 1
        return True, tmp_path / "raw"

    monkeypatch.setattr(sem, "raw_ready", _raw_ready)
    monkeypatch.setattr(sem, "tagging_ready", lambda slug: (True, tmp_path / "semantic"))

    events: list[tuple[str, dict | None]] = []
    monkeypatch.setattr(
        sem, "log_gate_event", lambda logger, event_name, *, fields=None: events.append((event_name, fields))
    )

    def _mk_ctx(slug: str):
        layout = SimpleNamespace(base_dir=tmp_path, book_dir=tmp_path / "book", log_dir=tmp_path / "logs")
        return SimpleNamespace(base_dir=tmp_path, set_step_status=lambda *a, **k: None), SimpleNamespace(), layout

    monkeypatch.setattr(sem, "_make_ctx_and_logger", _mk_ctx)
    monkeypatch.setattr(sem, "enrich_frontmatter", lambda ctx, logger, vocab, slug, **kwargs: [])
    monkeypatch.setattr(sem, "require_reviewed_vocab", lambda base_dir, logger, *, slug: {"tag": True})

    sem._run_enrich("dummy")
    sem._run_enrich("dummy")

    assert gate_calls["raw"] == 2
    assert any(evt[0] == "qa_gate_retry" and evt[1].get("action_id") == "enrich" for evt in events if evt[1])


def test_gating_failure_reasons_are_deterministic(monkeypatch, tmp_path):
    import ui.pages.semantics as sem

    sem._ACTION_RUNS.clear()
    events: list[tuple[str, dict | None]] = []
    monkeypatch.setattr(
        sem, "log_gate_event", lambda logger, event_name, *, fields=None: events.append((event_name, fields))
    )

    monkeypatch.setattr(sem, "get_state", lambda slug: "pronto")
    monkeypatch.setattr(sem, "raw_ready", lambda slug: (False, tmp_path / "raw"))
    monkeypatch.setattr(sem, "tagging_ready", lambda slug: (True, tmp_path / "semantic"))

    with pytest.raises(ConfigError):
        sem._require_semantic_gating("dummy")

    assert any(evt[0] == "evidence_gate_blocked" and evt[1].get("reason") == "raw_missing" for evt in events if evt[1])

    events.clear()

    _patch_streamlit_semantics(monkeypatch, sem)
    qa_dir = tmp_path / "logs"
    qa_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(sem, "_qa_evidence_path", lambda layout: qa_dir / sem.QA_EVIDENCE_FILENAME)
    monkeypatch.setattr(sem, "raw_ready", lambda slug: (True, tmp_path / "raw"))
    monkeypatch.setattr(sem, "tagging_ready", lambda slug: (True, tmp_path / "semantic"))
    monkeypatch.setattr(sem, "get_state", lambda slug: "arricchito")

    def _mk_ctx(slug: str):
        layout = SimpleNamespace(base_dir=tmp_path, book_dir=tmp_path / "book", log_dir=qa_dir)
        return SimpleNamespace(base_dir=tmp_path), SimpleNamespace(set_step_status=lambda *a, **k: None), layout

    monkeypatch.setattr(sem, "_make_ctx_and_logger", _mk_ctx)
    monkeypatch.setattr(sem, "write_summary_and_readme", lambda ctx, logger, slug: None)

    sem._run_summary("dummy")

    assert any(evt[0] == "qa_gate_failed" and evt[1].get("reason") == "qa_evidence_missing" for evt in events if evt[1])
