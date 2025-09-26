# src/ui/app.py
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import streamlit as st

from pipeline.context import ClientContext
from pipeline.path_utils import read_text_safe
from src.semantic.vision_ai import ConfigError
from src.semantic.vision_ai import generate as gen_vision_yaml

# ---------------------------
# Helpers (no side-effect)
# ---------------------------


def _setup_logging() -> logging.Logger:
    logger = logging.getLogger("ui.app")
    if not logger.handlers:
        h = logging.StreamHandler()
        fmt = logging.Formatter("%(asctime)s %(name)s [%(levelname)s] %(message)s")
        h.setFormatter(fmt)
        logger.addHandler(h)
    logger.setLevel(logging.INFO)
    return logger


def _load_ctx(slug: str, logger: logging.Logger) -> Optional[ClientContext]:
    try:
        return ClientContext.load(
            slug=slug,
            interactive=False,
            require_env=False,
            run_id=None,
        )
    except Exception:  # non esponiamo dettagli sensibili
        logger.exception("ContextLoadError")
        st.error(f"Errore nel caricamento del contesto per slug '{slug}'.")
        return None


def _hint_pdf_locations(base_dir: Path) -> str:
    cfg = base_dir / "config" / "VisionStatement.pdf"
    raw = base_dir / "raw" / "VisionStatement.pdf"
    return f"- {cfg}\n- {raw}"


# ---------------------------
# Main UI
# ---------------------------


def main() -> None:
    logger = _setup_logging()

    st.set_page_config(page_title="Onboarding NeXT / Timmy", layout="wide")
    st.title("Onboarding NeXT — Workspace & Semantica")

    # Sidebar: slug input
    with st.sidebar:
        st.header("Workspace")
        slug = st.text_input("Slug cliente (kebab-case)", placeholder="acme-sicilia")
        load_btn = st.button("Carica contesto", use_container_width=True)

    # Early exit: no slug, no load
    if not slug:
        st.info("Inserisci lo slug del cliente e premi 'Carica contesto'.")
        return

    ctx: Optional[ClientContext] = None
    if load_btn:
        ctx = _load_ctx(slug, logger)
        if ctx:
            st.sidebar.success(f"Contesto caricato: {slug}")

    # Manteniamo lo stato (quando Streamlit ricarica)
    if "ctx_loaded" not in st.session_state:
        st.session_state["ctx_loaded"] = False
    if load_btn and ctx:
        st.session_state["ctx_loaded"] = True
        st.session_state["slug"] = slug

    if not st.session_state["ctx_loaded"]:
        return

    # Ricarica il contesto dal nome slug in sessione per sicurezza
    slug = st.session_state["slug"]
    ctx = _load_ctx(slug, logger)
    if ctx is None:
        return

    base_dir = Path(ctx.base_dir)
    st.caption(f"Workspace base: `{base_dir}`")

    # Tabs
    t_sem, t_outputs = st.tabs(["📑 Semantica", "📁 Output"])

    with t_sem:
        st.subheader("Vision → YAML (generazione AI)")

        st.write(
            "Questo step genera `semantic/vision_statement.yaml` a partire dal `VisionStatement.pdf` "
            "del workspace corrente, usando GPT-5 (Responses API + Structured Outputs)."
        )

        st.markdown("**Assicurati di aver caricato `VisionStatement.pdf` in uno di questi percorsi:**")
        st.code(_hint_pdf_locations(base_dir), language="text")

        col1, col2 = st.columns([1, 2])
        with col1:
            run_btn = st.button("Genera vision_statement.yaml (AI)", type="primary")
        with col2:
            show_yaml = st.checkbox("Mostra contenuto YAML al termine", value=True)

        if run_btn:
            try:
                out_path = gen_vision_yaml(ctx, logger, slug=slug)
                st.success(f"Creato: {out_path}")

                if show_yaml:
                    try:
                        content = read_text_safe(base_dir, Path(out_path), encoding="utf-8")
                        st.code(content, language="yaml")
                    except Exception:
                        st.warning("File generato ma non leggibile ora; verifica i permessi o aprilo da file system.")
            except ConfigError as e:
                st.error(str(e))
            except Exception:
                logger.exception("VisionAIError")
                st.error("Errore nella generazione del YAML. Controlla i log per i dettagli.")

    with t_outputs:
        st.subheader("Esplora output del workspace")
        semantic_dir = base_dir / "semantic"
        cfg_dir = base_dir / "config"
        raw_dir = base_dir / "raw"

        st.markdown("**Cartelle principali**")
        st.write(f"- `{semantic_dir}`")
        st.write(f"- `{cfg_dir}`")
        st.write(f"- `{raw_dir}`")

        vs_yaml = semantic_dir / "vision_statement.yaml"
        if vs_yaml.exists():
            st.markdown("**Anteprima `semantic/vision_statement.yaml`**")
            try:
                preview = read_text_safe(base_dir, vs_yaml, encoding="utf-8")
                st.code(preview, language="yaml")
            except Exception:
                st.warning("Impossibile leggere l'anteprima del file YAML.")


if __name__ == "__main__":
    main()
