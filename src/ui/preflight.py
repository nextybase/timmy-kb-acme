from __future__ import annotations

import importlib
import os
import shutil
import socket
import subprocess
from typing import List, Tuple

try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover
    load_dotenv = None

try:
    import streamlit as st
except Exception:  # pragma: no cover
    st = None

CheckItem = Tuple[str, bool, str]

if load_dotenv:
    try:
        load_dotenv(override=False)
    except Exception:
        pass


def _is_importable(mod: str) -> bool:
    try:
        importlib.import_module(mod)
        return True
    except Exception:
        return False


def _docker_ok() -> tuple[bool, str]:
    docker_exe = shutil.which("docker")
    if docker_exe is None:
        return False, "Docker CLI non trovato (installa Docker Desktop/Engine)"
    try:
        subprocess.run(  # noqa: S603 - comando statico su eseguibile verificato
            [docker_exe, "info"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True,
            shell=False,
        )
        return True, ""
    except Exception:
        return False, "Docker non in esecuzione (avvialo e riprova)"


def _port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        return sock.connect_ex(("127.0.0.1", port)) == 0


def _has_openai_key() -> bool:
    if os.getenv("OPENAI_API_KEY"):
        return True
    if st is not None:
        try:
            return bool(st.secrets.get("OPENAI_API_KEY", ""))
        except Exception:
            return False
    return False


def run_preflight() -> tuple[List[CheckItem], bool]:
    results: List[CheckItem] = []

    docker_ok, hint = _docker_ok()
    results.append(("Docker", docker_ok, hint or "OK"))

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

    port_busy = _port_in_use(int(os.getenv("PORT", "4000"))) if docker_ok else False
    return results, port_busy
