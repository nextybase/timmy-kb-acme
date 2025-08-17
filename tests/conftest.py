# tests/conftest.py
import os
import sys
import shutil
import subprocess
from pathlib import Path
import pytest

# Assicura che il codice sotto src/ sia importabile come "pipeline.*"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

REPO_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_ROOT = REPO_ROOT / "output"
DUMMY_SLUG = "dummy"
DUMMY_BASE = OUTPUT_ROOT / f"timmy-kb-{DUMMY_SLUG}"


def _run_gen_dummy_kb() -> bool:
    """
    Prova a generare la KB dummy usando il tool ufficiale.
    Ritorna True se ha generato, False se il tool non esiste o fallisce.
    Nessun accesso a servizi esterni: solo FS locale.
    """
    tool = REPO_ROOT / "src" / "tools" / "gen_dummy_kb.py"
    if not tool.exists():
        return False

    # Garantisce che la radice output esista
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)

    try:
        # Usa l'interprete corrente; niente shell.
        subprocess.run(
            [sys.executable, str(tool), "--slug", DUMMY_SLUG, "--reset"],
            cwd=str(REPO_ROOT),
            check=True,
            capture_output=True,
            text=True,
        )
        return True
    except subprocess.CalledProcessError:
        # Non propaghiamo: i test hanno un fallback minimale
        return False


def _ensure_minimal_structure() -> None:
    """
    Fallback: crea struttura minima se il tool non è disponibile o fallisce.
    output/timmy-kb-dummy/{raw,book,config,logs} + config.yaml e README segnaposto.
    """
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    (DUMMY_BASE / "raw").mkdir(parents=True, exist_ok=True)
    (DUMMY_BASE / "book").mkdir(parents=True, exist_ok=True)
    (DUMMY_BASE / "config").mkdir(parents=True, exist_ok=True)
    (DUMMY_BASE / "logs").mkdir(parents=True, exist_ok=True)

    # config base (utile per slug/regex ecc.)
    cfg = DUMMY_BASE / "config" / "config.yaml"
    if not cfg.exists():
        cfg.write_text("slug_regex: '^[a-z0-9-]{3,}$'\n", encoding="utf-8")

    # README segnaposto in book/
    readme = DUMMY_BASE / "book" / "README.md"
    if not readme.exists():
        readme.write_text("# Documentazione Timmy-KB (dummy)\n", encoding="utf-8")


@pytest.fixture(scope="session")
def slug() -> str:
    """Slug fisso per tutti i test che toccano output/."""
    return DUMMY_SLUG


@pytest.fixture(scope="session")
def dummy_kb(slug: str):
    """
    Garantisce la presenza di output/timmy-kb-dummy/ con struttura regolare.
    Per default pulisce prima e (opzionalmente) dopo. Disattiva cleanup finale
    impostando KEEP_DUMMY_KB=1 nell'ambiente.
    """
    # Cleanup iniziale “soft” per evitare residui da run precedenti
    if DUMMY_BASE.exists():
        shutil.rmtree(DUMMY_BASE)

    generated = _run_gen_dummy_kb()
    if not generated:
        _ensure_minimal_structure()

    # Espone i path utili ai test
    yield {
        "base": DUMMY_BASE,
        "raw": DUMMY_BASE / "raw",
        "book": DUMMY_BASE / "book",
        "config": DUMMY_BASE / "config",
        "logs": DUMMY_BASE / "logs",
    }

    # Teardown: rimuovi la struttura, a meno che si voglia ispezionarla
    if os.getenv("KEEP_DUMMY_KB") not in ("1", "true", "True"):
        if DUMMY_BASE.exists():
            shutil.rmtree(DUMMY_BASE)


@pytest.fixture
def chdir_repo(monkeypatch):
    """Utility: imposta la CWD al root repo per test che assumono path relativi."""
    monkeypatch.chdir(REPO_ROOT)
    return REPO_ROOT
