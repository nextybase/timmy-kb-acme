# SPDX-License-Identifier: GPL-3.0-or-later
# tests/ui/test_semantics_state.py

from __future__ import annotations

import contextlib
from types import SimpleNamespace


def _patch_streamlit_semantics(monkeypatch, sem) -> None:
    """Rende innocui gli side-effect UI in test."""

    @contextlib.contextmanager
    def _spinner(_msg: str):
        yield

    # patch dei metodi usati nei runner
    monkeypatch.setattr(sem.st, "spinner", _spinner, raising=False)
    monkeypatch.setattr(sem.st, "success", lambda *a, **k: None, raising=False)
    monkeypatch.setattr(sem.st, "button", lambda *a, **k: False, raising=False)


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

    state_log: list[str] = []
    state = {"value": "pronto"}

    monkeypatch.setattr(sem, "get_state", lambda slug: state["value"])

    def _set_state(slug: str, value: str) -> None:
        state["value"] = value
        state_log.append(value)

    monkeypatch.setattr(sem, "set_state", _set_state)

    reset_calls: list[str] = []
    monkeypatch.setattr(sem, "_reset_gating_cache", lambda slug: reset_calls.append(slug))

    monkeypatch.setattr(sem, "has_raw_pdfs", lambda slug: (True, tmp_path / "raw"))
    monkeypatch.setattr(sem, "convert_markdown", lambda ctx, logger, slug=None: ["a.md"])
    monkeypatch.setattr(sem, "get_paths", lambda slug: {"base": tmp_path})
    monkeypatch.setattr(sem, "load_reviewed_vocab", lambda base_dir, logger: {"tag": True})
    monkeypatch.setattr(
        sem,
        "enrich_frontmatter",
        lambda ctx, logger, vocab, slug=None, **kwargs: ["a.md"],
    )
    monkeypatch.setattr(sem, "write_summary_and_readme", lambda ctx, logger, slug=None: None)

    def _ctx_logger(_slug: str):
        logger = SimpleNamespace(info=lambda *a, **k: None, warning=lambda *a, **k: None)
        return SimpleNamespace(base_dir=tmp_path), logger

    monkeypatch.setattr(sem, "_make_ctx_and_logger", _ctx_logger)

    sem._client_state = "pronto"  # type: ignore[attr-defined]
    sem._raw_ready = True  # type: ignore[attr-defined]

    sem._run_convert("dummy")
    assert state["value"] == "pronto"

    sem._run_enrich("dummy")
    assert state["value"] == "arricchito"

    sem._run_summary("dummy")
    assert state["value"] == "finito"

    assert reset_calls == ["dummy", "dummy", "dummy"]
    assert state_log == ["pronto", "arricchito", "finito"]


def test_semantics_gating_uses_ssot_constants():
    """
    Il gating deve usare la costante SSoT `SEMANTIC_ENTRY_STATES`
    (non una whitelist hardcoded locale).
    """
    import ui.pages.semantics as sem
    from ui.constants import SEMANTIC_ENTRY_STATES

    # ALLOWED_STATES è valorizzata a livello modulo == SEMANTIC_ENTRY_STATES
    assert set(sem.ALLOWED_STATES) == set(SEMANTIC_ENTRY_STATES)


def test_run_enrich_promotes_state_to_arricchito(monkeypatch, tmp_path):
    """
    Dopo l'azione 'Arricchisci frontmatter' lo stato cliente passa ad 'arricchito'.
    """
    import ui.pages.semantics as sem

    _patch_streamlit_semantics(monkeypatch, sem)

    # cattura delle promozioni di stato
    state_calls: list[tuple[str, str]] = []
    monkeypatch.setattr(sem, "set_state", lambda slug, s: state_calls.append((slug, s)))

    # ctx/logger minimi
    def _mk_ctx_and_logger(slug: str):
        return SimpleNamespace(base_dir=tmp_path), SimpleNamespace(name="test-logger")

    monkeypatch.setattr(sem, "_make_ctx_and_logger", _mk_ctx_and_logger)

    # get_paths() deve restituire un dizionario con 'base'
    monkeypatch.setattr(sem, "get_paths", lambda slug: {"base": tmp_path})

    # vocabolario e arricchimento simulati
    monkeypatch.setattr(sem, "load_reviewed_vocab", lambda base_dir, logger: {"ok": True})
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
        return SimpleNamespace(base_dir=tmp_path), logger

    monkeypatch.setattr(sem, "_make_ctx_and_logger", _mk_ctx_and_logger)
    monkeypatch.setattr(sem, "get_paths", lambda slug: {"base": tmp_path})
    monkeypatch.setattr(sem, "load_reviewed_vocab", lambda base_dir, logger: {})

    sem._run_enrich("dummy-srl")

    assert errors and "vocabolario canonico assente" in errors[0].lower()
    assert captions and "estrazione tag" in captions[0].lower()
    assert state_calls == [("dummy-srl", "pronto")]


def test_run_summary_promotes_state_to_finito(monkeypatch, tmp_path):
    """
    Dopo 'Genera SUMMARY/README' lo stato cliente passa a 'finito'.
    """
    import ui.pages.semantics as sem

    _patch_streamlit_semantics(monkeypatch, sem)

    # cattura delle promozioni di stato
    state_calls: list[tuple[str, str]] = []
    monkeypatch.setattr(sem, "set_state", lambda slug, s: state_calls.append((slug, s)))

    # ctx/logger minimi
    def _mk_ctx_and_logger(slug: str):
        return SimpleNamespace(base_dir=tmp_path), SimpleNamespace(name="test-logger")

    monkeypatch.setattr(sem, "_make_ctx_and_logger", _mk_ctx_and_logger)

    # writer simulato
    monkeypatch.setattr(sem, "write_summary_and_readme", lambda ctx, logger, slug: None)

    sem._run_summary("dummy-srl")

    assert state_calls, "set_state non è stato chiamato"
    assert state_calls[-1] == ("dummy-srl", "finito")
