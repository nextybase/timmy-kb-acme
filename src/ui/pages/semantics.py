# SPDX-License-Identifier: GPL-3.0-or-later
# src/ui/pages/semantics.py
from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import Any, Callable, Sequence, cast

from ui.types import StreamlitLike
from ui.utils.route_state import clear_tab, get_slug_from_qp, get_tab  # noqa: F401
from ui.utils.stubs import get_streamlit
from ui.utils.ui_controls import column_button as _column_button

st: StreamlitLike = get_streamlit()


from pipeline.exceptions import ConfigError, ConversionError
from pipeline.logging_utils import get_structured_logger, log_gate_event, tail_path
from pipeline.qa_evidence import QA_EVIDENCE_FILENAME as PIPELINE_QA_EVIDENCE_FILENAME
from pipeline.qa_evidence import load_qa_evidence
from pipeline.workspace_layout import WorkspaceLayout
from semantic.api import get_paths  # noqa: F401 - usato dai test tramite monkeypatch
from semantic.api import require_reviewed_vocab
from semantic.book_readiness import is_book_ready
from semantic.convert_service import convert_markdown
from semantic.frontmatter_service import enrich_frontmatter, write_summary_and_readme
from ui.chrome import render_chrome_then_require
from ui.clients_store import get_state, set_state
from ui.components.semantic_wizard import render_semantic_wizard
from ui.constants import SEMANTIC_ENTRY_STATES
from ui.errors import to_user_message
from ui.gating import reset_gating_cache as _reset_gating_cache
from ui.pages.registry import PagePaths
from ui.utils.context_cache import get_client_context
from ui.utils.status import status_guard  # helper condiviso (con fallback)
from ui.utils.workspace import get_ui_workspace_layout, raw_ready, tagging_ready

LOGGER = get_structured_logger("ui.semantics")


# SSoT: stati ammessi per la pagina Semantica (entry: include 'pronto')
ALLOWED_STATES = SEMANTIC_ENTRY_STATES
QA_EVIDENCE_FILENAME = PIPELINE_QA_EVIDENCE_FILENAME  # marker minimo: output pre-commit/pytest (vedi instructions/08)


def _make_ctx_and_logger(slug: str) -> tuple[Any, logging.Logger, WorkspaceLayout]:
    run_id = uuid.uuid4().hex
    logger = get_structured_logger("ui.semantics", run_id=run_id)
    ctx = get_client_context(slug, require_env=False, run_id=run_id)
    layout = WorkspaceLayout.from_context(ctx)
    return ctx, logger, layout


def _display_user_error(exc: Exception) -> None:
    title, body, caption = to_user_message(exc)
    st.error(title)
    if caption or body:
        st.caption(caption or body)


def _update_client_state(slug: str, target_state: str, logger: logging.Logger) -> None:
    """Aggiorna lo stato cliente loggando eventuali fallimenti e resettando il gating."""
    try:
        set_state(slug, target_state)
        log_gate_event(
            logger,
            "ui.semantics.state_promoted",
            fields={"slug": slug, "state_id": target_state},
        )
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
        cached_state, raw_cached, tags_cached, cached_dir = _GATE_CACHE[cache_key]
        if cached_state in ALLOWED_STATES:
            ready_now, raw_dir_now = raw_ready(slug)
            tags_now, _ = tagging_ready(slug)
            if ready_now and tags_now:
                result = (cached_state, ready_now, raw_dir_now or cached_dir)
                _GATE_CACHE[cache_key] = (cached_state, ready_now, tags_now, raw_dir_now or cached_dir)
                return result
            _GATE_CACHE.pop(cache_key, None)
            _raise_semantic_unavailable(slug, state, ready_now, raw_dir_now)
            return
        _GATE_CACHE.pop(cache_key, None)
    ready, raw_dir = raw_ready(slug)
    tags_ok, _ = tagging_ready(slug)
    if state not in ALLOWED_STATES or not ready or not tags_ok:
        _raise_semantic_unavailable(slug, state, ready, raw_dir)
    result = (state, ready, raw_dir)
    _GATE_CACHE[cache_key] = (state, ready, tags_ok, raw_dir)
    try:
        _GATING_LOG.info(
            "ui.semantics.gating_allowed",
            extra={
                "slug": slug or "",
                "state": state or "n/d",
                "raw_ready": bool(ready),
                "raw_path": tail_path(raw_dir) if raw_dir else "",
                "tagging_ready": bool(tags_ok),
            },
        )
    except Exception:
        pass
    return result


