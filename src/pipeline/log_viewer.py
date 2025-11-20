#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
# src/pipeline/log_viewer.py
"""
Utility di lettura e parsing per la dashboard dei log UI.

Obiettivi:
- Esporre una API minimale e testabile per la pagina `logs_panel`.
- Restare allineati al modello di logging strutturato definito in `logging_utils`.
- Rispettare il modello di path-safety (ensure_within_and_resolve).

Scope (step 1):
- Gestione dei log GLOBALI della UI salvati in `.timmykb/logs/`.
- Nessuna dipendenza da Streamlit o dalla UI.

Formato atteso delle righe di log (semplificato):

    2025-02-01 10:15:32,123 INFO ui.semantics: ui.semantics.load.ok |
        slug=acme-srl run_id=123 file_path=... event=ui.semantics.load.ok

Ragioniamo con:
- prefisso standard logging (timestamp, livello, logger)
- messaggio (che spesso coincide con l'`event`)
- metadati `key=value` separati da spazio (`slug`, `run_id`, `event`, `phase`, ...).
"""

from __future__ import annotations

import dataclasses
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, cast

from pipeline.constants import LOGS_DIR_NAME
from pipeline.path_utils import ensure_within_and_resolve

__all__ = [
    "LogFileInfo",
    "get_global_logs_dir",
    "list_global_log_files",
    "parse_log_line",
    "load_log_sample",
]

# Root del repository (es. .../timmy-kb-acme)
REPO_ROOT = Path(__file__).resolve().parents[2]

# Cartella globale dei log UI, relativa alla root del repository.
_DOT_TIMMY_DIRNAME = ".timmykb"


@dataclasses.dataclass(frozen=True)
class LogFileInfo:
    """Metadati sintetici su un file di log."""

    path: Path
    size_bytes: int
    mtime: float

    @property
    def name(self) -> str:  # pragma: no cover - one-liner
        return self.path.name

    @property
    def human_size(self) -> str:  # pragma: no cover - cosmetica
        b = self.size_bytes
        if b < 1024:
            return f"{b} B"
        kb = b / 1024
        if kb < 1024:
            return f"{kb:.1f} KiB"
        mb = kb / 1024
        return f"{mb:.1f} MiB"

    @property
    def human_mtime(self) -> str:  # pragma: no cover - cosmetica
        try:
            from datetime import datetime

            return datetime.fromtimestamp(self.mtime).strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            return f"{self.mtime:.0f}"


def get_global_logs_dir() -> Path:
    """Restituisce la cartella dei log globali della UI.

    Convenzione attuale:
    - locale: `<repo_root>/.timmykb/logs/`

    Non crea la cartella se mancante.
    """
    candidate = REPO_ROOT / _DOT_TIMMY_DIRNAME / LOGS_DIR_NAME
    # Path-safety: i log globali devono sempre stare sotto il repo.
    return cast(Path, ensure_within_and_resolve(REPO_ROOT, candidate))


def _iter_log_files_from_dir(log_dir: Path) -> Iterable[LogFileInfo]:
    if not log_dir.exists():
        return []

    infos: List[LogFileInfo] = []
    for p in log_dir.iterdir():
        if not p.is_file():
            continue
        if not p.name.lower().endswith(".log"):
            # In futuro potremmo voler includere .jsonl o simili; per ora solo .log
            continue
        try:
            stat = p.stat()
        except OSError:
            continue
        infos.append(LogFileInfo(path=p, size_bytes=stat.st_size, mtime=stat.st_mtime))

    # più recenti per primi
    infos.sort(key=lambda i: i.mtime, reverse=True)
    return infos


def list_global_log_files(max_files: int = 20) -> List[LogFileInfo]:
    """Elenca i file di log globali della UI, ordinati per mtime decrescente."""
    log_dir = get_global_logs_dir()
    files = list(_iter_log_files_from_dir(log_dir))
    if max_files and max_files > 0:
        return files[:max_files]
    return files


# --------------------------------------------------------------------------- #
# Parsing righe di log
# --------------------------------------------------------------------------- #

