"""File bridge between Streamlit UI and VS Code watcher.

Functions:
- write_request(prompt) -> str
- read_response() -> Optional[str]

Writes last request to `.timmykb/last_request.prompt` and also copies to
`.timmykb/history/<timestamp>.prompt`. Reads `.timmykb/last_response.md` if
present.
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

LOGGER = logging.getLogger("timmy_kb.vscode_bridge")


BASE = Path(".timmykb")
HISTORY = BASE / "history"


def _ensure_dirs() -> None:
    BASE.mkdir(parents=True, exist_ok=True)
    HISTORY.mkdir(parents=True, exist_ok=True)


def write_request(prompt: str) -> str:
    """Write the prompt to last_request and history. Returns path to last file."""
    _ensure_dirs()
    last_path = BASE / "last_request.prompt"
    last_path.write_text(prompt, encoding="utf-8")
    ts = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    hist_path = HISTORY / f"{ts}.prompt"
    hist_path.write_text(prompt, encoding="utf-8")
    LOGGER.info("Prompt written: %s and %s", last_path, hist_path)
    return str(last_path)


def read_response() -> Optional[str]:
    """Read last response markdown if present, else None."""
    p = BASE / "last_response.md"
    if p.exists():
        try:
            content = p.read_text(encoding="utf-8")
            LOGGER.info("Response read from %s", p)
            return content
        except Exception as e:
            LOGGER.exception("Error reading response %s: %s", p, e)
            return None
    return None
