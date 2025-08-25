# tests/conftest.py
from __future__ import annotations

import os
import sys
import shutil
import subprocess
from pathlib import Path
import pytest

# Root repo e output
REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
OUTPUT_ROOT = REPO_ROOT / "output"
DUMMY_SLUG = "dummy"
DUMMY_BASE = OUTPUT_ROOT / f"timmy-kb-{DUMMY_SLUG}"

# Import moduli sia come "src.semantic.*" sia come "pipeline.*"
# - REPO_ROOT per permettere import "src.<...>"
# - SRC_DIR per permettere import "pipeline.<...>"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

GEN_TOOL = REPO_ROOT / "src" / "tools" / "gen_dummy_kb.py"

def _run_gen_dummy_kb() -> None:
    """Genera la KB dummy usando lo strumento ufficiale. Fallisce hard se c'è un errore."""
    assert GEN_TOOL.exists(), f"Tool mancante: {GEN_TOOL}"
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)

    cmd = [
        sys.executable,
        str(GEN_TOOL),
        "--slug", DUMMY_SLUG,
        "--name", "Cliente Dummy",
        "--overwrite",
    ]

    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"

    result = subprocess.run(
        cmd,
        cwd=str(REPO_ROOT),
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )
    if result.returncode != 0:
        print(">>> gen_dummy_kb.py FAILED")
        print("STDOUT:\n", (result.stdout or "")[-4000:])
        print("STDERR:\n", (result.stderr or "")[-4000:])
        raise AssertionError(f"gen_dummy_kb.py è fallito con exit code {result.returncode}")

@pytest.fixture(scope="session")
def repo_root() -> Path:
    return REPO_ROOT

@pytest.fixture(scope="session")
def base_dir() -> Path:
    return DUMMY_BASE

@pytest.fixture(scope="session")
def dummy_kb(repo_root: Path, base_dir: Path):
    """Genera SEMPRE una sandbox pulita per il dummy prima dei test."""
    if base_dir.exists():
        shutil.rmtree(base_dir)

    _run_gen_dummy_kb()

    assert base_dir.exists(), f"Sandbox non creata: {base_dir}"
    assert (base_dir / "raw").exists()
    assert (base_dir / "semantic").exists()

    csv_path = base_dir / "semantic" / "tags_raw.csv"
    assert csv_path.exists(), f"CSV mancante: {csv_path}"

    pdfs = list((base_dir / "raw").rglob("*.pdf"))
    assert pdfs, "Attesi PDF sotto raw/, ma non ne sono stati trovati"

    yield {
        "base": base_dir,
        "raw": base_dir / "raw",
        "semantic": base_dir / "semantic",
        "config": base_dir / "config",
        "book": base_dir / "book",
        "logs": base_dir / "logs",
        "csv": csv_path,
        "pdfs": pdfs,
    }

    if os.getenv("KEEP_DUMMY_KB") not in ("1", "true", "True"):
        if base_dir.exists():
            shutil.rmtree(base_dir)

@pytest.fixture
def chdir_repo(monkeypatch):
    """Imposta la CWD alla root del repo (alcuni moduli assumono path relativi)."""
    monkeypatch.chdir(REPO_ROOT)
    return REPO_ROOT