_LOG_LINE_RE = re.compile(
    r"""
    ^
    (?P<timestamp>\d{4}-\d{2}-\d{2}\ \d{2}:\d{2}:\d{2},\d{3})  # 2025-02-01 10:15:32,123
    \s+
    (?P<level>[A-Z]+)                                         # INFO / WARNING / ERROR ...
    \s+
    (?P<logger>[^:]+)                                         # ui.onboarding, pre_onboarding, ...
    :
    \s+
    (?P<message>.*?)                                          # corpo messaggio (spesso = event)
    (?:\s+\|\s+(?P<meta>.*))?                                 # extras key=value opzionali
    $
    """,
    re.VERBOSE,
)

_KV_RE = re.compile(r"(?P<key>[a-zA-Z0-9_.]+)=(?P<value>[^ ]+)")


def parse_log_line(line: str) -> Optional[Dict[str, Any]]:
    """Parsa una singola riga di log strutturato.

    Restituisce un dict con le chiavi principali:

        {
          "timestamp": "...",
          "level": "INFO",
          "logger": "ui.onboarding",
          "message": "ui.onboarding_full.completed",
          "event": "ui.onboarding_full.completed",
          "slug": "acme-srl",
          "run_id": "...",
          "file_path": "...",
          ...
        }

    Se la riga non è nel formato atteso, restituisce None.
    """
    raw = line.strip()
    if not raw:
        return None

    m = _LOG_LINE_RE.match(raw)
    if not m:
        return None

    data = m.groupdict()
    meta = data.pop("meta") or ""

    # Metadati key=value
    extras: Dict[str, Any] = {}
    for match in _KV_RE.finditer(meta):
        key = match.group("key")
        value = match.group("value")
        extras[key] = value

    message = data.get("message", "")
    row: Dict[str, Any] = {
        "timestamp": data.get("timestamp"),
        "level": data.get("level"),
        "logger": data.get("logger"),
        "message": message,
    }

    # Se non c'è un campo event esplicito, usiamo il messaggio come event.
    if "event" in extras:
        row["event"] = extras["event"]
    else:
        row["event"] = message

    # Alcuni campi sono particolarmente utili per il filtering.
    for key in (
        "slug",
        "run_id",
        "stage",
        "phase",
        "customer",
        "file_path",
        "trace_id",
        "span_id",
    ):
        if key in extras:
            row[key] = extras[key]

    # Tutti gli altri metadati li teniamo in un dict extra opzionale.
    extra_keys = set(extras.keys()) - set(row.keys()) - {"event"}
    if extra_keys:
        row["extra"] = {k: extras[k] for k in sorted(extra_keys)}

    # Raw per debugging/espansioni future.
    row["_raw"] = raw
    return row


# --------------------------------------------------------------------------- #
# Lettura e campionamento dai file di log
# --------------------------------------------------------------------------- #


def _tail_lines(path: Path, max_lines: int) -> List[str]:
    """Restituisce le ultime `max_lines` righe del file.

    Implementazione semplice: legge tutto il file in memoria.
    Non è un problema perché:
    - i file sono ruotati (dimensione massima limitata)
    - `max_lines` è comunque limitato dalla UI.
    """
    try:
        with path.open("r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    except OSError:
        return []
    if max_lines <= 0:
        return lines
    return lines[-max_lines:]


def load_log_sample(log_file: Path, max_lines: int = 1000) -> List[Dict[str, Any]]:
    """Carica un campione di righe parsate da un file di log globale UI.

    Args:
        log_file: Path al file di log da leggere (relativo o assoluto).
        max_lines: Numero massimo di righe finali da considerare.

    Returns:
        Lista di dizionari (una per riga parsata con successo), in ordine cronologico.
    """
    log_dir = get_global_logs_dir()
    safe_path = ensure_within_and_resolve(log_dir, log_file)

    if not safe_path.exists():
        return []

    lines = _tail_lines(safe_path, max_lines=max_lines)
    rows: List[Dict[str, Any]] = []
    for line in lines:
        parsed = parse_log_line(line)
        if not parsed:
            continue
        rows.append(parsed)

    # ri-ordiniamo cronologicamente (le tail sono già "latest", ma preferiamo
    # timestamp crescente in tabella)
    rows.sort(key=lambda r: (r.get("timestamp") or "", r.get("level") or ""))
    return rows
