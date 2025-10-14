# SPDX-License-Identifier: GPL-3.0-or-later
# src/ui/pages/semantics.py
from __future__ import annotations

import logging
import uuid
from contextlib import contextmanager
from typing import Any, Iterator, Literal, cast

try:
    import streamlit as st
except Exception:  # pragma: no cover - fallback per ambienti test senza streamlit

    class _FunctionStub:
        """No-op callable/context manager usato per simulare API Streamlit."""

        def __call__(self, *args: Any, **kwargs: Any) -> "_FunctionStub":
            return self

        def __enter__(self) -> "_FunctionStub":
            return self

        def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> Literal[False]:
            return False

        def __getattr__(self, name: str) -> "_FunctionStub":
            return self

        def __bool__(self) -> bool:
            return False

    class _StreamlitStub:
        def __init__(self) -> None:
            self.session_state: dict[str, Any] = {}
            self.query_params: dict[str, str] = {}
            self.sidebar = _FunctionStub()

        def __getattr__(self, name: str) -> Any:
            if name == "stop":

                def _stop(*_args: Any, **_kwargs: Any) -> None:
                    raise RuntimeError("Streamlit stop non disponibile nel fallback")

                return _stop
            if name == "rerun":

                def _rerun(*_args: Any, **_kwargs: Any) -> None:
                    raise RuntimeError("Streamlit rerun non disponibile nel fallback")

                return _rerun
            if name == "spinner":

                @contextmanager
                def _spinner(*_args: Any, **_kwargs: Any) -> Iterator[None]:
                    yield None

                return _spinner
            if name == "columns":

                def _columns(spec: Any) -> tuple[_FunctionStub, ...]:
                    if isinstance(spec, (list, tuple)):
                        count = len(spec)
                    else:
                        try:
                            count = int(spec)
                        except Exception:
                            count = 0
                    return tuple(_FunctionStub() for _ in range(max(count, 0)))

                return _columns
            return _FunctionStub()

    st = cast(Any, _StreamlitStub())

from pipeline.context import ClientContext
from pipeline.exceptions import ConfigError, ConversionError
from pipeline.logging_utils import get_structured_logger
from semantic.api import convert_markdown, enrich_frontmatter, get_paths, load_reviewed_vocab, write_summary_and_readme
from ui.chrome import render_chrome_then_require
from ui.clients_store import get_state, set_state
from ui.constants import SEMANTIC_READY_STATES

try:
    from ui.utils.workspace import has_raw_pdfs
except Exception:  # pragma: no cover

    def has_raw_pdfs(_slug: str | None) -> tuple[bool, str | None]:
        return False, None


# SSoT: stati ammessi per la pagina Semantica
ALLOWED_STATES = SEMANTIC_READY_STATES


def _make_ctx_and_logger(slug: str) -> tuple[ClientContext, logging.Logger]:
    run_id = uuid.uuid4().hex
    logger = get_structured_logger("ui.semantics", run_id=run_id)
    ctx = ClientContext.load(slug=slug, interactive=False, require_env=False, run_id=run_id)
    return ctx, logger


def _safe_button(label: str, **kwargs: Any) -> bool:
    try:
        return bool(st.button(label, **kwargs))
    except TypeError:
        kwargs.pop("width", None)
        return bool(st.button(label, **kwargs))


def _run_convert(slug: str) -> None:
    ctx, logger = _make_ctx_and_logger(slug)
    with st.spinner("Converto PDF in Markdown..."):
        files = convert_markdown(ctx, logger, slug=slug)
    st.success(f"Conversione completata ({len(files)} file di contenuto).")


def _run_enrich(slug: str) -> None:
    ctx, logger = _make_ctx_and_logger(slug)
    base_dir = getattr(ctx, "base_dir", None) or get_paths(slug)["base"]
    vocab = load_reviewed_vocab(base_dir, logger)
    with st.spinner("Arricchisco frontmatter..."):
        touched = enrich_frontmatter(ctx, logger, vocab, slug=slug)
    st.success(f"Frontmatter aggiornato ({len(touched)} file).")
    try:
        # Promozione stato: arricchito
        set_state(slug, "arricchito")
    except Exception:
        # Lo stato non blocca l'uso della pagina; eventuale errore non è fatale per l'utente
        pass


def _run_summary(slug: str) -> None:
    ctx, logger = _make_ctx_and_logger(slug)
    with st.spinner("Genero SUMMARY.md e README.md..."):
        write_summary_and_readme(ctx, logger, slug=slug)
    st.success("SUMMARY.md e README.md generati.")
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

slug = render_chrome_then_require()

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
        st.caption(f"Stato: {state or 'n/d'} — RAW: {raw_dir or 'n/d'}")
        st.stop()

st.subheader("Onboarding semantico")
st.write("Conversione PDF → Markdown, arricchimento del frontmatter e generazione di README/SUMMARY.")

col_a, col_b = st.columns(2)
with col_a:
    if _safe_button("Converti PDF in Markdown", key="btn_convert", width="stretch"):
        try:
            _run_convert(slug)
        except (ConfigError, ConversionError) as e:
            st.error(str(e))
        except Exception as e:  # pragma: no cover
            st.error(f"Errore nella conversione: {e}")
    if _safe_button("Arricchisci frontmatter", key="btn_enrich", width="stretch"):
        try:
            _run_enrich(slug)
        except (ConfigError, ConversionError) as e:
            st.error(str(e))
        except Exception as e:  # pragma: no cover
            st.error(f"Errore nell'arricchimento: {e}")

with col_b:
    if _safe_button("Genera README/SUMMARY", key="btn_generate", width="stretch"):
        try:
            _run_summary(slug)
        except (ConfigError, ConversionError) as e:
            st.error(str(e))
        except Exception as e:  # pragma: no cover
            st.error(f"Errore nella generazione: {e}")
    if _safe_button("Anteprima Docker (HonKit)", key="btn_preview", width="stretch"):
        _go_preview()
