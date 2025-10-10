# tests/conftest.py
from __future__ import annotations

import logging
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
for candidate in (REPO_ROOT, SRC_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

# Import diretto dello script: repo root deve essere nel PYTHONPATH quando lanci pytest
from src.tools.gen_dummy_kb import main as gen_dummy_main

DUMMY_SLUG = "dummy"


@pytest.fixture(scope="session")
def dummy_workspace(tmp_path_factory):
    """
    Crea un workspace dummy COMPLETO in una dir temporanea di sessione,
    con:
      - config/config.yaml
      - config/VisionStatement.pdf
      - semantic/semantic_mapping.yaml (stub)
      - semantic/cartelle_raw.yaml (stub)
      - book/{alpha,beta,README,SUMMARY}.md
    Ritorna un dict con percorsi utili.
    """
    base_parent = tmp_path_factory.mktemp("kbws")
    clients_db_path = base_parent / "clients_db.yaml"
    rc = gen_dummy_main(
        [
            "--base-dir",
            str(base_parent),
            "--slug",
            DUMMY_SLUG,
            "--records",
            "0",  # niente finanza per i test generici
            "--clients-db",
            str(clients_db_path),
        ]
    )
    assert rc == 0, "gen_dummy_kb.py non è riuscito a creare il workspace"

    base = Path(base_parent) / f"{DUMMY_SLUG}"
    if not base.exists():  # fallback: alcuni script usano "timmy-kb-<slug>"
        base = Path(base_parent) / f"timmy-kb-{DUMMY_SLUG}"
    # normalizziamo al formato standard timmy-kb-<slug>
    if base.name != f"timmy-kb-{DUMMY_SLUG}":
        base = Path(base_parent) / f"timmy-kb-{DUMMY_SLUG}"

    cfg = base / "config" / "config.yaml"
    pdf = base / "config" / "VisionStatement.pdf"
    sem_map = base / "semantic" / "semantic_mapping.yaml"
    sem_cart = base / "semantic" / "cartelle_raw.yaml"
    book = base / "book"

    cfg.parent.mkdir(parents=True, exist_ok=True)
    if not cfg.exists():
        source_cfg = REPO_ROOT / "config" / "config.yaml"
        if source_cfg.exists():
            cfg.write_text(source_cfg.read_text(encoding="utf-8"), encoding="utf-8")
        else:
            cfg.write_text("vision_statement_pdf: config/VisionStatement.pdf\n", encoding="utf-8")

    pdf.parent.mkdir(parents=True, exist_ok=True)
    if not pdf.exists():
        source_pdf = REPO_ROOT / "config" / "VisionStatement.pdf"
        if source_pdf.exists():
            pdf.write_bytes(source_pdf.read_bytes())
        else:
            try:
                import fitz  # type: ignore

                doc = fitz.open()
                page = doc.new_page()
                page.insert_text((72, 72), "Dummy Vision")
                doc.save(str(pdf))
                doc.close()
            except Exception:
                pdf.write_bytes(b"%PDF-1.4\n%%EOF\n")

    sem_map.parent.mkdir(parents=True, exist_ok=True)
    if not sem_map.exists():
        sem_map.write_text(
            "context:\n" f"  slug: {DUMMY_SLUG}\n" f"  client_name: Dummy {DUMMY_SLUG}\n",
            encoding="utf-8",
        )

    sem_cart.parent.mkdir(parents=True, exist_ok=True)
    if not sem_cart.exists():
        sem_cart.write_text(
            "version: 1\n" "folders: []\n" "context:\n" f"  slug: {DUMMY_SLUG}\n",
            encoding="utf-8",
        )

    book.mkdir(parents=True, exist_ok=True)
    defaults = {"SUMMARY.md": "* [Alpha](alpha.md)\n* [Beta](beta.md)\n", "README.md": "# Dummy KB\n"}
    for name, content in defaults.items():
        target = book / name
        if not target.exists():
            target.write_text(content, encoding="utf-8")

    assert cfg.exists(), "config/config.yaml mancante"
    assert pdf.exists(), "config/VisionStatement.pdf mancante"
    assert sem_map.exists(), "semantic/semantic_mapping.yaml mancante"
    assert sem_cart.exists(), "semantic/cartelle_raw.yaml mancante"
    assert (book / "SUMMARY.md").exists()
    assert (book / "README.md").exists()

    return {
        "base": base,
        "config": cfg,
        "vision_pdf": pdf,
        "semantic_mapping": sem_map,
        "cartelle_raw": sem_cart,
        "book_dir": book,
        "slug": DUMMY_SLUG,
        "client_name": f"Dummy {DUMMY_SLUG}",
    }


@pytest.fixture
def dummy_ctx(dummy_workspace):
    """
    Ctx minimale compatibile con la pipeline: espone base_dir e client_name.
    Usalo per funzioni tipo provision_from_vision(..., ctx=...).
    """

    class Ctx:
        base_dir: Path = dummy_workspace["base"]
        client_name: str = dummy_workspace["client_name"]

    return Ctx()


@pytest.fixture
def dummy_logger():
    """Logger silenziato per i test: evita rumore in output."""
    log = logging.getLogger("test")
    log.setLevel(logging.INFO)
    while log.handlers:
        log.handlers.pop()
    log.addHandler(logging.NullHandler())
    return log


@pytest.fixture(autouse=True)
def _stable_env(monkeypatch, dummy_workspace):
    """
    Ambiente coerente per tutti i test:
    - evita che test tocchino output/ reale del repo
    - lascia vuote le var assistant per forzare branch GPT quando serve
    (i test che vogliono l'assistente le settino esplicitamente)
    """
    # Harden encoding
    monkeypatch.setenv("PYTHONUTF8", "1")
    monkeypatch.setenv("PYTHONIOENCODING", "UTF-8")

    # Disabilita accidentalmente l'assistente, salvo override nel test
    monkeypatch.delenv("OBNEXT_ASSISTANT_ID", raising=False)
    monkeypatch.delenv("ASSISTANT_ID", raising=False)

    # Evita side-effect su output/ del repo: se qualche codice usa default,
    # meglio che punti alla base temporanea del dummy.
    monkeypatch.chdir(dummy_workspace["base"])
    yield
