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
from pipeline.qa_gate import require_qa_gate_pass
from pipeline.workspace_layout import WorkspaceLayout
from semantic.api import get_paths  # noqa: F401 - usato dai test tramite monkeypatch
from semantic.api import require_reviewed_vocab
from semantic.book_readiness import is_book_ready
from semantic.convert_service import convert_markdown
from semantic.frontmatter_service import enrich_frontmatter, write_summary_and_readme
from ui.chrome import render_chrome_then_require
from ui.clients_store import get_state
from ui.clients_store import set_state as set_client_state
from ui.components.semantic_wizard import render_semantic_wizard
from ui.constants import SEMANTIC_ENTRY_STATES
from ui.errors import to_user_message
from ui.gating import reset_gating_cache as _reset_gating_cache
from ui.pages.registry import PagePaths
from ui.utils.context_cache import get_client_context
from ui.utils.status import status_guard  # helper condiviso (con degradazione)
from ui.utils.workspace import get_ui_workspace_layout, normalized_ready, tagging_ready

LOGGER = get_structured_logger("ui.semantics")


# SSoT: stati ammessi per la pagina Semantica (entry: include 'pronto')
ALLOWED_STATES = SEMANTIC_ENTRY_STATES
QA_EVIDENCE_FILENAME = PIPELINE_QA_EVIDENCE_FILENAME  # marker minimo: output pre-commit/pytest (vedi instructions/08)


def _log_semantics_failure(
    logger: logging.Logger,
    event: str,
    exc: Exception,
    *,
    extra: dict[str, object] | None = None,
) -> None:
    payload = {"error": repr(exc)}
    if extra:
        payload.update(extra)
    try:
        logger.warning(event, extra=payload)
    except Exception:
        logging.getLogger("ui.semantics").warning("%s error=%r", event, exc)


def _make_ctx_and_logger(slug: str) -> tuple[Any, logging.Logger, WorkspaceLayout]:
    run_id = uuid.uuid4().hex
    logger = get_structured_logger("ui.semantics", run_id=run_id)
    ctx = get_client_context(slug, require_drive_env=False, run_id=run_id)
    layout = WorkspaceLayout.from_context(ctx)
    return ctx, logger, layout


def _display_user_error(exc: Exception) -> None:
    title, body, caption = to_user_message(exc)
    st.error(title)
    if caption or body:
        st.caption(caption or body)


def _require_semantic_gating(slug: str, *, reuse_last: bool = False) -> tuple[str, bool, Path | None]:
    """Verifica gating indipendente dal contesto Streamlit."""
    cache_key = (slug or "<none>").strip().lower()
    state = (get_state(slug) or "").strip().lower()
    if reuse_last and cache_key in _GATE_CACHE:
        cached_state, _normalized_cached, tags_cached, cached_dir = _GATE_CACHE[cache_key]
        if cached_state in ALLOWED_STATES:
            ready_now, normalized_dir_now = normalized_ready(slug)
            tags_now, _ = tagging_ready(slug)
            if ready_now:
                result = (cached_state, ready_now, normalized_dir_now or cached_dir)
                _GATE_CACHE[cache_key] = (cached_state, ready_now, tags_now, normalized_dir_now or cached_dir)
                return result
            _GATE_CACHE.pop(cache_key, None)
            _raise_semantic_unavailable(slug, state, ready_now, normalized_dir_now)
            return
        _GATE_CACHE.pop(cache_key, None)
    ready, normalized_dir = normalized_ready(slug)
    tags_ok, _ = tagging_ready(slug)
    if state not in ALLOWED_STATES or not ready:
        _raise_semantic_unavailable(slug, state, ready, normalized_dir)
    result = (state, ready, normalized_dir)
    _GATE_CACHE[cache_key] = (state, ready, tags_ok, normalized_dir)
    try:
        _GATING_LOG.info(
            "ui.semantics.gating_allowed",
            extra={
                "slug": slug or "",
                "state": state or "n/d",
                "normalized_ready": bool(ready),
                "normalized_path": tail_path(normalized_dir) if normalized_dir else "",
                "tagging_ready": bool(tags_ok),
            },
        )
    except Exception as exc:
        _log_semantics_failure(
            _GATING_LOG,
            "ui.semantics.gating_allowed_log_failed",
            exc,
            extra={"slug": slug or "", "state": state or "n/d"},
        )
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
                fields=_gate_fields(slug=slug, state=get_state(slug) or "", action="convert"),
            )
    except Exception as exc:
        _log_semantics_failure(
            logger,
            "ui.semantics.step_status_failed",
            exc,
            extra={"slug": slug, "action_id": "convert", "status": "start", "retry": bool(is_retry)},
        )
    with status_guard(
        "Converto Markdown normalizzati in book...",
        expanded=True,
        error_label="Errore durante la conversione",
    ) as status:
        files = convert_markdown(ctx, logger, slug=slug)
        if status is not None and hasattr(status, "update"):
            status.update(label=f"Conversione completata ({len(files)} file di contenuto).", state="complete")
    try:
        ctx.set_step_status("convert", "done")
    except Exception as exc:
        _log_semantics_failure(
            logger,
            "ui.semantics.step_status_failed",
            exc,
            extra={"slug": slug, "action_id": "convert", "status": "done"},
        )


