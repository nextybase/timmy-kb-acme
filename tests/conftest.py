# tests/conftest.py
import sys
import faulthandler
import subprocess
from pathlib import Path
from typing import Mapping, Dict
import pytest

ROOT = Path(__file__).resolve().parents[1]  # repo root
SRC = ROOT / "src"  # src dir

# Metti entrambi sul path:
for p in (str(SRC), str(ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)


def pytest_sessionstart(session):
    # Attiva faulthandler per diagnosi rapide
    faulthandler.enable(sys.stderr)


@pytest.fixture
def dummy_kb(tmp_path: Path) -> Mapping[str, Path]:
    """Crea una KB fittizia e restituisce un mapping di Path.

    Chiavi: 'base', 'raw', 'book', 'semantic'. Se esiste lo script tools/gen_dummy_kb.py
    lo usa; in fallback crea una struttura minima. Aggiunge placeholder solo se assenti.
    """
    kb = tmp_path / "kb"
    kb.mkdir(exist_ok=True)

    # Percorso script di generazione (se presente)
    script = Path(__file__).parents[1] / "src" / "tools" / "gen_dummy_kb.py"
    if script.exists():
        subprocess.run(
            [sys.executable, str(script), "--out", str(kb), "--slug", "dummy"],
            check=True,
        )
        # Se lo script ha creato una root annidata (timmy-kb-dummy), usa quella
        nested = kb / "timmy-kb-dummy"
        if nested.exists():
            kb = nested
    else:
        # Fallback minimo: crea le cartelle base
        (kb / "raw").mkdir(parents=True, exist_ok=True)
        (kb / "book").mkdir(parents=True, exist_ok=True)
        (kb / "semantic").mkdir(parents=True, exist_ok=True)

    # Cartelle attese (idempotenti)
    raw = (kb / "raw").resolve()
    raw.mkdir(parents=True, exist_ok=True)
    book = (kb / "book").resolve()
    book.mkdir(parents=True, exist_ok=True)
    semantic = (kb / "semantic").resolve()
    semantic.mkdir(parents=True, exist_ok=True)

    # Microhelper: placeholder innocui, creati solo se assenti
    def _touch(p: Path, content: str | None = None) -> None:
        if not p.exists():
            p.parent.mkdir(parents=True, exist_ok=True)
            if content is None:
                p.touch()
            else:
                p.write_text(content, encoding="utf-8")

    _touch(raw / ".gitkeep")
    _touch(book / ".gitkeep")
    _touch(semantic / ".gitkeep")
    _touch(raw / "README.md", "# RAW placeholder\n")

    out: Dict[str, Path] = {
        "base": kb.resolve(),
        "raw": raw,
        "book": book,
        "semantic": semantic,
    }
    return out