def _run_convert(slug: str, *, layout: WorkspaceLayout | None = None) -> None:
    _require_semantic_gating(slug, reuse_last=True)
    ctx, logger, _ = _make_ctx_and_logger(slug)
    is_retry = _mark_retry(slug, "convert")
    try:
        ctx.set_step_status("convert", "retry" if is_retry else "start")
        if is_retry:
            log_gate_event(
                _GATING_LOG,
                "qa_gate_retry",
                fields={"slug": slug, "state_id": get_state(slug) or "", "action_id": "convert"},
            )
    except Exception:
        pass
    with status_guard(
        "Converto PDF in Markdown...",
        expanded=True,
        error_label="Errore durante la conversione",
    ) as status:
        files = convert_markdown(ctx, logger, slug=slug)
        if status is not None and hasattr(status, "update"):
            status.update(label=f"Conversione completata ({len(files)} file di contenuto).", state="complete")
    try:
        ctx.set_step_status("convert", "done")
    except Exception:
        pass
    _update_client_state(slug, "pronto", logger)


def _get_canonical_vocab(
    base_dir: Path,
    logger: logging.Logger,
    slug: str,
) -> dict[str, dict[str, Sequence[str]]]:
    """Restituisce il vocabolario canonico o solleva ConfigError."""
    return cast(dict[str, dict[str, Sequence[str]]], require_reviewed_vocab(base_dir, logger, slug=slug))


def _qa_evidence_path(layout: WorkspaceLayout) -> Path:
    """Percorso marker QA (contratto: log pre-commit/pytest salvati sotto logs/)."""
    logs_dir = getattr(layout, "logs_dir", None) or getattr(layout, "log_dir", None)
    if logs_dir is None:
        raise ConfigError("Directory log mancante per QA evidence.")
    return logs_dir / QA_EVIDENCE_FILENAME


def _run_enrich(slug: str, *, layout: WorkspaceLayout | None = None) -> None:
    try:
        _require_semantic_gating(slug, reuse_last=True)
    except ConfigError:
        tags_ok, sem_dir = tagging_ready(slug)
        if not tags_ok:
            _log_gating_block(slug, get_state(slug) or "", False, sem_dir)
            log_gate_event(
                _GATING_LOG,
                "evidence_gate_blocked",
                fields={"slug": slug or "", "state_id": get_state(slug) or "", "reason": "tagging_not_ready"},
            )
            st.error("Arricchimento bloccato: genera prima semantic/tags.db e tags_reviewed.yaml.")
            st.caption("Esegui Estrai tag (tag_onboarding) per popolari i prerequisiti e riprova.")
            return
        raise
    ctx, logger, layout = _make_ctx_and_logger(slug)
    base_dir = layout.base_dir
    is_retry = _mark_retry(slug, "enrich")
    try:
        ctx.set_step_status("enrich", "retry" if is_retry else "start")
        if is_retry:
            log_gate_event(
                _GATING_LOG,
                "qa_gate_retry",
                fields={"slug": slug, "state_id": get_state(slug) or "", "action_id": "enrich"},
            )
    except Exception:
        pass
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
        st.page_link(PagePaths.MANAGE, label="Vai a Gestisci cliente", icon=">")
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
        ctx.set_step_status("enrich", "done")
    except Exception:
        pass
    _update_client_state(slug, "arricchito", logger)


def _run_summary(slug: str, *, layout: WorkspaceLayout | None = None) -> None:
    try:
        _require_semantic_gating(slug, reuse_last=True)
    except ConfigError:
        tags_ok, sem_dir = tagging_ready(slug)
        if not tags_ok:
            log_gate_event(
                _GATING_LOG,
                "evidence_gate_blocked",
                fields={
                    "slug": slug or "",
                    "state_id": get_state(slug) or "",
                    "reason": "summary_prerequisites_missing",
                },
            )
            st.error("Generazione SUMMARY/README bloccata: prerequisiti RAW/TAG mancanti.")
            st.caption("Verifica presenza PDF in raw/ e semantic/tags.db + tags_reviewed.yaml.")
            return
        raise
    ctx, logger, layout = _make_ctx_and_logger(slug)
    qa_marker = _qa_evidence_path(layout)
    try:
        logs_dir = getattr(layout, "logs_dir", None) or getattr(layout, "log_dir", None)
        if logs_dir is None:
            raise ConfigError("Directory log mancante per QA evidence.")
        evidence = load_qa_evidence(logs_dir)
    except ConfigError as exc:
        reason = "qa_evidence_missing" if exc.code == "qa_evidence_missing" else "qa_evidence_invalid"
        log_gate_event(
            _GATING_LOG,
            "qa_gate_failed",
            fields={
                "slug": slug or "",
                "state_id": get_state(slug) or "",
                "reason": reason,
                "evidence_path": tail_path(qa_marker),
            },
        )
        st.error("QA Gate mancante: esegui `python -m timmy_kb.cli.qa_evidence --slug <slug>` per generare l'evidenza.")
        st.caption("Il comando produce `qa_passed.json` in logs/ e fallisce se la QA non passa.")
        return
    if evidence.get("qa_status") != "pass":
        log_gate_event(
            _GATING_LOG,
            "qa_gate_failed",
            fields={
                "slug": slug or "",
                "state_id": get_state(slug) or "",
                "reason": "qa_evidence_failed",
                "evidence_path": tail_path(qa_marker),
            },
        )
        st.error(
            "QA Gate fallito: evidenza QA non in stato 'pass'. "
            "Riesegui `python -m timmy_kb.cli.qa_evidence --slug <slug>`."
        )
        st.caption("Correggi la QA e ripeti l'azione SUMMARY.")
        return
    is_retry = _mark_retry(slug, "summary")
    try:
        ctx.set_step_status("summary", "retry" if is_retry else "start")
        if is_retry:
            log_gate_event(
                _GATING_LOG,
                "qa_gate_retry",
                fields={"slug": slug or "", "state_id": get_state(slug) or "", "action_id": "summary"},
            )
    except Exception:
        pass
    with status_guard(
        "Genero SUMMARY.md e README.md...",
        expanded=True,
        error_label="Errore durante la generazione",
    ) as status:
        write_summary_and_readme(ctx, logger, slug=slug)
        if status is not None and hasattr(status, "update"):
            status.update(label="SUMMARY.md e README.md generati.", state="complete")
    try:
        ctx.set_step_status("summary", "done")
    except Exception:
        pass
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
_tagging_ready: bool = False
_book_ready: bool = False
_book_dir: Path | None = None
_GATE_CACHE: dict[str, tuple[str, bool, bool, Path | None]] = {}
_ACTION_RUNS: dict[str, dict[str, int]] = {}
_GATING_LOG = get_structured_logger("ui.semantics.gating")
_PROGRESS = {
    "pronto": "[1/3] Conversione completata. Procedi con arricchimento e README/SUMMARY.",
    "arricchito": "[2/3] Conversione + arricchimento completati. Genera README/SUMMARY.",
    "finito": "[3/3] Tutti gli step completati: pronta per la preview locale.",
}


