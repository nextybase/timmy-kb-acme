# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

import csv
import io
import json
from pathlib import Path
from textwrap import dedent
from typing import Any, Callable, Mapping, Optional

import yaml

from pipeline.exceptions import ConfigError
from pipeline.path_utils import ensure_within_and_resolve, read_text_safe
from pipeline.tracing import start_decision_span
from storage.tags_store import import_tags_yaml_to_db
from ui.clients_store import get_state as _get_client_state
from ui.utils.core import safe_write_text

__all__ = [
    "handle_tags_raw_save",
    "handle_tags_raw_enable",
    "enable_tags_service",
    "enable_tags_stub",
    "open_tags_editor_modal",
    "open_tags_raw_modal",
]

DEFAULT_TAGS_YAML = (
    dedent(
        """\
    version: 2
    keep_only_listed: true
    tags: []
    """
    ).strip()
    + "\n"
)

DEFAULT_TAGS_CSV = "relative_path,suggested_tags,entities,keyphrases,score,sources\n"

ALLOWED_TAG_ACTIONS = {"keep", "drop", "merge"}


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
):
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
        attributes=base_attrs,
    )


def _lookup_client_state(slug: str) -> str | None:
    try:
        return _get_client_state(slug)
    except Exception:
        return None


def _validate_tags_yaml_payload(content: str) -> dict[str, Any]:
    """Valida la struttura minima di `tags_reviewed.yaml` e ritorna il payload."""
    parsed = yaml.safe_load(content)
    if not isinstance(parsed, dict):
        raise ConfigError("Top-level YAML deve essere un mapping")
    version = str(parsed.get("version") or "").strip()
    if version not in {"2", "2.0"}:
        raise ConfigError("Campo 'version' mancante o non supportato (atteso '2').")
    keep_only_listed = parsed.get("keep_only_listed")
    if not isinstance(keep_only_listed, bool):
        raise ConfigError("Campo 'keep_only_listed' deve essere booleano.")
    tags_payload = parsed.get("tags")
    if not isinstance(tags_payload, list):
        raise ConfigError("Campo 'tags' deve essere una lista.")
    for idx, item in enumerate(tags_payload):
        if not isinstance(item, dict):
            raise ConfigError(f"Elemento tags[{idx}] deve essere un mapping.")
        name = item.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ConfigError(f"Elemento tags[{idx}] privo di 'name' valido.")
        action = item.get("action") or "keep"
        if not isinstance(action, str):
            raise ConfigError(f"Elemento tags[{idx}] ha 'action' non valido.")
        normalized_action = action.strip().lower()
        if normalized_action not in ALLOWED_TAG_ACTIONS:
            allowed = ", ".join(sorted(ALLOWED_TAG_ACTIONS))
            raise ConfigError(f"Elemento tags[{idx}] ha 'action' non supportato " f"(consentiti: {allowed}).")
        item["action"] = normalized_action
        synonyms = item.get("synonyms")
        if synonyms is not None:
            if not isinstance(synonyms, list) or any(not isinstance(s, str) for s in synonyms):
                raise ConfigError(f"Elemento tags[{idx}] ha 'synonyms' non valido (lista di stringhe attesa).")
        note = item.get("note") or ""
        if not isinstance(note, str):
            raise ConfigError(f"Elemento tags[{idx}] ha 'note' non valido (stringa attesa).")
        item["note"] = note
    return parsed