def _get_canonical_vocab(
    repo_root_dir: Path,
    logger: logging.Logger,
    slug: str,
) -> dict[str, dict[str, Sequence[str]]]:
    """Restituisce il vocabolario canonico o solleva ConfigError."""
    return cast(dict[str, dict[str, Sequence[str]]], require_reviewed_vocab(repo_root_dir, logger, slug=slug))


def _qa_evidence_path(layout: WorkspaceLayout) -> Path:
    """Percorso marker QA (contratto: log pre-commit/pytest salvati sotto logs/)."""
    return layout.logs_dir / QA_EVIDENCE_FILENAME


def _run_enrich(slug: str, *, layout: WorkspaceLayout | None = None) -> None:
    try:
        _require_semantic_gating(slug, reuse_last=True)
    except ConfigError:
        tags_ok, sem_dir = tagging_ready(slug)
        if not tags_ok:
            _, normalized_dir = normalized_ready(slug)
            _log_gating_block(slug, get_state(slug) or "", False, normalized_dir)
            log_gate_event(
                _GATING_LOG,
                "evidence_gate_blocked",
                fields=_gate_fields(
                    slug=slug,
                    state=get_state(slug) or "",
                    action="enrich",
                    reason="tagging_not_ready",
                ),
            )
            st.error("Arricchimento bloccato: genera prima semantic/tags.db.")
            st.caption("Esegui Estrai tag (tag_onboarding) per popolari i prerequisiti e riprova.")
            return
        raise
    ctx, logger, layout = _make_ctx_and_logger(slug)
    repo_root_dir = layout.repo_root_dir
    is_retry = _mark_retry(slug, "enrich")
    try:
        ctx.set_step_status("enrich", "retry" if is_retry else "start")
        if is_retry:
            log_gate_event(
                _GATING_LOG,
                "qa_gate_retry",
                fields=_gate_fields(slug=slug, state=get_state(slug) or "", action="enrich"),
            )
    except Exception as exc:
        _log_semantics_failure(
            logger,
            "ui.semantics.step_status_failed",
            exc,
            extra={"slug": slug, "action_id": "enrich", "status": "start", "retry": bool(is_retry)},
        )
    try:
        vocab = _get_canonical_vocab(repo_root_dir, logger, slug=slug)
    except ConfigError as exc:
        _log_semantics_failure(
            logger,
            "ui.semantics.vocab_missing",
            exc,
            extra={"slug": slug},
        )
        st.error("Arricchimento non eseguito: vocabolario canonico assente (`semantic/tags.db`).")
        st.caption("Apri **Gestisci cliente -> Estrai tag** e completa l'estrazione tag per rigenerare il DB.")
        st.page_link(PagePaths.MANAGE, label="Vai a Gestisci cliente", icon="➡️")
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
    except Exception as exc:
        _log_semantics_failure(
            logger,
            "ui.semantics.step_status_failed",
            exc,
            extra={"slug": slug, "action_id": "enrich", "status": "done"},
        )


