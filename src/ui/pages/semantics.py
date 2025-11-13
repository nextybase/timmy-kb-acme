# SPDX-License-Identifier: GPL-3.0-or-later
# src/ui/pages/semantics.py
from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import Any, Optional, Tuple, cast

from ui.utils.route_state import clear_tab, get_slug_from_qp, get_tab, set_tab  # noqa: F401
from ui.utils.stubs import get_streamlit
from ui.utils.ui_controls import column_button as _column_button

st = get_streamlit()


from pipeline.exceptions import ConfigError, ConversionError
from pipeline.logging_utils import get_structured_logger
from semantic.api import convert_markdown, enrich_frontmatter, get_paths, load_reviewed_vocab, write_summary_and_readme
from ui.chrome import render_chrome_then_require
from ui.clients_store import get_state, set_state
from ui.constants import SEMANTIC_ENTRY_STATES, SEMANTIC_GATING_MESSAGE, SEMANTIC_READY_STATES
from ui.errors import to_user_message
from ui.utils.context_cache import get_client_context
from ui.utils.status import status_guard  # helper condiviso (con fallback)

try:
    from ui.utils.workspace import has_raw_pdfs
except Exception:  # pragma: no cover

    def has_raw_pdfs(slug: Optional[str]) -> Tuple[bool, Optional[Path]]:
        return False, None


try:
    from ui.gating import reset_gating_cache as _reset_gating_cache
except Exception:  # pragma: no cover

    def _reset_gating_cache(_slug: str | None = None) -> None:
        return


# SSoT: stati ammessi per la pagina Semantica (entry: include 'pronto')
ALLOWED_STATES = SEMANTIC_ENTRY_STATES


def _make_ctx_and_logger(slug: str) -> tuple[Any, logging.Logger]:
    run_id = uuid.uuid4().hex
    logger = get_structured_logger("ui.semantics", run_id=run_id)
    ctx = get_client_context(slug, interactive=False, require_env=False, run_id=run_id)
    return ctx, logger


def _display_user_error(exc: Exception) -> None:
    title, body, caption = to_user_message(exc)
    st.error(title)
    if caption or body:
        st.caption(caption or body)


def _update_client_state(slug: str, target_state: str, logger: logging.Logger) -> None:
    """Aggiorna lo stato cliente loggando eventuali fallimenti e resettando il gating."""
    try:
        set_state(slug, target_state)
    except Exception as exc:
        try:
            logger.warning(
                "ui.semantics.state_update_failed",
                extra={"slug": slug, "target_state": target_state, "error": str(exc)},
            )
        except Exception:
            pass
    finally:
        cache_key = (slug or "<none>").strip()
        _GATE_CACHE.pop(cache_key, None)
        _reset_gating_cache(slug)


def _require_semantic_gating(slug: str, *, reuse_last: bool = False) -> tuple[str, bool, Path | None]:
    """Verifica gating indipendente dal contesto Streamlit."""
    cache_key = (slug or "<none>").strip()
    if reuse_last and cache_key in _GATE_CACHE:
        cached = _GATE_CACHE[cache_key]
        if cached[0] in ALLOWED_STATES and cached[1]:
            return cached
    state = (get_state(slug) or "").strip().lower()
    ready, raw_dir = has_raw_pdfs(slug)
    if state not in ALLOWED_STATES or not ready:
        raw_display = raw_dir or "n/d"
        raise RuntimeError(f"Semantica non disponibile (state={state or 'n/d'}, raw={raw_display})")
    result = (state, ready, raw_dir)
    _GATE_CACHE[cache_key] = result
    return result


def _run_convert(slug: str) -> None:
    _require_semantic_gating(slug, reuse_last=True)
    ctx, logger = _make_ctx_and_logger(slug)
    with status_guard(
        "Converto PDF in Markdown...",
        expanded=True,
        error_label="Errore durante la conversione",
    ) as status:
        files = convert_markdown(ctx, logger, slug=slug)
        if status is not None and hasattr(status, "update"):
            status.update(label=f"Conversione completata ({len(files)} file di contenuto).", state="complete")
    _update_client_state(slug, "pronto", logger)


def _run_enrich(slug: str) -> None:
    _require_semantic_gating(slug, reuse_last=True)
    ctx, logger = _make_ctx_and_logger(slug)
    base_dir = getattr(ctx, "base_dir", None) or get_paths(slug)["base"]
    vocab = load_reviewed_vocab(base_dir, logger)
    if not vocab:
        try:
            logger.warning("ui.semantics.vocab_missing", extra={"slug": slug})
        except Exception:
            pass
        _update_client_state(slug, "pronto", logger)
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
    _update_client_state(slug, "arricchito", logger)


def _run_summary(slug: str) -> None:
    _require_semantic_gating(slug, reuse_last=True)
    ctx, logger = _make_ctx_and_logger(slug)
    with status_guard(
        "Genero SUMMARY.md e README.md...",
        expanded=True,
        error_label="Errore durante la generazione",
    ) as status:
        write_summary_and_readme(ctx, logger, slug=slug)
        if status is not None and hasattr(status, "update"):
            status.update(label="SUMMARY.md e README.md generati.", state="complete")
    _update_client_state(slug, "finito", logger)


def _go_preview() -> None:
    try:
        set_tab("preview")
    except Exception:
        pass
    rerun_fn = getattr(st, "rerun", None)
    if callable(rerun_fn):
        try:
            rerun_fn()
        except Exception:
            pass


# ---------------- UI ----------------

slug = cast(str, render_chrome_then_require())

try:
    from streamlit.runtime.scriptrunner import get_script_run_ctx
except Exception:
    _HAS_STREAMLIT_CONTEXT = False
else:
    _HAS_STREAMLIT_CONTEXT = get_script_run_ctx() is not None

_client_state: str | None = None
_raw_ready: bool = False
_GATE_CACHE: dict[str, tuple[str, bool, Path | None]] = {}

if _HAS_STREAMLIT_CONTEXT:
    try:
        _client_state, _raw_ready, _ = _require_semantic_gating(slug)
    except RuntimeError as exc:
        st.info(SEMANTIC_GATING_MESSAGE)
        st.caption(str(exc))
        try:
            st.stop()
        except Exception as stop_exc:
            raise RuntimeError("Semantica non disponibile senza contesto Streamlit") from stop_exc

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
        _display_user_error(e)
    except Exception as e:  # pragma: no cover
        _display_user_error(e)

if _column_button(col_a, "Arricchisci frontmatter", key="btn_enrich", width="stretch"):
    try:
        _run_enrich(slug)
    except (ConfigError, ConversionError) as e:
        _display_user_error(e)
    except Exception as e:  # pragma: no cover
        _display_user_error(e)

# Colonna B
if _column_button(col_b, "Genera README/SUMMARY", key="btn_generate", width="stretch"):
    try:
        _run_summary(slug)
    except (ConfigError, ConversionError) as e:
        _display_user_error(e)
    except Exception as e:  # pragma: no cover
        _display_user_error(e)

preview_enabled = _client_state in SEMANTIC_READY_STATES and _raw_ready
if preview_enabled and _column_button(col_b, "Anteprima Docker (HonKit)", key="btn_preview", width="stretch"):
    _go_preview()
elif not preview_enabled:
    _col_caption = getattr(col_b, "caption", None)
    caption_fn = _col_caption if callable(_col_caption) else getattr(st, "caption", None)
    if callable(caption_fn):
        caption_fn("Anteprima disponibile dopo l'arricchimento ('arricchito' o 'finito').")