def handle_tags_raw_save(
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


def enable_tags_stub(
    slug: str,
    semantic_dir: Path,
    yaml_path: Path,
    *,
    st: Any,
    logger: Any,
    set_client_state: Callable[[str, str], bool],
    reset_gating_cache: Callable[[str | None], None],
    read_fn: Optional[Callable[..., str | None]] = None,
    write_fn: Optional[Callable[..., None]] = None,
    import_yaml_fn: Optional[Callable[..., Any]] = None,
) -> bool:
    try:
        semantic_dir.mkdir(parents=True, exist_ok=True)
        reader = read_fn or read_text_safe
        writer = write_fn or safe_write_text
        importer = import_yaml_fn or import_tags_yaml_to_db
        previous: str | None = None
        try:
            previous = reader(semantic_dir, yaml_path, encoding="utf-8")
        except Exception:
            previous = None
        importer_counts: dict[str, int] | None = None
        created_stub = False
        if not yaml_path.exists():
            writer(yaml_path, DEFAULT_TAGS_YAML, encoding="utf-8", atomic=True)
            created_stub = True

        if yaml_path.exists():
            try:
                importer_counts = importer(yaml_path, logger=logger)
                logger.info("ui.manage.tags.db_synced", extra={"slug": slug, "path": str(yaml_path)})
                if created_stub:
                    with _human_override_span(logger, slug, st, phase="ui.manage.tags_yaml", reason="stub_created"):
                        logger.info(
                            "ui.manage.tags.stub_created",
                            extra={"slug": slug, "path": str(yaml_path)},
                        )
            except Exception as exc:
                if previous is not None:
                    writer(yaml_path, previous, encoding="utf-8", atomic=True)
                    logger.warning(
                        "ui.manage.tags.rollback",
                        extra={"slug": slug, "path": str(yaml_path), "reason": "stub-db-error"},
                    )
                logger.warning(
                    "ui.manage.tags.db_sync_failed",
                    extra={"slug": slug, "path": str(yaml_path), "error": str(exc)},
                )
                st.error(f"Sincronizzazione tags.db non riuscita: {exc}")
                return False
        else:
            logger.warning(
                "ui.manage.tags.db_sync_skipped",
                extra={"slug": slug, "path": str(yaml_path), "reason": "file-missing"},
            )

        has_terms = bool(importer_counts and importer_counts.get("terms"))
        target_state = "arricchito" if has_terms else "pronto"
        previous_state = _lookup_client_state(slug)
        decision_attrs = {
            "previous_value": previous_state,
            "new_value": target_state,
        }
        updated = False
        decision_span_value: Any | None = None
        try:
            with _human_override_span(
                logger,
                slug,
                st,
                phase="ui.manage.tags_yaml",
                reason="state_override",
                attributes=decision_attrs,
            ) as decision_span_value:
                updated = set_client_state(slug, target_state)
                if decision_span_value is not None:
                    decision_span_value.set_attribute("status", "success" if updated else "failed")
        except Exception as exc:
            if decision_span_value is not None:
                decision_span_value.set_attribute("status", "failed")
            logger.warning("ui.manage.state.update_failed", extra={"slug": slug, "error": str(exc)})
            updated = False

        if updated:
            if has_terms:
                st.toast("`tags_reviewed.yaml` generato (stub). Stato aggiornato a 'arricchito'.")
            else:
                st.warning(
                    "Vocabolario ancora vuoto: stato riportato a 'pronto'. Compila lo YAML prima dell'arricchimento."
                )
            reset_gating_cache(slug)
        else:
            st.error("Aggiornamento stato cliente non riuscito: verifica clients_db/clients.yaml.")
            logger.error("ui.manage.state.update_failed", extra={"slug": slug, "target": target_state})
            return False

        with _human_override_span(logger, slug, st, phase="ui.manage.tags_yaml", reason="stub_publish"):
            logger.info("ui.manage.tags_yaml.published_stub", extra={"slug": slug, "path": str(yaml_path)})
        return True
    except Exception as exc:
        st.error(f"Abilitazione (stub) non riuscita: {exc}")
        logger.warning("ui.manage.tags_yaml.stub_error", extra={"slug": slug, "error": str(exc)})
        return False


def enable_tags_service(
    slug: str,
    semantic_dir: Path,
    csv_path: Path,
    yaml_path: Path,
    *,
    st: Any,
    logger: Any,
    set_client_state: Callable[[str, str], bool],
    reset_gating_cache: Callable[[str | None], None],
) -> bool:
    try:
        from semantic.api import export_tags_yaml_from_db
        from semantic.tags_io import write_tags_review_stub_from_csv
        from storage.tags_store import derive_db_path_from_yaml_path

        if not csv_path.exists():
            st.error("`tags_raw.csv` mancante: salva o rigenera il CSV prima di abilitare la semantica.")
            logger.warning(
                "ui.manage.tags_raw.missing",
                extra={"slug": slug, "path": str(csv_path)},
            )
            return False

        write_tags_review_stub_from_csv(semantic_dir, csv_path, logger)
        db_path = Path(derive_db_path_from_yaml_path(yaml_path))
        export_tags_yaml_from_db(
            semantic_dir,
            db_path,
            logger,
            workspace_base=semantic_dir.parent,
        )
        previous_state = _lookup_client_state(slug)
        decision_attrs = {
            "previous_value": previous_state,
            "new_value": "arricchito",
        }
        updated = False
        decision_span_value: Any | None = None
        try:
            with _human_override_span(
                logger,
                slug,
                st,
                phase="ui.manage.tags_yaml",
                reason="manual_publish",
                attributes=decision_attrs,
            ) as decision_span_value:
                updated = set_client_state(slug, "arricchito")
                if decision_span_value is not None:
                    decision_span_value.set_attribute("status", "success" if updated else "failed")
        except Exception as exc:
            if decision_span_value is not None:
                decision_span_value.set_attribute("status", "failed")
            logger.warning("ui.manage.state.update_failed", extra={"slug": slug, "error": str(exc)})
            updated = False
        if updated:
            st.toast("`tags_reviewed.yaml` generato. Stato aggiornato a 'arricchito'.")
            reset_gating_cache(slug)
        else:
            st.error("Abilitazione semantica riuscita ma aggiornamento stato fallito.")
            logger.error("ui.manage.state.update_failed", extra={"slug": slug, "target": "arricchito"})
            return False
        with _human_override_span(logger, slug, st, phase="ui.manage.tags_yaml", reason="manual_publish"):
            logger.info("ui.manage.tags_yaml.published", extra={"slug": slug, "path": str(yaml_path)})
        return True
    except Exception as exc:
        st.error(f"Abilitazione non riuscita: {exc}")
        logger.warning("ui.manage.tags_yaml.publish.error", extra={"slug": slug, "error": str(exc)})
        return False


def handle_tags_raw_enable(
    slug: str,
    semantic_dir: Path,
    csv_path: Path,
    yaml_path: Path,
    *,
    st: Any,
    logger: Any,
    tags_mode: str,
    run_tags_fn: Optional[Callable[[str], Any]],
    set_client_state: Callable[[str, str], bool],
    reset_gating_cache: Callable[[str | None], None],
    read_fn: Optional[Callable[..., str | None]] = None,
    write_fn: Optional[Callable[..., None]] = None,
    import_yaml_fn: Optional[Callable[..., Any]] = None,
) -> bool:
    if tags_mode == "stub":
        return enable_tags_stub(
            slug,
            semantic_dir,
            yaml_path,
            st=st,
            logger=logger,
            set_client_state=set_client_state,
            reset_gating_cache=reset_gating_cache,
            read_fn=read_fn,
            write_fn=write_fn,
            import_yaml_fn=import_yaml_fn,
        )
    if run_tags_fn is None and tags_mode != "stub":
        logger.error(
            "ui.manage.tags.service_missing",
            extra={"slug": slug, "mode": tags_mode or "default"},
        )
        st.error("Servizio di estrazione tag non disponibile.")
        return False
    return enable_tags_service(
        slug,
        semantic_dir,
        csv_path,
        yaml_path,
        st=st,
        logger=logger,
        set_client_state=set_client_state,
        reset_gating_cache=reset_gating_cache,
    )


def open_tags_editor_modal(
    slug: str,
    base_dir: Path,
    *,
    st: Any,
    logger: Any,
    column_button: Callable[..., bool],
    set_client_state: Callable[[str, str], bool],
    reset_gating_cache: Callable[[str | None], None],
    path_resolver: Callable[[Path, Path], Path] = ensure_within_and_resolve,
    read_fn: Optional[Callable[..., str | None]] = None,
    write_fn: Optional[Callable[..., None]] = None,
    import_yaml_fn: Optional[Callable[..., Any]] = None,
) -> None:
    yaml_path = Path(path_resolver(base_dir, base_dir / "semantic" / "tags_reviewed.yaml"))
    yaml_parent = yaml_path.parent
    reader = read_fn or read_text_safe
    writer = write_fn or safe_write_text
    importer = import_yaml_fn or import_tags_yaml_to_db
    try:
        initial_text = reader(yaml_parent, yaml_path, encoding="utf-8")
    except Exception:
        initial_text = DEFAULT_TAGS_YAML
    logger.info("ui.manage.tags.open", extra={"slug": slug})
    dialog_factory = getattr(st, "dialog", None)

    def _editor_body() -> None:
        caption_fn = getattr(st, "caption", None)
        if callable(caption_fn):
            caption_fn("Modifica e salva il file `semantic/tags_reviewed.yaml`.")
        content = st.text_area(
            "Contenuto YAML",
            value=initial_text,
            height=420,
            key="tags_yaml_editor",
            label_visibility="collapsed",
        )
        col_a, col_b = st.columns(2)
        if column_button(col_a, "Salva", type="primary"):
            try:
                _validate_tags_yaml_payload(content)
            except Exception as exc:
                st.error(f"YAML non valido: {exc}")
                logger.warning("ui.manage.tags.yaml.invalid", extra={"slug": slug, "error": str(exc)})
                return
            backup_text: Optional[str]
            try:
                try:
                    backup_text = reader(yaml_parent, yaml_path, encoding="utf-8")
                except Exception:
                    backup_text = None
                logger.info("ui.manage.tags.yaml.valid", extra={"slug": slug})
                yaml_parent.mkdir(parents=True, exist_ok=True)
                writer(yaml_path, content, encoding="utf-8", atomic=True)
                if yaml_path.exists():
                    try:
                        importer(yaml_path, logger=logger)
                        logger.info("ui.manage.tags.db_synced", extra={"slug": slug, "path": str(yaml_path)})
                    except Exception as exc:
                        if backup_text is not None:
                            writer(yaml_path, backup_text, encoding="utf-8", atomic=True)
                            logger.warning(
                                "ui.manage.tags.rollback",
                                extra={"slug": slug, "path": str(yaml_path), "reason": "db-sync-error"},
                            )
                        logger.warning(
                            "ui.manage.tags.db_sync_failed",
                            extra={"slug": slug, "path": str(yaml_path), "error": str(exc)},
                        )
                        st.error(f"Sincronizzazione tags.db non riuscita: {exc}")
                        return
                else:
                    logger.warning(
                        "ui.manage.tags.db_sync_skipped",
                        extra={"slug": slug, "path": str(yaml_path), "reason": "file-missing"},
                    )
                st.toast("`tags_reviewed.yaml` salvato.")
                logger.info("ui.manage.tags.save", extra={"slug": slug, "path": str(yaml_path)})
                reset_gating_cache(slug)
                st.rerun()
            except Exception as exc:
                if backup_text is not None:
                    writer(yaml_path, backup_text, encoding="utf-8", atomic=True)
                    logger.warning(
                        "ui.manage.tags.rollback",
                        extra={"slug": slug, "path": str(yaml_path), "reason": "save-exception"},
                    )
                st.error(f"Errore nel salvataggio: {exc}")
                logger.warning("ui.manage.tags.save.error", extra={"slug": slug, "error": str(exc)})
        if column_button(col_b, "Chiudi"):
            st.rerun()

    if dialog_factory:
        runner = dialog_factory("Modifica tags_reviewed.yaml")(_editor_body)
        runner()
    else:
        with st.container(border=True):
            st.subheader("Modifica tags_reviewed.yaml")
            _editor_body()


def open_tags_raw_modal(
    slug: str,
    base_dir: Path,
    *,
    st: Any,
    logger: Any,
    column_button: Callable[..., bool],
    tags_mode: str,
    run_tags_fn: Optional[Callable[[str], Any]],
    set_client_state: Callable[[str, str], bool],
    reset_gating_cache: Callable[[str | None], None],
    path_resolver: Callable[[Path, Path], Path] = ensure_within_and_resolve,
    read_fn: Optional[Callable[..., str | None]] = None,
    write_fn: Optional[Callable[..., None]] = None,
    import_yaml_fn: Optional[Callable[..., Any]] = None,
) -> None:
    semantic_dir = Path(path_resolver(base_dir, base_dir / "semantic"))
    csv_path = Path(path_resolver(semantic_dir, semantic_dir / "tags_raw.csv"))
    yaml_path = Path(path_resolver(semantic_dir, semantic_dir / "tags_reviewed.yaml"))
    reader = read_fn or read_text_safe
    writer = write_fn or safe_write_text
    importer = import_yaml_fn or import_tags_yaml_to_db
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
                "Modifica `semantic/tags_raw.csv`. **Salva raw** aggiorna il CSV; "
                "**Abilita** genera `tags_reviewed.yaml` e abilita la Semantica."
            )

        content = st.text_area(
            "Contenuto CSV",
            value=initial_text,
            height=420,
            key="tags_csv_editor",
            label_visibility="collapsed",
        )

        def _render_tags_preview(csv_text: str) -> None:
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
                try:
                    parsed = json.loads(tags_raw)
                    if isinstance(parsed, list):
                        tags_list = [str(t).strip() for t in parsed if str(t).strip()]
                    else:
                        tags_list = []
                except Exception:
                    tags_list = [t.strip() for t in tags_raw.split(",") if t.strip()]
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

        if column_button(col_a, "Salva raw", type="secondary"):
            handle_tags_raw_save(
                slug,
                content,
                csv_path,
                semantic_dir,
                st=st,
                logger=logger,
                write_fn=writer,
            )

        enable_disabled = tags_mode != "stub" and run_tags_fn is None
        enable_help = (
            "Abilita genera `tags_reviewed.yaml` e aggiorna il DB semantico."
            if not enable_disabled
            else "Servizio tagging non disponibile: installa/abilita `ui.services.tags_adapter` o usa TAGS_MODE=stub."
        )
        if column_button(
            col_b,
            "Abilita",
            type="primary",
            disabled=enable_disabled,
            help=enable_help,
        ):
            if handle_tags_raw_enable(
                slug,
                semantic_dir,
                csv_path,
                yaml_path,
                st=st,
                logger=logger,
                tags_mode=tags_mode,
                run_tags_fn=run_tags_fn,
                set_client_state=set_client_state,
                reset_gating_cache=reset_gating_cache,
                read_fn=reader,
                write_fn=writer,
                import_yaml_fn=importer,
            ):
                st.rerun()

    if dialog_factory:
        (dialog_factory("Revisione keyword (tags_raw.csv)")(_body))()
    else:
        with st.container(border=True):
            st.subheader("Revisione keyword (tags_raw.csv)")
            _body()
