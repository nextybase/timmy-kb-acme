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


def test_semantics_gating_uses_ssot_constants():
    """
    Il gating deve usare la costante SSoT `SEMANTIC_READY_STATES`
    (non una whitelist hardcoded locale).
    """
    import ui.pages.semantics as sem
    from ui.constants import SEMANTIC_READY_STATES

    # ALLOWED_STATES è valorizzata a livello modulo == SEMANTIC_READY_STATES
    assert set(sem.ALLOWED_STATES) == set(SEMANTIC_READY_STATES)


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
