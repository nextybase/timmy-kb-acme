# tests/conftest.py
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]      # repo root
SRC  = ROOT / "src"                              # src dir

# Metti entrambi sul path:
for p in (str(SRC), str(ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)
