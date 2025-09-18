"""Bridge tra UI Streamlit e watcher di VS Code.

Funzioni:
- write_request(prompt) -> str
- read_response() -> Optional[str]

Scrive l'ultima richiesta in `.timmykb/last_request.prompt` e ne copia una
copia in `.timmykb/history/<timestamp>.prompt`. Legge `.timmykb/last_response.md`
se presente.
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from pipeline.file_utils import safe_write_text
from pipeline.path_utils import ensure_within, read_text_safe

LOGGER = logging.getLogger("timmy_kb.vscode_bridge")


BASE = Path(".timmykb")
HISTORY = BASE / "history"


def _ensure_dirs() -> None:
    BASE.mkdir(parents=True, exist_ok=True)
    HISTORY.mkdir(parents=True, exist_ok=True)


def write_request(prompt: str) -> str:
    """Scrive il prompt nei file last_request e history. Ritorna il path del file scritto."""
    _ensure_dirs()
    last_path = BASE / "last_request.prompt"
    ensure_within(BASE, last_path)
    safe_write_text(last_path, prompt, encoding="utf-8", atomic=True)
    ts = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    hist_path = HISTORY / f"{ts}.prompt"
    ensure_within(HISTORY, hist_path)
    safe_write_text(hist_path, prompt, encoding="utf-8", atomic=True)
    LOGGER.info("Prompt written: %s and %s", last_path, hist_path)
    return str(last_path)


def read_response() -> Optional[str]:
    """Legge l'ultima risposta markdown se presente, altrimenti None."""
    p = BASE / "last_response.md"
    if p.exists():
        try:
            content = read_text_safe(BASE, p)
            LOGGER.info("Response read from %s", p)
            return str(content) if content is not None else None
        except Exception as e:
            LOGGER.exception("Error reading response %s: %s", p, e)
            return None
    return None
