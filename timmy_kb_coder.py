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

import logging
import os
from pathlib import Path
from typing import Any, Dict, cast

from pipeline.config_utils import get_client_config

# Config repo (per leggere config.yaml se disponibile)
from pipeline.context import ClientContext
from pipeline.env_utils import ensure_dotenv_loaded
from semantic.types import EmbeddingsClient
from src.ingest import OpenAIEmbeddings
from src.kb_db import get_db_path, init_db
from src.prompt_builder import build_prompt
from src.retriever import QueryParams, search_with_config  # <-- usa la facade
from src.vscode_bridge import read_response, write_request

st: Any | None
try:
    import streamlit as _st

    st = _st
except Exception:  # pragma: no cover
    st = None

# Logging (passive at import-time): define constants/logger only
LOGS_DIR = Path("logs")
LOGGER = logging.getLogger("timmy_kb.ui")


def _configure_logging() -> None:
    """Configure app logging in an idempotent way.

    - Create `logs/` and `timmy_kb.log` file.
    - Add handlers only if not already present for this logger.
    - Do not touch the root logger.
    """
    # Idempotency: skip if our handlers are already attached
    if any(getattr(h, "_kb_handler", False) for h in LOGGER.handlers):
        return

    LOGS_DIR.mkdir(parents=True, exist_ok=True)

    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    fh = logging.FileHandler(LOGS_DIR / "timmy_kb.log", encoding="utf-8")
    fh.setFormatter(fmt)
    fh._kb_handler = True  # type: ignore[attr-defined]

    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    sh._kb_handler = True  # type: ignore[attr-defined]

    LOGGER.setLevel(logging.INFO)
    LOGGER.propagate = False
    LOGGER.addHandler(fh)
    LOGGER.addHandler(sh)


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
    api_key_codex = os.getenv("OPENAI_API_KEY_CODEX")
    ui = st
    if not api_key and not api_key_codex:
        LOGGER.info("coder.rag.disabled", extra={"event": "coder.rag.disabled", "reason": "missing_openai_keys"})
        if ui is not None:
            ui.warning("OPENAI_API_KEY_CODEX non trovato nell'ambiente (.env consigliato). RAG disattivato.")
        return None
    try:
        if api_key:
            LOGGER.info("embeddings.api_key", extra={"event": "embeddings.api_key", "source": "env"})
            return OpenAIEmbeddings()
        LOGGER.info("embeddings.api_key", extra={"event": "embeddings.api_key", "source": "codex_fallback"})
        return OpenAIEmbeddings(api_key=api_key_codex)
    except Exception as e:  # pragma: no cover - mostra feedback in UI
        LOGGER.exception("coder.embeddings.ui_error", extra={"event": "coder.embeddings.ui_error", "error": str(e)})
        LOGGER.info(
            "coder.rag.disabled", extra={"event": "coder.rag.disabled", "reason": "init_error", "error": str(e)}
        )
        if ui is not None:
            ui.error(f"Errore init embeddings: {e}")
        return None


def _load_client_cfg(slug: str) -> Dict[str, Any]:
    """Carica il config cliente (output/timmy-kb-<slug>/config/config.yaml) se esiste, altrimenti {}."""
    try:
        ctx = ClientContext.load(slug=slug, interactive=False, require_env=False, run_id=None)
        cfg = get_client_config(ctx) or {}
        return cfg if isinstance(cfg, dict) else {}
    except Exception as e:
        LOGGER.info(
            "coder.config.unavailable",
            extra={
                "event": "coder.config.unavailable",
                "slug": slug,
                "error": str(e),
            },
        )
        return {}


def main() -> None:
    _configure_logging()
    # Carica .env su richiesta runtime (lazy, idempotente)
    try:
        ensure_dotenv_loaded()
    except Exception:
        pass
    _ensure_startup()
    if st is None:
        raise RuntimeError("Streamlit non disponibile per Timmy KB Coder UI.")
    st.set_page_config(page_title="Timmy KB Coder", layout="wide")
    st.title("Timmy KB Coder (UI dedicata — distinta da onboarding_ui.py)")

    # Controls
    col1, col2, col3 = st.columns([1, 1, 1])
    with col1:
        use_rag = st.toggle("Usa RAG", value=True, key="coder_use_rag")
    with col2:
        project_slug = st.text_input("Project slug", value="evagrin", key="coder_project_slug")
    with col3:
        scope = cast(str, st.selectbox("Scope", options=["Timmy", "ClasScrum", "Zeno"], index=0, key="coder_scope"))

    next_premise = st.text_area("NeXT Premise", height=120, key="coder_next_premise")
    coding_rules = st.text_area("Coding Rules (web)", height=120, key="coder_coding_rules")
    task = st.text_area("Task", height=160, key="coder_task")

    st.markdown("### Chat (opzionale)")
    chat_context = st.text_area("Chat log (append-only)", height=120, value="", key="coder_chat_log")

    # Actions
    c1, c2 = st.columns([1, 1])
    if c1.button("Compila & Invia a VS Code", key="coder_send_to_vscode", width="stretch"):
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
                LOGGER.exception(
                    "coder.search.error",
                    extra={
                        "event": "coder.search.error",
                        "slug": project_slug,
                        "scope": scope,
                        "error": str(e),
                    },
                )
                st.error(f"Errore nella ricerca: {e}")
                retrieved = []
        # Riepilogo risultati (anche se vuoto)
        try:
            LOGGER.info(
                "coder.search.summary",
                extra={
                    "event": "coder.search.summary",
                    "slug": project_slug,
                    "scope": scope,
                    "results": int(len(retrieved or [])),
                },
            )
        except Exception:
            pass
        prompt = build_prompt(next_premise, coding_rules, task, retrieved)
        st.code(prompt, language="markdown")
        path = write_request(prompt)
        st.success(f"Prompt salvato in {path}")

    if c2.button("Leggi risposta da VS Code", key="coder_read_from_vscode", width="stretch"):
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
