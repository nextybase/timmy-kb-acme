# src/vscode_bridge.py
"""Bridge tra UI Streamlit e watcher di VS Code.

Funzioni:
- write_request(prompt) -> str
- read_response() -> Optional[str]

Scrive l'ultima richiesta in `.timmykb/last_request.prompt` e ne copia una
copia in `.timmykb/history/<timestamp>.prompt`. Legge `.timmykb/last_response.md`
se presente.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional

from pipeline.file_utils import safe_write_text
from pipeline.logging_utils import get_structured_logger
from pipeline.path_utils import ensure_within, read_text_safe

LOGGER = get_structured_logger("timmy_kb.vscode_bridge", propagate=False)

BASE = Path(".timmykb")
HISTORY = BASE / "history"


def _ensure_dirs() -> None:
    BASE.mkdir(parents=True, exist_ok=True)
    HISTORY.mkdir(parents=True, exist_ok=True)


def write_request(prompt: str) -> str:
    """Scrive il prompt nei file last_request e history.

    Ritorna il path del file scritto.
    """
    _ensure_dirs()
    last_path = BASE / "last_request.prompt"
    ensure_within(BASE, last_path)
    safe_write_text(last_path, prompt, encoding="utf-8", atomic=True)

    ts = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    hist_path = HISTORY / f"{ts}.prompt"
    ensure_within(HISTORY, hist_path)
    safe_write_text(hist_path, prompt, encoding="utf-8", atomic=True)

    LOGGER.info(
        "vscode_bridge.prompt_written",
        extra={
            "event": "vscode_bridge.prompt_written",
            "last_path": str(last_path),
            "history_path": str(hist_path),
        },
    )
    return str(last_path)


def read_response() -> Optional[str]:
    """Legge l'ultima risposta markdown se presente, altrimenti None."""
    p = BASE / "last_response.md"
    if p.exists():
        try:
            content = read_text_safe(BASE, p)
            LOGGER.info(
                "vscode_bridge.response_read",
                extra={"event": "vscode_bridge.response_read", "response_path": str(p)},
            )
            return str(content) if content is not None else None
        except Exception as e:
            LOGGER.exception(
                "vscode_bridge.response_error",
                extra={"event": "vscode_bridge.response_error", "response_path": str(p), "error": str(e)},
            )
            return None

    LOGGER.info(
        "vscode_bridge.response_missing",
        extra={"event": "vscode_bridge.response_missing", "response_path": str(p)},
    )
    return None


__all__ = ["write_request", "read_response"]
