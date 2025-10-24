# SPDX-License-Identifier: GPL-3.0-or-later
# src/ui/pages/semantics.py
from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import Any, Optional, Tuple, cast

from ui.utils.stubs import get_streamlit

st = get_streamlit()


from pipeline.context import ClientContext
from pipeline.exceptions import ConfigError, ConversionError
from pipeline.logging_utils import get_structured_logger
from semantic.api import convert_markdown, enrich_frontmatter, get_paths, load_reviewed_vocab, write_summary_and_readme
from ui.chrome import render_chrome_then_require
from ui.clients_store import get_state, set_state
from ui.constants import SEMANTIC_READY_STATES
from ui.errors import to_user_message
from ui.utils.status import status_guard  # helper condiviso (con fallback)

try:
    from ui.utils.workspace import has_raw_pdfs
except Exception:  # pragma: no cover

    def has_raw_pdfs(slug: Optional[str]) -> Tuple[bool, Optional[Path]]:
        return False, None


# SSoT: stati ammessi per la pagina Semantica
ALLOWED_STATES = SEMANTIC_READY_STATES


def _make_ctx_and_logger(slug: str) -> tuple[ClientContext, logging.Logger]:
    run_id = uuid.uuid4().hex
    logger = get_structured_logger("ui.semantics", run_id=run_id)
    ctx = ClientContext.load(slug=slug, interactive=False, require_env=False, run_id=run_id)
    return ctx, logger


def _column_button(col: Any, label: str, **kwargs: Any) -> bool:
    btn = getattr(col, "button", None)
    if not callable(btn):
        raise AttributeError("Column object does not expose button()")
    try:
        return bool(btn(label, **kwargs))
    except TypeError as exc:
        if "width" in str(exc):
            kwargs.pop("width", None)
            return bool(btn(label, **kwargs))
        raise


def _run_convert(slug: str) -> None:
    ctx, logger = _make_ctx_and_logger(slug)
    with status_guard(
        "Converto PDF in Markdown...",
        expanded=True,
        error_label="Errore durante la conversione",
    ) as status:
        files = convert_markdown(ctx, logger, slug=slug)
        if status is not None and hasattr(status, "update"):
            status.update(label=f"Conversione completata ({len(files)} file di contenuto).", state="complete")


def _run_enrich(slug: str) -> None:
    ctx, logger = _make_ctx_and_logger(slug)
    base_dir = getattr(ctx, "base_dir", None) or get_paths(slug)["base"]
    vocab = load_reviewed_vocab(base_dir, logger)
    if not vocab:
        try:
            logger.warning("ui.semantics.vocab_missing", extra={"slug": slug})
        except Exception:
            pass
        st.error("Arricchimento non eseguito: vocabolario canonico assente (`semantic/tags.db`).")
        st.caption("Vai su **Gestisci cliente** e completa l'estrazione tag, poi riprova.")
        return
    with status_guard(
        "Arricchisco il frontmatter...",
        expanded=True,
        error_label="Errore durante l'arricchimento",
    ) as status:
        touched = enrich_frontmatter(ctx, logger, vocab, slug=slug)
        if status is not None and hasattr(status, "update"):
            status.update(label=f"Frontmatter aggiornato ({len(touched)} file).", state="complete")
    try:
        # Promozione stato: arricchito
        set_state(slug, "arricchito")
    except Exception:
        # Lo stato non blocca l'uso della pagina; eventuale errore non è fatale per l'utente
        pass


def _run_summary(slug: str) -> None:
    ctx, logger = _make_ctx_and_logger(slug)
    with status_guard(
        "Genero SUMMARY.md e README.md...",
        expanded=True,
        error_label="Errore durante la generazione",
    ) as status:
        write_summary_and_readme(ctx, logger, slug=slug)
        if status is not None and hasattr(status, "update"):
            status.update(label="SUMMARY.md e README.md generati.", state="complete")
    try:
        # Promozione stato: finito
        set_state(slug, "finito")
    except Exception:
        pass


def _go_preview() -> None:
    try:
        st.query_params["tab"] = "preview"
    except Exception:
        pass
    st.rerun()


# ---------------- UI ----------------

slug = cast(str, render_chrome_then_require())

try:
    from streamlit.runtime.scriptrunner import get_script_run_ctx
except Exception:
    _HAS_STREAMLIT_CONTEXT = False
else:
    _HAS_STREAMLIT_CONTEXT = get_script_run_ctx() is not None

if _HAS_STREAMLIT_CONTEXT:
    state = (get_state(slug) or "").strip().lower()
    ready, raw_dir = has_raw_pdfs(slug)
    if state not in ALLOWED_STATES or not ready:
        st.info("La semantica sarà disponibile quando lo stato raggiunge 'pronto' e `raw/` contiene PDF.")
        st.caption(f"Stato: {state or 'n/d'} - RAW: {raw_dir or 'n/d'}")
        try:
            st.stop()
        except Exception as exc:
            raise RuntimeError("Semantica non disponibile senza contesto Streamlit") from exc

st.subheader("Onboarding semantico")
_write = getattr(st, "write", None)
if callable(_write):
    _write("Conversione PDF → Markdown, arricchimento del frontmatter e generazione di README/SUMMARY.")
else:
    _cap = getattr(st, "caption", None)
    if callable(_cap):
        _cap("Conversione PDF → Markdown, arricchimento del frontmatter e generazione di README/SUMMARY.")

col_a, col_b = st.columns(2)

# Colonna A
if _column_button(col_a, "Converti PDF in Markdown", key="btn_convert", width="stretch"):
    try:
        _run_convert(slug)
    except (ConfigError, ConversionError) as e:
        title, body, caption = to_user_message(e)
        st.error(title)
        if caption:
            st.caption(caption)
        else:
            st.caption(body)
    except Exception as e:  # pragma: no cover
        title, body, caption = to_user_message(e)
        st.error(title)
        st.caption(caption or body)

if _column_button(col_a, "Arricchisci frontmatter", key="btn_enrich", width="stretch"):
    try:
        _run_enrich(slug)
    except (ConfigError, ConversionError) as e:
        title, body, caption = to_user_message(e)
        st.error(title)
        st.caption(caption or body)
    except Exception as e:  # pragma: no cover
        t, b, c = to_user_message(e)
        st.error(t)
        st.caption(c or b)

# Colonna B
if _column_button(col_b, "Genera README/SUMMARY", key="btn_generate", width="stretch"):
    try:
        _run_summary(slug)
    except (ConfigError, ConversionError) as e:
        t, b, c = to_user_message(e)
        st.error(t)
        st.caption(c or b)
    except Exception as e:  # pragma: no cover
        t, b, c = to_user_message(e)
        st.error(t)
        st.caption(c or b)

if _column_button(col_b, "Anteprima Docker (HonKit)", key="btn_preview", width="stretch"):
    _go_preview()
