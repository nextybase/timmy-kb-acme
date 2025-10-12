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
    monkeypatch.setattr(sem, "enrich_frontmatter", lambda ctx, logger, vocab, slug: ["file1.md", "file2.md"])

    sem._run_enrich("acme-srl")

    assert state_calls, "set_state non è stato chiamato"
    assert state_calls[-1] == ("acme-srl", "arricchito")


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

    sem._run_summary("acme-srl")

    assert state_calls, "set_state non è stato chiamato"
    assert state_calls[-1] == ("acme-srl", "finito")
