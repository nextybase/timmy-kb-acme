# tests/test_ui_labels.py
from __future__ import annotations

import re
from pathlib import Path


def _read(repo: Path, rel: str) -> str:
    p = repo / rel
    assert p.exists(), f"File mancante: {rel}"
    return p.read_text(encoding="utf-8", errors="ignore")


def test_landing_labels_beta0():
    """Verifica che la landing esponga i label aggiornati per la Beta 0."""
    repo = Path(__file__).resolve().parents[1]
    txt = _read(repo, "src/ui/landing_slug.py")

    # Bottoni/etichette principali del nuovo flusso
    assert "Verifica cliente" in txt
    assert "Crea workspace + carica PDF" in txt
    assert "Vai alla configurazione" in txt
    assert "Esci" in txt

    # Editor YAML: etichette dei due editor testuali
    assert "semantic/semantic_mapping.yaml" in txt
    assert "semantic/cartelle_raw.yaml" in txt


def test_no_legacy_labels_or_switchers_anymore():
    """
    Assicura che non ci siano più label/chiavi legacy nel codice dell'app.
    Escludiamo i test stessi per evitare falsi positivi (questo file contiene le stringhe vietate).
    """
    repo = Path(__file__).resolve().parents[1]
    app_files: list[Path] = []

    # Scansioniamo solo il codice applicativo (no tests)
    for root in ("onboarding_ui.py", "src", "ui"):
        p = repo / root
        if p.is_file():
            app_files.append(p)
        elif p.exists():
            app_files.extend(f for f in p.rglob("*.py"))

    hay = "\n".join(
        f.read_text(encoding="utf-8", errors="ignore")
        for f in app_files
        if "venv" not in str(f) and ".tox" not in str(f)
    )

    forbidden = [
        "Inizializza workspace",  # vecchio bottone di setup
        "Rigenera YAML",  # vecchia azione di ready
        "render_sidebar_tab_switches",  # switcher tab legacy
        "src/ui/tabs",  # percorso legacy
        "from src.ui.tabs",  # import legacy
        "import src.ui.tabs",  # import legacy
    ]
    for needle in forbidden:
        assert needle not in hay, f"Residuo legacy trovato nel codice app: {needle!r}"


def test_entrypoint_uses_native_navigation():
    """Controlla che l'entrypoint usi il router nativo e non mischi sistemi."""
    repo = Path(__file__).resolve().parents[1]
    entry = _read(repo, "onboarding_ui.py")

    assert "st.navigation(" in entry, "router nativo (st.navigation) mancante"
    assert "st.Page(" in entry, "st.Page mancante"

    # Evita mescolanze con vecchio sistema a tab
    forbidden = r"(active_tab|TAB_HOME|TAB_MANAGE|TAB_SEM|_render_tabs_router|render_sidebar_tab_switches)"
    assert not re.search(forbidden, entry), "riferimenti legacy nell'entrypoint"
