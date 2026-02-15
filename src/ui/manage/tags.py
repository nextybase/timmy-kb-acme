# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import csv
import io
from pathlib import Path
from typing import Any, Callable, Mapping, Optional

from pipeline.path_utils import ensure_within_and_resolve, read_text_safe
from pipeline.tracing import start_decision_span
from storage.tags_store import ensure_schema_v2
from ui.utils.core import safe_write_text
from ui.utils.workspace import tagging_ready

__all__ = [
    "save_tags_draft_csv",
    "validate_tags_draft",
    "validate_tags_service",
    "validate_tags_stub",
    "handle_tags_raw_save",
    "handle_tags_raw_enable",
    "enable_tags_service",
    "enable_tags_stub",
    "open_tags_editor_modal",
    "open_tags_draft_modal",
    "open_tags_raw_modal",
]

DEFAULT_TAGS_CSV = "relative_path,suggested_tags,entities,keyphrases,score,sources\n"


def _resolve_user_role(st: Any | None) -> str:
    state = getattr(st, "session_state", None)
    if state is None:
        return "knowledge_manager"
    role = None
    if hasattr(state, "get"):
        role = state.get("user_role") or state.get("active_role")
    else:
        role = getattr(state, "user_role", None) or getattr(state, "active_role", None)
    return role or "knowledge_manager"


def _human_override_span(
    logger: Any,
    slug: str,
    st: Any,
    *,
    phase: str,
    reason: str,
    status: str = "applied",
    attributes: Mapping[str, Any] | None = None,
) -> Any:
    run_id = getattr(getattr(logger, "_logging_ctx_view", None), "run_id", None)
    base_attrs = {
        "hilt_involved": True,
        "user_role": _resolve_user_role(st),
        "override_reason": reason,
        "status": status,
    }
    if attributes:
        for key, value in attributes.items():
            if value is not None:
                base_attrs[key] = value
    return start_decision_span(
        "human_override",
        slug=slug,
        run_id=run_id,
        trace_kind="onboarding",
        phase=phase,
        decision_channel="human",
        policy_id="HUMAN.OVERRIDE",
        attributes=base_attrs,
    )


def _ensure_tags_db_ready(
    semantic_dir: Path,
    *,
    slug: str,
    logger: Any,
    st: Any,
    db_path: Path | None = None,
) -> Path | None:
    db_path = db_path or (semantic_dir / "tags.db")
    if not db_path.exists():
        logger.warning(
            "ui.manage.tags.db_missing",
            extra={"slug": slug, "path": str(db_path)},
        )
        st.error("`semantic/tags.db` non trovato: esegui l'onboarding semantico per generarlo.")
        stop_fn = getattr(st, "stop", None)
        if callable(stop_fn):
            stop_fn()
        return None
    try:
        ensure_schema_v2(str(db_path))
        return db_path
    except Exception as exc:
        logger.warning(
            "ui.manage.tags.db_invalid",
            extra={"slug": slug, "path": str(db_path), "error": str(exc)},
        )
        st.error("`semantic/tags.db` non valido: esegui l'onboarding semantico per rigenerarlo.")
        stop_fn = getattr(st, "stop", None)
        if callable(stop_fn):
            stop_fn()
        return None


def save_tags_draft_csv(
    slug: str,
    content: str,
    csv_path: Path,
    semantic_dir: Path,
    *,
    st: Any,
    logger: Any,
    write_fn: Optional[Callable[..., None]] = None,
) -> bool:
    header = (content.splitlines() or [""])[0]
    header_tokens = {token.strip().lower() for token in header.split(",")}
    if "suggested_tags" not in header_tokens:
        st.error("CSV non valido: manca la colonna 'suggested_tags'.")
        logger.warning("ui.manage.tags_raw.invalid_header", extra={"slug": slug})
        return False

    semantic_dir.mkdir(parents=True, exist_ok=True)
    writer = write_fn or safe_write_text
    writer(csv_path, content, encoding="utf-8", atomic=True)
    st.toast("`tags_raw.csv` salvato.")
    run_id = getattr(getattr(logger, "_logging_ctx_view", None), "run_id", None)
    with start_decision_span(
        "human_override",
        slug=slug,
        run_id=run_id,
        trace_kind="onboarding",
        phase="ui.manage.tags_raw",
        attributes={
            "hilt_involved": True,
            "user_role": _resolve_user_role(st),
            "override_reason": "manual_tags_csv",
            "status": "applied",
        },
    ):
        logger.info("ui.manage.tags_raw.saved", extra={"slug": slug, "path": str(csv_path)})
    return True


