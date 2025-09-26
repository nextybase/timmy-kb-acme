from __future__ import annotations

import sys
from pathlib import Path

_src_root = Path(__file__).resolve().parent / "src"
if str(_src_root) not in sys.path:
    sys.path.insert(0, str(_src_root))

from src.ui.app import main  # noqa: E402


if __name__ == "__main__":
    main()
