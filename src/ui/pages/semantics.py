# SPDX-License-Identifier: GPL-3.0-or-later
# src/ui/pages/semantics.py
from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import Any, Callable, Optional, Sequence, Tuple, cast

from ui.types import StreamlitLike
from ui.utils.route_state import clear_tab, get_slug_from_qp, get_tab  # noqa: F401
from ui.utils.stubs import get_streamlit
from ui.utils.ui_controls import column_button as _column_button

st: StreamlitLike = get_streamlit()


from pipeline.exceptions import ConfigError, ConversionError
from pipeline.logging_utils import get_structured_logger, tail_path
from semantic.api import load_reviewed_vocab  # noqa: F401
from semantic.api import (
    convert_markdown,
    enrich_frontmatter,
    get_paths,
    require_reviewed_vocab,
    write_summary_and_readme,
)
from semantic.book_readiness import is_book_ready
from ui.chrome import render_chrome_then_require
from ui.clients_store import get_state, set_state
from ui.components.semantic_wizard import render_semantic_wizard
from ui.constants import SEMANTIC_ENTRY_STATES, SEMANTIC_GATING_MESSAGE
from ui.errors import to_user_message
from ui.pages.registry import PagePaths
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
        cache_key = (slug or "<none>").strip().lower()
        _GATE_CACHE.pop(cache_key, None)
        _reset_gating_cache(slug)


def _require_semantic_gating(slug: str, *, reuse_last: bool = False) -> tuple[str, bool, Path | None]:
    """Verifica gating indipendente dal contesto Streamlit."""
    cache_key = (slug or "<none>").strip().lower()
    state = (get_state(slug) or "").strip().lower()
    if reuse_last and cache_key in _GATE_CACHE:
        cached_state, _, _ = _GATE_CACHE[cache_key]
        if cached_state in ALLOWED_STATES:
            ready_now, raw_dir_now = has_raw_pdfs(slug)
            if ready_now:
                result = (cached_state, ready_now, raw_dir_now)
                _GATE_CACHE[cache_key] = result
                return result
            _GATE_CACHE.pop(cache_key, None)
            _raise_semantic_unavailable(slug, state, ready_now, raw_dir_now)
    ready, raw_dir = has_raw_pdfs(slug)
    if state not in ALLOWED_STATES or not ready:
        _raise_semantic_unavailable(slug, state, ready, raw_dir)
    result = (state, ready, raw_dir)
    _GATE_CACHE[cache_key] = result
    try:
        _GATING_LOG.info(
            "ui.semantics.gating_allowed",
            extra={
                "slug": slug or "",
                "state": state or "n/d",
                "raw_ready": bool(ready),
                "raw_path": tail_path(raw_dir) if raw_dir else "",
            },
        )
    except Exception:
        pass
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


def _get_canonical_vocab(
    base_dir: Path,
    logger: logging.Logger,
    slug: str,
) -> dict[str, dict[str, Sequence[str]]]:
    """Restituisce il vocabolario canonico o solleva ConfigError."""

    vocab = cast(dict[str, dict[str, Sequence[str]]], load_reviewed_vocab(base_dir, logger))
    if vocab:
        return vocab
    required = cast(dict[str, dict[str, Sequence[str]]], require_reviewed_vocab(base_dir, logger, slug=slug))
    return required


def _run_enrich(slug: str) -> None:
    _require_semantic_gating(slug, reuse_last=True)
    ctx, logger = _make_ctx_and_logger(slug)
    base_dir = getattr(ctx, "base_dir", None) or get_paths(slug)["base"]
    try:
        vocab = _get_canonical_vocab(base_dir, logger, slug=slug)
    except ConfigError as exc:
        try:
            logger.warning("ui.semantics.vocab_missing", extra={"slug": slug, "error": str(exc)})
        except Exception:
            pass
        _update_client_state(slug, "pronto", logger)
        st.error("Arricchimento non eseguito: vocabolario canonico assente (`semantic/tags.db`).")
        st.caption("Apri **Gestisci cliente -> Estrai tag** e completa l'estrazione tag per rigenerare il DB.")
        st.page_link("manage", label="Vai a Gestisci cliente", icon=">")
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
    """
    Step 4: passa dalla pagina Semantica alla pagina Docker Preview.

    """
    try:
        st.switch_page(PagePaths.PREVIEW)
    except Exception:
        return