def validate_tags_service(
    slug: str,
    semantic_dir: Path,
    csv_path: Path,
    *,
    st: Any,
    logger: Any,
    set_client_state: Callable[[str, str], bool] | None = None,
    reset_gating_cache: Callable[[str | None], None],
) -> bool:
    try:
        from semantic.tags_io import write_tags_review_stub_from_csv

        if not csv_path.exists():
            st.error("`tags_raw.csv` mancante: salva o rigenera il CSV prima della validazione.")
            logger.warning(
                "ui.manage.tags_raw.missing",
                extra={"slug": slug, "path": str(csv_path)},
            )
            return False

        write_tags_review_stub_from_csv(semantic_dir, csv_path, logger)
        db_path = semantic_dir / "tags.db"
        if _ensure_tags_db_ready(semantic_dir, slug=slug, logger=logger, st=st, db_path=db_path) is None:
            return False
        tagging_ok, _ = tagging_ready(slug)
        if tagging_ok:
            if callable(set_client_state):
                set_client_state(slug, "arricchito")
            st.toast("Validazione completata: `tags.db` aggiornato.")
        else:
            st.warning("Vocabolario incompleto: verifica i tag della bozza e ripeti la validazione.")
        reset_gating_cache(slug)
        with _human_override_span(logger, slug, st, phase="ui.manage.tags_db", reason="manual_validate"):
            logger.info("ui.manage.tags_db.updated", extra={"slug": slug, "path": str(db_path)})
        return True
    except Exception as exc:
        st.error(f"Validazione non riuscita: {exc}")
        logger.warning("ui.manage.tags_db.update.error", extra={"slug": slug, "error": str(exc)})
        return False


def validate_tags_stub(
    slug: str,
    semantic_dir: Path,
    *_args: Any,
    st: Any,
    logger: Any,
    set_client_state: Callable[[str, str], bool],
    reset_gating_cache: Callable[[str | None], None],
    **_kwargs: Any,
) -> bool:
    return validate_tags_service(
        slug,
        semantic_dir,
        semantic_dir / "tags_raw.csv",
        st=st,
        logger=logger,
        set_client_state=set_client_state,
        reset_gating_cache=reset_gating_cache,
    )


def validate_tags_draft(
    slug: str,
    semantic_dir: Path,
    csv_path: Path,
    *,
    st: Any,
    logger: Any,
    set_client_state: Callable[[str, str], bool] | None = None,
    reset_gating_cache: Callable[[str | None], None],
    **_: Any,
) -> bool:
    return validate_tags_service(
        slug,
        semantic_dir,
        csv_path,
        st=st,
        logger=logger,
        set_client_state=set_client_state,
        reset_gating_cache=reset_gating_cache,
    )


def open_tags_editor_modal(
    slug: str,
    repo_root_dir: Path,
    *,
    st: Any,
    logger: Any,
    column_button: Callable[..., bool],
    set_client_state: Callable[[str, str], bool],
    reset_gating_cache: Callable[[str | None], None],
    path_resolver: Callable[[Path, Path], Path] = ensure_within_and_resolve,
    read_fn: Optional[Callable[..., str | None]] = None,
    write_fn: Optional[Callable[..., None]] = None,
) -> None:
    open_tags_draft_modal(
        slug,
        repo_root_dir,
        st=st,
        logger=logger,
        column_button=column_button,
        set_client_state=set_client_state,
        reset_gating_cache=reset_gating_cache,
        path_resolver=path_resolver,
        read_fn=read_fn,
        write_fn=write_fn,
    )


