# tests/test_onboarding_full_paths.py
from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

import pytest


@pytest.mark.parametrize("slug", ["acme"])
def test_onboarding_full_respects_repo_root_dir(
    tmp_path: Path, monkeypatch: Any, slug: str
) -> None:
    """
    L'orchestratore deve:
    - caricare ClientContext PRIMA di determinare i path,
    - creare la cartella logs sotto REPO_ROOT_DIR (override rispettato),
    - non eseguire lavoro esterno durante il test (push / build),
      grazie ai monkeypatch su funzioni pesanti.
    """
    repo_root = tmp_path / "custom-root"
    monkeypatch.setenv("REPO_ROOT_DIR", str(repo_root))
    monkeypatch.setenv("GITHUB_TOKEN", "dummy-token")

    # Import lazy per evitare side-effects di import precedenti
    mod = importlib.import_module("src.onboarding_full")

    # Evita lavoro pesante: niente I/O esterno o push reali
    # write_summary_and_readme(context, logger, slug=...)
    if hasattr(mod, "_write_summary_and_readme"):
        monkeypatch.setattr(mod, "_write_summary_and_readme", lambda *a, **k: None)
    # ensure_book_purity(context, logger)
    if hasattr(mod, "_ensure_book_purity"):
        monkeypatch.setattr(mod, "_ensure_book_purity", lambda *a, **k: None)
    # push_output_to_github(...)
    if hasattr(mod, "push_output_to_github"):
        monkeypatch.setattr(mod, "push_output_to_github", lambda *a, **k: None)

    # Esegue l'orchestratore in modalità non-interattiva
    mod.onboarding_full_main(slug=slug, non_interactive=True, run_id="test-run")

    # Assert: la directory logs deve essere stata creata sotto REPO_ROOT_DIR
    log_dir = repo_root / "logs"
    assert log_dir.exists() and log_dir.is_dir(), (
        "log_dir non creato sotto REPO_ROOT_DIR; "
        "verifica che onboarding_full_main usi context.base_dir"
    )