def _run_summary(slug: str, *, layout: WorkspaceLayout | None = None) -> None:
    try:
        _require_semantic_gating(slug, reuse_last=True)
    except ConfigError:
        tags_ok, sem_dir = tagging_ready(slug)
        if not tags_ok:
            log_gate_event(
                _GATING_LOG,
                "evidence_gate_blocked",
                fields=_gate_fields(
                    slug=slug,
                    state=get_state(slug) or "",
                    action="summary",
                    reason="summary_prerequisites_missing",
                ),
            )
            st.error("Generazione SUMMARY/README bloccata: prerequisiti normalized/tag mancanti.")
            st.caption("Verifica la presenza di Markdown in normalized/ e semantic/tags.db.")
            return
        raise
    ctx, logger, layout = _make_ctx_and_logger(slug)
    qa_marker = _qa_evidence_path(layout)
    try:
        require_qa_gate_pass(layout.logs_dir, slug=slug)
    except Exception as exc:
        reason = getattr(exc, "reason", None)
        if reason not in {"qa_evidence_missing", "qa_evidence_invalid", "qa_evidence_failed"}:
            reason = "qa_evidence_invalid"
        log_gate_event(
            _GATING_LOG,
            "qa_gate_failed",
            fields=_gate_fields(
                slug=slug,
                state=get_state(slug) or "",
                action="summary",
                reason=reason,
                evidence_path=tail_path(qa_marker),
            ),
        )
        st.error("QA Gate mancante: esegui `python -m timmy_kb.cli.qa_evidence --slug <slug>` per generare l'evidenza.")
        st.caption("Il comando produce `qa_passed.json` in logs/ e fallisce se la QA non passa.")
        return
    is_retry = _mark_retry(slug, "summary")
    try:
        ctx.set_step_status("summary", "retry" if is_retry else "start")
        if is_retry:
            log_gate_event(
                _GATING_LOG,
                "qa_gate_retry",
                fields=_gate_fields(slug=slug, state=get_state(slug) or "", action="summary"),
            )
    except Exception as exc:
        _log_semantics_failure(
            logger,
            "ui.semantics.step_status_failed",
            exc,
            extra={"slug": slug, "action_id": "summary", "status": "start", "retry": bool(is_retry)},
        )
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
    except Exception as exc:
        _log_semantics_failure(
            logger,
            "ui.semantics.step_status_failed",
            exc,
            extra={"slug": slug, "action_id": "summary", "status": "done"},
        )


def _go_preview() -> bool:
    """
    Step 4: passa dalla pagina Semantica alla pagina Docker Preview.

    """
    try:
        st.switch_page(PagePaths.PREVIEW)
        return True
    except Exception as exc:
        _log_semantics_failure(
            LOGGER,
            "ui.semantics.preview_switch_failed",
            exc,
            extra={"target": str(PagePaths.PREVIEW)},
        )
        return False


_client_state: str | None = None
_normalized_ready: bool = False
_tagging_ready: bool = False
_book_ready: bool = False
_book_dir: Path | None = None
_GATE_CACHE: dict[str, tuple[str, bool, bool, Path | None]] = {}
_ACTION_RUNS: dict[str, dict[str, int]] = {}
_GATING_LOG = get_structured_logger("ui.semantics.gating")
_GATE_PHASE_ID = "semantic"
_GATE_INTENT_ID = "ui.semantics"
_PROGRESS = {
    "pronto": "[1/3] PDF convertiti in normalized. Completa le lavorazioni semantiche.",
    "arricchito": "[2/3] Knowledge Graph creato. Puoi rifinire contenuti e chiudere il cliente.",
    "finito": "[3/3] Stato chiuso manualmente dall'utente.",
}


def _gate_fields(
    *,
    slug: str | None,
    state: str,
    action: str,
    **extra: Any,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "slug": slug or "",
        "state_id": state or "",
        "phase_id": _GATE_PHASE_ID,
        "intent_id": _GATE_INTENT_ID,
        "action_id": action,
    }
    payload.update(extra)
    return payload


