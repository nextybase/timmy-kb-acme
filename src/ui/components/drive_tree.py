# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import io
from typing import Any, Dict, Iterable, List, Optional, cast

from pipeline.drive_utils import delete_drive_file as _delete_drive_file
from pipeline.exceptions import CapabilityUnavailableError
from pipeline.logging_utils import get_structured_logger
from ui.services.drive_runner import MIME_FOLDER, get_drive_service, list_drive_files
from ui.utils.context_cache import get_client_context

try:
    import streamlit as st
except Exception:  # pragma: no cover
    st = None

_LOGGER = get_structured_logger("ui.components.drive_tree")
_FIELDS_MINIMAL = "nextPageToken, files(id, name, mimeType, size, modifiedTime)"


def _parse_mtime(value: Optional[str]) -> Optional[float]:
    if not value:
        return None
    try:
        from email.utils import parsedate_to_datetime

        dt = parsedate_to_datetime(value)
        return dt.timestamp()
    except Exception:  # pragma: no cover
        return None


def _as_meta(entry: Dict[str, Any]) -> Dict[str, Any]:
    mime = entry.get("mimeType")
    node_type = "dir" if mime == MIME_FOLDER else "file"
    size_raw = entry.get("size")
    size: Optional[int]
    try:
        size = int(size_raw) if size_raw is not None else None
    except (TypeError, ValueError):  # pragma: no cover
        size = None
    return {
        "type": node_type,
        "size": size,
        "mtime": _parse_mtime(entry.get("modifiedTime")),
    }


def _human_size(size: Optional[int]) -> str:
    if not size:
        return ""
    units = ["B", "KB", "MB", "GB", "TB"]
    value = float(size)
    for unit in units:
        if value < 1024.0 or unit == units[-1]:
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} {unit}"
        value /= 1024.0
    return f"{size} B"


def _list_children(service: Any, parent_id: str) -> List[Dict[str, Any]]:
    files: List[Dict[str, Any]] = []
    if not callable(list_drive_files):  # pragma: no cover
        raise CapabilityUnavailableError(
            "Google Drive capability not available. Install extra dependencies with: pip install .[drive]"
        )
    for item in list_drive_files(service, parent_id, fields=_FIELDS_MINIMAL):
        files.append(item)
    files.sort(key=lambda f: (0 if f.get("mimeType") == MIME_FOLDER else 1, (f.get("name") or "").lower()))
    return files


def _find_child_folder(service: Any, parent_id: str, name: str) -> Optional[Dict[str, Any]]:
    if not callable(list_drive_files):  # pragma: no cover
        raise CapabilityUnavailableError(
            "Google Drive capability not available. Install extra dependencies with: pip install .[drive]"
        )
    query_name = name.replace("'", "\\'")
    query = "mimeType = 'application/vnd.google-apps.folder' " f"and name = '{query_name}'"
    for item in list_drive_files(service, parent_id, query=query, fields=_FIELDS_MINIMAL):
        return cast(Dict[str, Any], item)
    return None


def _render_entry_line(label: str, meta: Dict[str, Any], depth: int = 0, suffix: str = "") -> None:
    if st is None:  # pragma: no cover
        return
    icon = "[DIR]" if meta.get("type") == "dir" else "[FILE]"
    size_label = _human_size(meta.get("size"))
    details = f" size={size_label}" if size_label else ""
    if suffix:
        details += f" {suffix}"
    indent = " " * (depth * 2)
    line = f"{indent}{icon} {label}{details}"
    st.text(line)


def _clear_tree_cache_best_effort() -> None:
    try:
        from ui.app_services.drive_cache import _clear_drive_tree_cache

        _clear_drive_tree_cache()
    except Exception:  # pragma: no cover
        return


def _find_files_by_name(service: Any, parent_id: str, file_name: str) -> List[Dict[str, Any]]:
    query_name = file_name.replace("'", "\\'")
    query = f"'{parent_id}' in parents and name = '{query_name}' and trashed = false"
    if not callable(list_drive_files):  # pragma: no cover
        raise CapabilityUnavailableError(
            "Google Drive capability not available. Install extra dependencies with: pip install .[drive]"
        )
    return [
        cast(Dict[str, Any], item)
        for item in list_drive_files(service, parent_id, query=query, fields="files(id,name)")
    ]


def _upload_or_update_drive_file(
    *,
    service: Any,
    parent_id: str,
    file_name: str,
    payload: bytes,
    mime_type: str,
) -> str:
    from googleapiclient.http import MediaIoBaseUpload

    if not file_name.strip():
        raise RuntimeError("Nome file non valido.")

    media = MediaIoBaseUpload(io.BytesIO(payload), mimetype=mime_type or "application/octet-stream", resumable=False)
    matches = _find_files_by_name(service, parent_id, file_name)
    if len(matches) > 1:
        raise RuntimeError(f"Più file con nome '{file_name}' nella cartella selezionata.")

    if matches:
        file_id = str(matches[0].get("id") or "")
        if not file_id:
            raise RuntimeError(f"File id non valido per '{file_name}'.")
        updated = (
            service.files()
            .update(
                fileId=file_id,
                media_body=media,
                supportsAllDrives=True,
                fields="id",
            )
            .execute()
        )
        return str(updated.get("id") or file_id)

    created = (
        service.files()
        .create(
            body={"name": file_name, "parents": [parent_id], "mimeType": mime_type or "application/octet-stream"},
            media_body=media,
            supportsAllDrives=True,
            fields="id",
        )
        .execute()
    )
    return str(created.get("id") or "")


