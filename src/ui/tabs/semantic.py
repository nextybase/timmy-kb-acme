from __future__ import annotations

from pathlib import Path
from typing import Any

import streamlit as st

from pipeline.context import ClientContext
from semantic.api import convert_markdown, enrich_frontmatter, get_paths, load_reviewed_vocab, write_summary_and_readme


def render_semantic_tab(*, log: Any, slug: str) -> None:
    st.subheader("Semantica: conversione e arricchimento")
    if st.button("1) Converti PDF in Markdown", key="btn_sem_convert", use_container_width=True):
        try:
            ctx = ClientContext.load(slug=slug, interactive=False, require_env=False, run_id=None)
            convert_markdown(ctx, log, slug=slug)
            st.success("Conversione completata.")
        except Exception as e:
            st.exception(e)

    if st.button("2) Arricchisci frontmatter", key="btn_sem_enrich", use_container_width=True):
        try:
            ctx = ClientContext.load(slug=slug, interactive=False, require_env=False, run_id=None)
            paths = get_paths(slug)
            base_dir: Path = ctx.base_dir or paths["base"]
            vocab = load_reviewed_vocab(base_dir, log)
            touched = enrich_frontmatter(ctx, log, vocab, slug=slug)
            st.success(f"Frontmatter arricchiti: {len(touched)}")
        except Exception as e:
            st.exception(e)

    if st.button("3) Genera SUMMARY e README", key="btn_sem_md", use_container_width=True):
        try:
            ctx = ClientContext.load(slug=slug, interactive=False, require_env=False, run_id=None)
            write_summary_and_readme(ctx, log, slug=slug)
            st.success("SUMMARY.md e README.md generati/validati.")
        except Exception as e:
            st.exception(e)
