"""
Timmy KB Coder (UI dedicata — distinta da onboarding_ui.py)

Quick demo script:
1) Ensure folders exist (created automatically on app start):
   - data/
   - logs/
   - .timmykb/ (with history/)
2) Run the app:
   python -m streamlit run timmy_kb_coder.py
3) Example ingest (from a Python REPL or a separate script):
   >>> from src.ingest import ingest_folder
   >>> summary = ingest_folder(
   ...     project_slug="evagrin", scope="Timmy",
   ...     folder_glob="docs/**/*.md", version="v1",
   ...     meta={"source": "docs"},
   ... )
   >>> summary
   {'files': 5, 'chunks': 42}
"""

from __future__ import annotations

import importlib.util
import logging
import os
from pathlib import Path
from typing import cast, Dict, Any

import streamlit as st

from semantic.types import EmbeddingsClient
from src.ingest import OpenAIEmbeddings
from src.kb_db import get_db_path, init_db
from src.prompt_builder import build_prompt
from src.retriever import QueryParams, search_with_config  # <-- usa la facade
from src.vscode_bridge import read_response, write_request

# Config repo (per leggere config.yaml se disponibile)
from pipeline.context import ClientContext
from pipeline.config_utils import get_client_config

# Optional: load .env senza try/except/pass (evita flake8-bandit S110)
if importlib.util.find_spec("dotenv") is not None:  # pragma: no cover - optional dependency
    from dotenv import load_dotenv  # type: ignore

    load_dotenv()

# Logging setup
LOGS_DIR = Path("logs")
LOGS_DIR.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(LOGS_DIR / "timmy_kb.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
LOGGER = logging.getLogger("timmy_kb.ui")


def _ensure_startup() -> None:
    """Ensure required folders and DB exist."""
    Path("data").mkdir(parents=True, exist_ok=True)
    Path(".timmykb").mkdir(parents=True, exist_ok=True)
    Path(".timmykb/history").mkdir(parents=True, exist_ok=True)
    init_db(get_db_path())


def _emb_client_or_none(use_rag: bool) -> EmbeddingsClient | None:
    """Return an embeddings client if RAG is enabled and credentials are present; otherwise None."""
    if not use_rag:
        return None
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        st.warning("OPENAI_API_KEY non trovato nell'ambiente (.env consigliato). RAG disattivato.")
        return None
    try:
        return OpenAIEmbeddings()
    except Exception as e:  # pragma: no cover - mostra feedback in UI
        LOGGER.exception("Errore init embeddings: %s", e)
        st.error(f"Errore init embeddings: {e}")
        return None


def _load_client_cfg(slug: str) -> Dict[str, Any]:
    """Carica il config cliente (output/timmy-kb-<slug>/config/config.yaml) se esiste, altrimenti {}."""
    try:
        ctx = ClientContext.load(slug=slug, interactive=False, require_env=False, run_id=None)
        cfg = get_client_config(ctx) or {}
        return cfg if isinstance(cfg, dict) else {}
    except Exception as e:
        LOGGER.info("Config cliente non disponibile per slug=%s: %s", slug, e)
        return {}


def main() -> None:
    _ensure_startup()
    st.set_page_config(page_title="Timmy KB Coder", layout="wide")
    st.title("Timmy KB Coder (UI dedicata — distinta da onboarding_ui.py)")

    # Controls
    col1, col2, col3 = st.columns([1, 1, 1])
    with col1:
        use_rag = st.toggle("Usa RAG", value=True)
    with col2:
        project_slug = st.text_input("Project slug", value="evagrin")
    with col3:
        scope = cast(str, st.selectbox("Scope", options=["Timmy", "ClasScrum", "Zeno"], index=0))

    next_premise = st.text_area("NeXT Premise", height=120)
    coding_rules = st.text_area("Coding Rules (web)", height=120)
    task = st.text_area("Task", height=160)

    st.markdown("### Chat (opzionale)")
    chat_context = st.text_area("Chat log (append-only)", height=120, value="")

    # Actions
    c1, c2 = st.columns([1, 1])
    if c1.button("Compila & Invia a VS Code", use_container_width=True):
        retrieved: list[dict] = []
        emb_client = _emb_client_or_none(use_rag)
        if use_rag and emb_client is not None:
            try:
                params = QueryParams(
                    db_path=get_db_path(),
                    project_slug=project_slug,
                    scope=scope,
                    query=f"{task}\n\n{chat_context}" if chat_context else task,
                    k=8,
                    candidate_limit=4000,
                )
                # carica (se c'è) il config del cliente per allineare candidate_limit/budget
                cfg = _load_client_cfg(project_slug)
                retrieved = search_with_config(params, cfg, emb_client)
            except Exception as e:  # pragma: no cover - mostra feedback in UI
                LOGGER.exception("Errore nella ricerca: %s", e)
                st.error(f"Errore nella ricerca: {e}")
                retrieved = []
        prompt = build_prompt(next_premise, coding_rules, task, retrieved)
        st.code(prompt, language="markdown")
        path = write_request(prompt)
        st.success(f"Prompt salvato in {path}")

    if c2.button("Leggi risposta da VS Code", use_container_width=True):
        resp = read_response()
        if resp:
            st.markdown(resp)
        else:
            st.info("Nessuna risposta trovata in .timmykb/last_response.md")

    # Footer
    st.divider()
    st.caption(f"DB path: {get_db_path()}")
    st.caption(f"Log: {LOGS_DIR / 'timmy_kb.log'}")


if __name__ == "__main__":
    main()