def _open_drive_upload_modal(
    *,
    service: Any,
    slug: str,
    folder_name: str,
    folder_id: str,
) -> None:
    if st is None:  # pragma: no cover
        return
    dialog_factory = getattr(st, "dialog", None)
    if not callable(dialog_factory):
        st.error("Upload non disponibile: Streamlit dialog non supportato in questo runtime.")
        return

    def _modal() -> None:
        st.caption(f"Carica file in `raw/{folder_name}` (Drive).")
        files = st.file_uploader(
            "Trascina qui i file oppure clicca per selezionarli",
            accept_multiple_files=True,
            key=f"drive_upload_files_{slug}_{folder_name}",
        )
        if files:
            st.caption(f"File pronti: {len(files)}")
        c_cancel, c_upload = st.columns(2)
        if c_cancel.button("Annulla", key=f"drive_upload_cancel_{slug}_{folder_name}"):
            return
        if c_upload.button("Carica", type="primary", key=f"drive_upload_submit_{slug}_{folder_name}"):
            if not files:
                st.warning("Seleziona almeno un file da caricare.")
                return
            valid_files: List[tuple[str, bytes, str]] = []
            total_bytes = 0
            for up in files:
                file_name = str(getattr(up, "name", "") or "").strip()
                payload = up.getvalue()
                if not file_name or payload is None:
                    continue
                mime_type = str(getattr(up, "type", "") or "application/octet-stream")
                valid_files.append((file_name, payload, mime_type))
                total_bytes += len(payload)
            if not valid_files:
                st.warning("Nessun file valido da caricare.")
                return

            progress = st.progress(0, text="Preparazione upload...")
            status_box = st.empty()
            uploaded_count = 0
            uploaded_bytes = 0
            for file_name, payload, mime_type in valid_files:
                status_box.caption(f"Carico `{file_name}` ({_human_size(len(payload))})...")
                _upload_or_update_drive_file(
                    service=service,
                    parent_id=folder_id,
                    file_name=file_name,
                    payload=payload,
                    mime_type=mime_type,
                )
                uploaded_count += 1
                uploaded_bytes += len(payload)
                progress_value = int((uploaded_bytes / max(total_bytes, 1)) * 100)
                progress.progress(
                    min(progress_value, 100),
                    text=(
                        f"Upload {uploaded_count}/{len(valid_files)} file - "
                        f"{_human_size(uploaded_bytes)} / {_human_size(total_bytes)}"
                    ),
                )
            progress.progress(100, text=f"Upload completato: {_human_size(uploaded_bytes)}")
            status_box.caption("Operazione completata.")
            _LOGGER.info(
                "drive_tree.upload_completed",
                extra={"slug": slug, "folder": folder_name, "uploaded_count": uploaded_count},
            )
            st.toast(f"Upload completato in raw/{folder_name}: {uploaded_count} file.")
            _clear_tree_cache_best_effort()
            rerun_fn = getattr(st, "rerun", None)
            if callable(rerun_fn):
                rerun_fn()

    open_modal = dialog_factory(f"Upload su Drive - raw/{folder_name}", width="large")
    runner = open_modal(_modal)
    if callable(runner):
        runner()
    else:
        _modal()


def _render_drive_file_row(
    *,
    service: Any,
    slug: str,
    sub_name: str,
    entry: Dict[str, Any],
) -> None:
    if st is None:  # pragma: no cover
        return
    file_name = str(entry.get("name") or "")
    file_id = str(entry.get("id") or "")
    file_meta = _as_meta(entry)
    size_label = _human_size(file_meta.get("size"))
    caption = f"`{file_name}`" + (f" ({size_label})" if size_label else "")

    c_name, c_delete = st.columns([0.9, 0.1])
    with c_name:
        st.markdown(caption)
    with c_delete:
        key = f"drive_del_{slug}_{sub_name}_{file_id or file_name}"
        if st.button("🗑️", key=key, help=f"Elimina {file_name} da Drive", type="secondary"):
            if not file_id:
                st.error(f"Impossibile eliminare `{file_name}`: id file Drive non disponibile.")
                return
            try:
                _delete_drive_file(service, file_id, redact_logs=False)
                _LOGGER.info(
                    "drive_tree.file_deleted",
                    extra={"slug": slug, "folder": sub_name, "file": file_name, "file_id": file_id},
                )
                st.toast(f"Eliminato da Drive: {file_name}")
                _clear_tree_cache_best_effort()
                rerun_fn = getattr(st, "rerun", None)
                if callable(rerun_fn):
                    rerun_fn()
            except Exception as exc:
                _LOGGER.warning(
                    "drive_tree.file_delete_failed",
                    extra={"slug": slug, "folder": sub_name, "file": file_name, "error": str(exc)},
                )
                st.error(f"Eliminazione non riuscita per `{file_name}`: {exc}")


