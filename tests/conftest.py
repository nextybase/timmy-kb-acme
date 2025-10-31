# tests/conftest.py
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
for candidate in (REPO_ROOT, SRC_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

# Reindirizza di default il registry clienti verso una copia interna usata solo dai test
_DEFAULT_TEST_CLIENTS_DB_DIR = Path(".pytest_clients_db")
_DEFAULT_TEST_CLIENTS_DB_FILE = _DEFAULT_TEST_CLIENTS_DB_DIR / "clients.yaml"
(REPO_ROOT / _DEFAULT_TEST_CLIENTS_DB_DIR).mkdir(parents=True, exist_ok=True)
if "CLIENTS_DB_DIR" not in os.environ:
    os.environ["CLIENTS_DB_DIR"] = str(_DEFAULT_TEST_CLIENTS_DB_DIR)
if "CLIENTS_DB_FILE" not in os.environ:
    os.environ["CLIENTS_DB_FILE"] = _DEFAULT_TEST_CLIENTS_DB_FILE.name

# Import diretto dello script: repo root deve essere nel PYTHONPATH quando lanci pytest
try:
    from timmykb.tools.gen_dummy_kb import main as _gen_dummy_main  # type: ignore
except ModuleNotFoundError as exc:
    if exc.name in {"yaml", "pyyaml"}:
        _gen_dummy_main = None
    else:
        raise

DUMMY_SLUG = "dummy"


def _ensure_gen_dummy_available():
    if _gen_dummy_main is None:
        pytest.skip(
            "pyyaml richiesto per generare il workspace dummy (timmykb.tools.gen_dummy_kb)",
            allow_module_level=True,
        )
    return _gen_dummy_main


def _bool_env(name: str, default: bool) -> bool:
    v = os.getenv(name)
    if v is None:
        return default
    return v not in {"0", "false", "False", ""}


@pytest.fixture(scope="session")
def dummy_workspace(tmp_path_factory):
    """
    Crea un workspace dummy in una dir temporanea di sessione con:
      - config/config.yaml (+ VisionStatement.pdf)
      - raw/ (sempre)
      - book/ (con README.md e SUMMARY.md di default)
      - semantic/* (SOLO se DUMMY_WS_WITH_SEMANTIC=1; default: ON per retro-compatibilità test)

    Ritorna un dict con percorsi utili (anche le chiavi 'semantic_mapping' e 'cartelle_raw'
    sono sempre presenti nel dict; i file possono non esistere se DUMMY_WS_WITH_SEMANTIC=0).
    """
    base_parent = tmp_path_factory.mktemp("kbws")
    clients_db_relative = Path("clients_db/clients.yaml")
    gen_dummy_main = _ensure_gen_dummy_available()
    rc = gen_dummy_main(
        [
            "--base-dir",
            str(base_parent),
            "--slug",
            DUMMY_SLUG,
            "--records",
            "0",  # niente finanza per i test generici
            "--clients-db",
            clients_db_relative.as_posix(),
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

    raw_dir = base / "raw"
    book = base / "book"

    sem_dir = base / "semantic"
    sem_map = sem_dir / "semantic_mapping.yaml"
    sem_cart = sem_dir / "cartelle_raw.yaml"

    # --- Locale minimo sempre presente ---
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

    raw_dir.mkdir(parents=True, exist_ok=True)

    # Book con file minimi (molti test li usano)
    book.mkdir(parents=True, exist_ok=True)
    defaults = {
        "SUMMARY.md": "* [Alpha](alpha.md)\n* [Beta](beta.md)\n",
        "README.md": "# Dummy KB\n",
    }
    for name, content in defaults.items():
        target = book / name
        if not target.exists():
            target.write_text(content, encoding="utf-8")

    # --- Stub semantic opzionali (ON di default per retro-compat test) ---
    with_semantic = _bool_env("DUMMY_WS_WITH_SEMANTIC", True)
    if with_semantic:
        sem_dir.mkdir(parents=True, exist_ok=True)
        if not sem_map.exists():
            sem_map.write_text(
                "context:\n" f"  slug: {DUMMY_SLUG}\n" f"  client_name: Dummy {DUMMY_SLUG}\n",
                encoding="utf-8",
            )
        if not sem_cart.exists():
            sem_cart.write_text(
                "version: 1\n" "folders: []\n" "context:\n" f"  slug: {DUMMY_SLUG}\n",
                encoding="utf-8",
            )

    # Assert minimi sempre veri nel modello pre-Vision
    assert cfg.exists(), "config/config.yaml mancante"
    assert pdf.exists(), "config/VisionStatement.pdf mancante"
    assert raw_dir.exists(), "raw/ mancante"
    assert (book / "SUMMARY.md").exists()
    assert (book / "README.md").exists()
    # Gli assert sui semantic restano condizionati dal flag
    if with_semantic:
        assert sem_map.exists(), "semantic/semantic_mapping.yaml mancante"
        assert sem_cart.exists(), "semantic/cartelle_raw.yaml mancante"

    clients_db_dir = base / "clients_db"
    clients_db_dir.mkdir(parents=True, exist_ok=True)
    clients_db_file = clients_db_dir / "clients.yaml"

    return {
        "base": base,
        "config": cfg,
        "vision_pdf": pdf,
        "semantic_mapping": sem_map,
        "cartelle_raw": sem_cart,
        "book_dir": book,
        "raw_dir": raw_dir,
        "slug": DUMMY_SLUG,
        "client_name": f"Dummy {DUMMY_SLUG}",
        "with_semantic": with_semantic,
        "clients_db_file": clients_db_file,
        "clients_db_dir": clients_db_dir,
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
    - evita che i test tocchino output/ reale del repo
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
    # Reindirizza il registry clienti verso la copia temporanea
    repo_root_override = Path(dummy_workspace["base"])
    clients_db_dir = Path("clients_db")
    clients_db_file = Path("clients.yaml")
    try:
        import ui.clients_store as _clients_store

        monkeypatch.setattr(_clients_store, "REPO_ROOT", repo_root_override)
        monkeypatch.setattr(_clients_store, "DB_DIR", clients_db_dir)
        monkeypatch.setattr(_clients_store, "DB_FILE", clients_db_file)
        monkeypatch.setenv("CLIENTS_DB_DIR", clients_db_dir.as_posix())
        monkeypatch.setenv("CLIENTS_DB_FILE", clients_db_file.as_posix())
    except Exception:
        pass
    try:
        from ui.utils.stubs import reset_streamlit_stub

        reset_streamlit_stub()
    except Exception:
        pass
    yield