def open_tags_draft_modal(
    slug: str,
    repo_root_dir: Path,
    *,
    st: Any,
    logger: Any,
    column_button: Callable[..., bool],
    set_client_state: Callable[[str, str], bool],
    reset_gating_cache: Callable[[str | None], None],
    path_resolver: Callable[[Path, Path], Path] = ensure_within_and_resolve,
    read_fn: Optional[Callable[..., str | None]] = None,
    write_fn: Optional[Callable[..., None]] = None,
) -> None:
    perimeter_root = repo_root_dir
    semantic_dir = Path(path_resolver(perimeter_root, repo_root_dir / "semantic"))
    csv_path = Path(path_resolver(semantic_dir, semantic_dir / "tags_raw.csv"))
    reader = read_fn or read_text_safe
    writer = write_fn or safe_write_text
    try:
        initial_text = reader(semantic_dir, csv_path, encoding="utf-8")
    except Exception:
        initial_text = DEFAULT_TAGS_CSV

    logger.info("ui.manage.tags_raw.open", extra={"slug": slug})
    dialog_factory = getattr(st, "dialog", None)

    def _body() -> None:
        caption_fn = getattr(st, "caption", None)
        if callable(caption_fn):
            caption_fn(
                "Modifica `semantic/tags_raw.csv`. **Salva bozza** aggiorna il CSV; "
                "**Valida** conferma i tag e crea/aggiorna `semantic/tags.db`."
            )

        content = st.text_area(
            "Contenuto CSV",
            value=initial_text,
            height=420,
            key="tags_csv_editor",
            label_visibility="collapsed",
        )

        def _render_tags_preview(csv_text: str) -> None:
            def _parse_suggested_tags(raw_value: str) -> list[str]:
                ordered: list[str] = []
                seen: set[str] = set()
                for token in (raw_value or "").split(","):
                    tag = token.strip().lower()
                    if not tag:
                        continue
                    tag_key = tag.casefold()
                    if tag_key in seen:
                        continue
                    seen.add(tag_key)
                    ordered.append(tag)
                return ordered

            try:
                stream = io.StringIO(csv_text)
                rows = list(csv.DictReader(stream))
            except Exception:
                rows = []
            if not rows:
                st.info("Nessuna anteprima disponibile: CSV vuoto o non parsabile.")
                return
            st.markdown("**Anteprima keyword per percorso**")
            max_rows = 30
            for idx, row in enumerate(rows[:max_rows]):
                rel_path = (row.get("relative_path") or "").strip()
                tags_raw = row.get("suggested_tags") or ""
                tags_list = _parse_suggested_tags(str(tags_raw))
                label = rel_path or f"riga {idx + 2}"
                st.markdown(f"- **{label}**")
                if tags_list:
                    st.markdown("  - " + "\n  - ".join(tags_list))
                else:
                    st.caption("  Nessuna suggested_tag in questa riga.")

            if len(rows) > max_rows:
                st.caption(f"Mostrate {max_rows} righe su {len(rows)} totali.")

        with st.expander("Anteprima ad albero delle keyword", expanded=False):
            _render_tags_preview(content)

        col_a, col_b = st.columns(2)

        if column_button(col_a, "Salva bozza", type="secondary"):
            save_tags_draft_csv(
                slug,
                content,
                csv_path,
                semantic_dir,
                st=st,
                logger=logger,
                write_fn=writer,
            )

        if column_button(
            col_b,
            "Valida",
            type="primary",
            help="Valida conferma i tag della bozza e crea/aggiorna `semantic/tags.db`.",
        ):
            if validate_tags_draft(
                slug,
                semantic_dir,
                csv_path,
                st=st,
                logger=logger,
                set_client_state=set_client_state,
                reset_gating_cache=reset_gating_cache,
            ):
                st.rerun()

    if dialog_factory:
        (dialog_factory("Revisione keyword (tags_raw.csv)")(_body))()
    else:
        with st.container(border=True):
            st.subheader("Revisione keyword (tags_raw.csv)")
            _body()


handle_tags_raw_save = save_tags_draft_csv
enable_tags_stub = validate_tags_stub
enable_tags_service = validate_tags_service
handle_tags_raw_enable = validate_tags_draft
open_tags_raw_modal = open_tags_draft_modal