def _summarise_entries(entries: Iterable[Dict[str, Any]]) -> str:
    total = 0
    files = 0
    for entry in entries:
        total += 1
        if entry.get("mimeType") != MIME_FOLDER:
            files += 1
    if total == 0:
        return "vuoto"
    if files == total:
        return f"{files} file"
    return f"{total} elementi, {files} file"


def render_drive_tree(slug: str) -> Dict[str, Dict[str, Any]]:
    """Renderizza l'albero Drive del cliente e ritorna un indice dei metadati."""
    index: Dict[str, Dict[str, Any]] = {}
    if st is None:
        return index
    try:
        ctx = get_client_context(slug, require_drive_env=True)
    except Exception as exc:  # pragma: no cover
        st.error("Impossibile inizializzare il contesto Drive.")
        _LOGGER.warning("drive_tree.context_failed", extra={"slug": slug, "error": str(exc)})
        return index

    drive_parent_id = getattr(ctx, "env", {}).get("DRIVE_ID") if getattr(ctx, "env", None) else None
    if not drive_parent_id:
        st.warning("Variabile DRIVE_ID assente. Configura l'ambiente e riprova.")
        return index

    try:
        service = get_drive_service(ctx)
    except CapabilityUnavailableError as exc:
        _LOGGER.error(
            "ui.drive.failure",
            extra={
                "reason": "capability_unavailable",
                "capability": "drive",
                "error": str(exc),
            },
        )
        st.error(str(exc))
        raise
    except Exception as exc:  # pragma: no cover
        st.error("Connessione a Google Drive fallita.")
        _LOGGER.warning("drive_tree.service_failed", extra={"slug": slug, "error": str(exc)})
        return index

    slug_folder = _find_child_folder(service, drive_parent_id, slug)
    if not slug_folder:
        st.warning(f"Cartella Drive '{slug}' non trovata sotto DRIVE_ID.")
        return index

    st.subheader(f"Albero Drive (DRIVE_ID/{slug})")
    st.caption("Focus su raw/ e sottocartelle.")
    children = _list_children(service, slug_folder["id"])
    raw_entry: Optional[Dict[str, Any]] = None
    for entry in children:
        name = entry.get("name") or ""
        rel_path = name
        meta = _as_meta(entry)
        index[rel_path] = meta
        if meta["type"] == "dir" and name == "raw":
            raw_entry = entry
            break

    if raw_entry is None:
        st.warning("Cartella `raw/` non presente nel client su Drive.")
        return index

    raw_meta = _as_meta(raw_entry)
    index["raw"] = raw_meta
    raw_children = _list_children(service, raw_entry["id"])
    with st.expander("raw/", expanded=True):
        _render_entry_line(f"{slug}/raw", raw_meta, depth=0, suffix=_summarise_entries(raw_children))
        for sub in raw_children:
            sub_name = sub.get("name") or ""
            sub_rel = f"raw/{sub_name}"
            sub_meta = _as_meta(sub)
            index[sub_rel] = sub_meta
            if sub_meta["type"] != "dir":
                continue
            sub_items = _list_children(service, sub["id"])
            sub_files: List[Dict[str, Any]] = []
            sub_dirs: List[Dict[str, Any]] = []
            for item in sub_items:
                item_name = item.get("name") or ""
                item_rel = f"raw/{sub_name}/{item_name}"
                item_meta = _as_meta(item)
                index[item_rel] = item_meta
                if item_meta["type"] == "dir":
                    sub_dirs.append(item)
                else:
                    sub_files.append(item)

            with st.expander(f"{sub_name}/ ({len(sub_files)} file)", expanded=False):
                c_actions, _ = st.columns([0.3, 0.7])
                with c_actions:
                    if st.button(
                        "⬆ Upload",
                        key=f"drive_upload_open_{slug}_{sub_name}",
                        help=f"Carica file in raw/{sub_name} su Drive.",
                        type="secondary",
                    ):
                        try:
                            _open_drive_upload_modal(
                                service=service,
                                slug=slug,
                                folder_name=sub_name,
                                folder_id=str(sub.get("id") or ""),
                            )
                        except Exception as exc:
                            _LOGGER.warning(
                                "drive_tree.upload_failed",
                                extra={"slug": slug, "folder": sub_name, "error": str(exc)},
                            )
                            st.error(f"Upload non riuscito in raw/{sub_name}: {exc}")
                if not sub_items:
                    st.caption("Cartella vuota.")
                for item in sub_files:
                    _render_drive_file_row(
                        service=service,
                        slug=slug,
                        sub_name=sub_name,
                        entry=item,
                    )
                if sub_dirs:
                    st.caption("Sottocartelle presenti:")
                    for dir_item in sub_dirs:
                        dir_name = dir_item.get("name") or ""
                        _render_entry_line(
                            f"{slug}/raw/{sub_name}/{dir_name}",
                            _as_meta(dir_item),
                            depth=0,
                            suffix="(cartella)",
                        )
    return index
