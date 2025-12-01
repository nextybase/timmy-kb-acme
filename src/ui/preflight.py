# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

import importlib
import json
import os
import socket
from pathlib import Path
from typing import List, Tuple

try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover
    load_dotenv = None

try:
    import streamlit as st
except Exception:  # pragma: no cover
    st = None

from pipeline.docker_utils import check_docker_status
from pipeline.env_utils import ensure_dotenv_loaded, get_env_var
from pipeline.logging_utils import get_structured_logger
from pipeline.path_utils import ensure_within_and_resolve, read_text_safe

CheckItem = Tuple[str, bool, str]
LOGGER = get_structured_logger("ui.preflight")


def _maybe_load_dotenv() -> None:
    """Carica .env solo quando serve (no side-effects a import-time)."""
    if load_dotenv:
        try:
            load_dotenv(override=False)
        except Exception:
            pass
    try:
        ensure_dotenv_loaded()
    except Exception:
        pass


def _is_importable(mod: str) -> bool:
    try:
        importlib.import_module(mod)
        return True
    except Exception:
        return False


def _docker_ok() -> tuple[bool, str]:
    return check_docker_status()


def _timmykb_origin_ok() -> tuple[bool, str]:
    """
    Verifica che i moduli `timmykb` e `ui` provengano dallo stesso root.

    Serve a intercettare scenari in cui:
    - la UI viene eseguita dal repository clonato;
    - ma la pipeline viene importata da una vecchia installazione in site-packages.
    """
    try:
        import timmykb  # type: ignore[import]
    except Exception as exc:  # pragma: no cover - ambiente minimale
        # Non blocchiamo l'esecuzione: la UI può usare i fallback basati su src/*
        return (
            False,
            "Pacchetto 'timmykb' non importabile " f"({exc}). Consigliato: `pip install -e .` nella root del repo.",
        )

    try:
        pkg_file = Path(timmykb.__file__).resolve()  # type: ignore[attr-defined]
    except Exception:
        # Se __file__ non è disponibile non possiamo verificare l'origine,
        # ma non consideriamo il caso bloccante.
        return True, "Origine 'timmykb' non determinabile (__file__ mancante)."

    preflight_file = Path(__file__).resolve()
    # directory comune dei moduli di progetto (es. <repo>/src oppure site-packages)
    ui_root = preflight_file.parents[1]
    pkg_root = pkg_file.parents[1]

    if ui_root == pkg_root:
        return True, f"OK (UI e pipeline allineate in {pkg_root})"

    hint = (
        "UI e pacchetto 'timmykb' provengono da root diversi.\n"
        f" - UI: {ui_root}\n"
        f" - timmykb: {pkg_root}\n"
        "Probabile installazione vecchia nel venv. "
        "Attiva il venv corretto e riesegui `pip install -e .` nella root del repo."
    )
    try:
        LOGGER.warning(
            "ui.preflight.timmykb_mismatch",
            extra={"ui_root": str(ui_root), "pkg_root": str(pkg_root)},
        )
    except Exception:
        pass
    return False, hint


def _port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        return sock.connect_ex(("127.0.0.1", port)) == 0


def _has_openai_key() -> bool:
    if get_env_var("OPENAI_API_KEY", default=None):
        return True
    if st is not None:
        try:
            return bool(st.secrets.get("OPENAI_API_KEY", ""))
        except Exception:
            return False
    return False


def _vision_schema_ok() -> tuple[bool, str]:
    if os.getenv("TIMMY_VISION_SKIP_SCHEMA_CHECK", "0").lower() in {"1", "true", "yes", "on"}:
        return True, "Vision schema check bypassed (TIMMY_VISION_SKIP_SCHEMA_CHECK)"
    repo_root = Path(__file__).resolve().parents[2]
    schema_path = ensure_within_and_resolve(repo_root, repo_root / "schemas" / "VisionOutput.schema.json")
    if not schema_path.exists():
        return False, f"schema mancante: {schema_path}"
    try:
        schema_text = read_text_safe(repo_root, schema_path, encoding="utf-8")
        schema = json.loads(schema_text)
    except json.JSONDecodeError as exc:
        return False, f"schema JSON invalido: {exc}"
    props = set(schema.get("properties", {}).keys())
    required = set(schema.get("required", []))
    missing = props - required
    extra = required - props
    if missing or extra:
        parts = []
        if missing:
            parts.append(f"mancano in required: {', '.join(sorted(missing))}")
        if extra:
            parts.append(f"required contiene chiavi assenti: {', '.join(sorted(extra))}")
        detail = "; ".join(parts)
        return False, detail
    return True, "Vision schema allineato"


def run_preflight() -> tuple[List[CheckItem], bool]:
    _maybe_load_dotenv()
    results: List[CheckItem] = []

    schema_ok, schema_msg = _vision_schema_ok()
    results.append(("Vision schema", schema_ok, schema_msg))

    docker_ok, hint = _docker_ok()
    results.append(("Docker", docker_ok, hint or "OK"))

    # Allineamento UI/pipeline: evita mismatch tra repo clonato e installazione pip.
    timmy_ok, timmy_hint = _timmykb_origin_ok()
    results.append(("TimmyKB install", timmy_ok, timmy_hint))

    results.append(("PyMuPDF", _is_importable("fitz"), "pip install pymupdf"))
    results.append(("ReportLab", _is_importable("reportlab"), "pip install reportlab"))
    results.append(
        (
            "Google API Client",
            _is_importable("googleapiclient.discovery"),
            "pip install google-api-python-client",
        )
    )
    results.append(("OPENAI_API_KEY", _has_openai_key(), "Imposta .env o st.secrets e riavvia"))

    port_val = get_env_var("PORT", default="4000")
    try:
        port_num = int(port_val or "4000")
    except Exception:
        port_num = 4000
    port_busy = _port_in_use(port_num) if docker_ok else False
    return results, port_busy
