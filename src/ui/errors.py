# SPDX-License-Identifier: GPL-3.0-or-later
# ui/errors.py
from __future__ import annotations

from typing import Optional, Tuple


def to_user_message(exc: Exception) -> Tuple[str, str, Optional[str]]:
    """
    Mappa eccezioni note in (title, body, caption) per la UI.
    """
    msg = str(exc).strip()
    lower = msg.lower()

    # Vision HALT (HaltError) – spesso contiene info sulle sezioni mancanti
    if exc.__class__.__name__.lower() == "halterror":
        caption = None
        missing = ""
        # best-effort: alcuni HaltError espongono un dict con sections mancanti
        details = getattr(exc, "missing", None)
        if isinstance(details, dict) and "sections" in details:
            try:
                missing = ", ".join(str(x) for x in (details.get("sections") or []))
            except Exception:
                pass
        if "vision" in lower or "halt" in lower:
            caption = f"Sezioni mancanti: {missing}" if missing else "Completa il Vision Statement e riprova."
        return ("Vision interrotta (HALT)", f"Vision interrotta: {msg}", caption)

    # ConfigError con pattern "sezioni mancanti" / "visionstatement incompleto"
    if "sezioni mancanti" in lower or "visionstatement incompleto" in lower:
        missing = ""
        if "-" in msg:
            try:
                missing = msg.split("-", 1)[-1].strip()
            except Exception:
                pass
        caption = f"Rivedi il PDF e assicurati che tutte le sezioni richieste siano presenti. {missing}".strip()
        return (
            "Errore durante Vision",
            f"Vision interrotta: mancano sezioni obbligatorie → {missing or 'n/d'}",
            caption,
        )

    # Fallback generico
    return ("Operazione non riuscita", msg or "Si è verificato un errore inatteso.", None)
