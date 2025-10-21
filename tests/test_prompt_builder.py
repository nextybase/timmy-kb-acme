# tests/test_prompt_builder.py
from __future__ import annotations

import logging
import re
from typing import Any

import pytest


def _import_builder():
    # Import locale per evitare side-effects globali
    from timmykb.prompt_builder import build_prompt  # type: ignore

    return build_prompt


def test_build_prompt_without_retrieved(caplog: pytest.LogCaptureFixture) -> None:
    build_prompt = _import_builder()
    caplog.set_level(logging.INFO, logger="timmy_kb.prompt_builder")

    prompt = build_prompt(
        next_premise="Premessa NeXT: obiettivi e vincoli.",
        coding_rules="Segui WCAG 2.2.",
        task="Implementa la form di login.",
        retrieved=[],
    )

    # intestazioni principali
    assert "# Timmy KB Coder — Request" in prompt
    assert "## NeXT Premise" in prompt
    assert "## Task" in prompt
    assert "## Coding Rules (Web)" in prompt

    # nessun contesto recuperato => nessuna sezione e nessuna istruzione di micro-citazioni
    assert "## Retrieved Context" not in prompt
    assert "micro-citations" not in prompt

    # logging informativo con lunghezza
    assert any("Prompt built, length=" in rec.getMessage() for rec in caplog.records)


def test_build_prompt_with_retrieved_multiple_blocks() -> None:
    build_prompt = _import_builder()

    retrieved: list[dict[str, Any]] = [
        {"content": "Snippet A di documentazione.", "score": 0.875, "meta": {"source": "db", "id": "a1"}},
        {"content": "Snippet B con API.", "score": 0.5, "meta": {"source": "docs", "path": "docs/api.md"}},
    ]
    prompt = build_prompt(
        next_premise="Premessa NeXT sintetica.",
        coding_rules="Usa lazy loading.",
        task="Scrivi un client HTTP.",
        retrieved=retrieved,
    )

    # sezione presente
    assert "## Retrieved Context" in prompt

    # blocchi enumerati [#1], [#2] con score a 3 decimali e metadati
    assert "[#1] score=0.875" in prompt
    assert "Snippet A di documentazione." in prompt
    # meta dict: l'ordine chiavi è stabile in CPython; in caso di alterazioni, verifica la presenza delle coppie
    assert "meta={'source': 'db', 'id': 'a1'}" in prompt or ("meta={'id': 'a1', 'source': 'db'}" in prompt)

    assert "[#2] score=0.500" in prompt
    assert "Snippet B con API." in prompt
    assert "meta={'source': 'docs', 'path': 'docs/api.md'}" in prompt or (
        "meta={'path': 'docs/api.md', 'source': 'docs'}" in prompt
    )

    # istruzione sulle micro-citazioni
    assert "Use the Retrieved Context micro-citations like [#1]" in prompt


def test_build_prompt_empty_inputs_formatting() -> None:
    build_prompt = _import_builder()

    prompt = build_prompt(
        next_premise="",
        coding_rules="",
        task="",
        retrieved=[],
    )

    # NeXT Premise non appare se vuota
    assert "## NeXT Premise" not in prompt

    # Task presente con placeholder
    assert "## Task" in prompt
    assert "<no task provided>" in prompt

    # Coding Rules presente con bullet predefinite
    assert "## Coding Rules (Web)" in prompt
    # Verifica che almeno una bullet standard ci sia (accessibilità)
    assert re.search(r"Accessibility:.*ARIA", prompt)

    # Assicura newline finale come da implementazione
    assert prompt.endswith("\n")