_client_state: str | None = None
_raw_ready: bool = False
_book_ready: bool = False
_book_dir: Path | None = None
_GATE_CACHE: dict[str, tuple[str, bool, Path | None]] = {}
_GATING_LOG = get_structured_logger("ui.semantics.gating")
_PROGRESS = {
    "pronto": "[1/3] Conversione completata. Procedi con arricchimento e README/SUMMARY.",
    "arricchito": "[2/3] Conversione + arricchimento completati. Genera README/SUMMARY.",
    "finito": "[3/3] Tutti gli step completati: pronta per preview/push.",
}


def _log_gating_block(slug: str | None, state: str, raw_ready: bool, raw_dir: Path | None) -> None:
    try:
        _GATING_LOG.info(
            "ui.semantics.gating_blocked",
            extra={
                "slug": slug or "",
                "state": state or "n/d",
                "raw_ready": bool(raw_ready),
                "raw_path": tail_path(raw_dir) if raw_dir else "",
            },
        )
    except Exception:
        pass


def _raise_semantic_unavailable(slug: str | None, state: str, raw_ready: bool, raw_dir: Path | None) -> None:
    _log_gating_block(slug, state, raw_ready, raw_dir)
    raw_display = tail_path(raw_dir) if raw_dir else "n/d"
    raise ConfigError(
        f"Semantica non disponibile (state={state or 'n/d'}, raw={raw_display})",
        slug=slug,
        file_path=raw_dir,
    )


def _handle_semantic_action(action: Callable[[str], None], slug: str) -> None:
    """Wrapper comune per gestire le eccezioni UI delle azioni semantiche."""
    try:
        action(slug)
    except (ConfigError, ConversionError) as exc:
        _display_user_error(exc)
    except Exception as exc:  # pragma: no cover
        _display_user_error(exc)


def main() -> None:
    """Entry point Streamlit per la pagina Semantica."""

    slug = cast(str, render_chrome_then_require())

    try:  # pragma: no cover - dipende dall'ambiente Streamlit
        from streamlit.runtime.scriptrunner import get_script_run_ctx
    except Exception:  # pragma: no cover
        has_ctx = False
    else:  # pragma: no cover
        has_ctx = get_script_run_ctx() is not None

    global _client_state, _raw_ready, _book_ready, _book_dir

    if has_ctx:
        try:
            _client_state, _raw_ready, _ = _require_semantic_gating(slug)
        except ConfigError as exc:
            st.info(SEMANTIC_GATING_MESSAGE)
            st.caption(str(exc))
            try:
                st.stop()
            except Exception as stop_exc:  # pragma: no cover - Streamlit specific
                raise RuntimeError("Semantica non disponibile senza contesto Streamlit") from stop_exc

        try:
            _book_dir = get_paths(slug).get("book")
            if _book_dir is not None:
                _book_ready = is_book_ready(_book_dir)
        except Exception as exc:  # pragma: no cover - best effort
            try:
                _GATING_LOG.warning(
                    "ui.semantics.book_readiness_check_failed",
                    extra={
                        "slug": slug,
                        "error": str(exc),
                    },
                )
            except Exception:
                pass

    if _column_button(st, "Rileva PDF in raw", key="btn_rescan_raw", width="stretch"):
        cache_key = (slug or "<none>").strip().lower()
        _GATE_CACHE.pop(cache_key, None)
        _reset_gating_cache(slug)
        has_raw_pdfs(slug)
        st.toast("Stato raw aggiornato.")

    client_state_ok = _client_state in SEMANTIC_ENTRY_STATES

    actions = {
        "convert": lambda: _handle_semantic_action(_run_convert, slug),
        "enrich": lambda: _handle_semantic_action(_run_enrich, slug),
        "summary": lambda: _handle_semantic_action(_run_summary, slug),
        "preview": _go_preview,
    }

    render_semantic_wizard(
        slug=slug or "",
        client_state_ok=client_state_ok,
        book_ready=_book_ready,
        actions=actions,
    )

    progress_msg = _PROGRESS.get((_client_state or "").strip().lower())
    if progress_msg:
        st.caption(progress_msg)


if __name__ == "__main__":  # pragma: no cover
    main()