def _mark_retry(slug: str, action: str) -> bool:
    action_map = _ACTION_RUNS.setdefault(slug, {})
    action_map[action] = action_map.get(action, 0) + 1
    return action_map[action] > 1


def _log_gating_block(
    slug: str | None, state: str, normalized_ready: bool, normalized_dir: Path | None, *, reason: str | None = None
) -> None:
    try:
        _GATING_LOG.info(
            "ui.semantics.gating_blocked",
            extra={
                "slug": slug or "",
                "state": state or "n/d",
                "normalized_ready": bool(normalized_ready),
                "normalized_path": tail_path(normalized_dir) if normalized_dir else "",
                "reason": reason or "",
            },
        )
        log_gate_event(
            _GATING_LOG,
            "evidence_gate_blocked",
            fields=_gate_fields(
                slug=slug,
                state=state,
                action="gating_blocked",
                reason=reason or "",
            ),
        )
    except Exception as exc:
        _log_semantics_failure(
            _GATING_LOG,
            "ui.semantics.gating_block_log_failed",
            exc,
            extra={"slug": slug or "", "state": state or "n/d"},
        )


def _raise_semantic_unavailable(
    slug: str | None, state: str, normalized_ready: bool, normalized_dir: Path | None
) -> None:
    reason = "invalid_state" if state not in ALLOWED_STATES else "normalized_missing"
    _log_gating_block(slug, state, normalized_ready, normalized_dir, reason=reason)
    normalized_display = tail_path(normalized_dir) if normalized_dir else "n/d"
    raise ConfigError(
        f"Semantica non disponibile ({reason}; state={state or 'n/d'}, normalized={normalized_display})",
        slug=slug,
        file_path=normalized_dir,
        code=reason,
    )


def _handle_semantic_action(action: Callable[[str], None], slug: str) -> bool:
    """Wrapper comune per gestire le eccezioni UI delle azioni semantiche."""
    try:
        action(slug)
        return True
    except (ConfigError, ConversionError) as exc:
        _display_user_error(exc)
        return False
    except Exception as exc:  # pragma: no cover
        _display_user_error(exc)
        return False


def main() -> None:
    """Entry point Streamlit per la pagina Semantica."""

    slug = cast(str, render_chrome_then_require())
    try:
        layout = get_ui_workspace_layout(slug, require_drive_env=False)
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

    global _client_state, _normalized_ready, _tagging_ready, _book_ready, _book_dir

    if has_ctx:
        _client_state, _normalized_ready, _ = _require_semantic_gating(slug)
        _tagging_ready, _ = tagging_ready(slug)
        _book_dir = layout.book_dir
        _book_ready = is_book_ready(_book_dir)

    if _column_button(st, "Rileva Markdown in normalized", key="btn_rescan_normalized", width="stretch"):
        cache_key = (slug or "<none>").strip().lower()
        _GATE_CACHE.pop(cache_key, None)
        _reset_gating_cache(slug)
        normalized_ready(slug)
        st.toast("Stato normalized aggiornato.")

    # Abilita i passi semantici quando il cliente e' in stato valido e normalized e' pronto.
    # I prerequisiti specifici (es. tagging/vocab) vengono verificati dentro le singole azioni.
    client_state_ok = (_client_state in SEMANTIC_ENTRY_STATES) and bool(_normalized_ready)

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

    if (_client_state or "").strip().lower() == "arricchito":
        if _column_button(
            st,
            "Segna cliente come finito",
            key="btn_semantics_set_finished",
            type="primary",
            width="stretch",
        ):
            try:
                set_client_state(slug, "finito")
                _reset_gating_cache(slug)
                st.toast("Stato cliente aggiornato a 'finito'.")
                rerun_fn = getattr(st, "rerun", None)
                if callable(rerun_fn):
                    rerun_fn()
            except Exception as exc:  # pragma: no cover
                _log_semantics_failure(
                    LOGGER,
                    "ui.semantics.client_state.finish_failed",
                    exc,
                    extra={"slug": slug},
                )
                st.error(f"Impossibile aggiornare lo stato a 'finito': {exc}")


if __name__ == "__main__":  # pragma: no cover
    main()