def _mark_retry(slug: str, action: str) -> bool:
    action_map = _ACTION_RUNS.setdefault(slug, {})
    action_map[action] = action_map.get(action, 0) + 1
    return action_map[action] > 1


def _log_gating_block(
    slug: str | None, state: str, raw_ready: bool, raw_dir: Path | None, *, reason: str | None = None
) -> None:
    try:
        _GATING_LOG.info(
            "ui.semantics.gating_blocked",
            extra={
                "slug": slug or "",
                "state": state or "n/d",
                "raw_ready": bool(raw_ready),
                "raw_path": tail_path(raw_dir) if raw_dir else "",
                "reason": reason or "",
            },
        )
        log_gate_event(
            _GATING_LOG,
            "evidence_gate_blocked",
            fields={
                "slug": slug or "",
                "state_id": state or "",
                "reason": reason or "",
            },
        )
    except Exception:
        pass


def _raise_semantic_unavailable(slug: str | None, state: str, raw_ready: bool, raw_dir: Path | None) -> None:
    reason = (
        "invalid_state" if state not in ALLOWED_STATES else ("raw_missing" if not raw_ready else "tagging_not_ready")
    )
    _log_gating_block(slug, state, raw_ready, raw_dir, reason=reason)
    raw_display = tail_path(raw_dir) if raw_dir else "n/d"
    raise ConfigError(
        f"Semantica non disponibile ({reason}; state={state or 'n/d'}, raw={raw_display})",
        slug=slug,
        file_path=raw_dir,
        code=reason,
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
    try:
        layout = get_ui_workspace_layout(slug, require_env=False)
    except (ConfigError, ConversionError) as exc:
        LOGGER.error("ui.semantics.layout_invalid", extra={"slug": slug, "error": str(exc)})
        _display_user_error(exc)
        try:
            st.stop()
        except Exception as stop_exc:  # pragma: no cover - Streamlit specific
            raise RuntimeError("Semantica non disponibile senza contesto Streamlit") from stop_exc

    try:  # pragma: no cover - dipende dall'ambiente Streamlit
        from streamlit.runtime.scriptrunner import get_script_run_ctx
    except Exception:  # pragma: no cover
        has_ctx = False
    else:  # pragma: no cover
        has_ctx = get_script_run_ctx() is not None

    global _client_state, _raw_ready, _tagging_ready, _book_ready, _book_dir

    if has_ctx:
        _client_state, _raw_ready, _ = _require_semantic_gating(slug)
        _tagging_ready, _ = tagging_ready(slug)
        _book_dir = layout.book_dir
        _book_ready = is_book_ready(_book_dir)

    if _column_button(st, "Rileva PDF in raw", key="btn_rescan_raw", width="stretch"):
        cache_key = (slug or "<none>").strip().lower()
        _GATE_CACHE.pop(cache_key, None)
        _reset_gating_cache(slug)
        raw_ready(slug)
        st.toast("Stato raw aggiornato.")

    client_state_ok = (_client_state in SEMANTIC_ENTRY_STATES) and bool(_tagging_ready)

    actions = {
        "convert": lambda: _handle_semantic_action(lambda s: _run_convert(s, layout=layout), slug),
        "enrich": lambda: _handle_semantic_action(lambda s: _run_enrich(s, layout=layout), slug),
        "summary": lambda: _handle_semantic_action(lambda s: _run_summary(s, layout=layout), slug),
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
