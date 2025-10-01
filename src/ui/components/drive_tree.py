from __future__ import annotations

import logging
from typing import Any, Dict, Iterable, List, Optional, cast

try:
    import streamlit as st
except Exception:  # pragma: no cover
    st = None

try:
    from pipeline.context import ClientContext
    from pipeline.drive_utils import MIME_FOLDER, get_drive_service, list_drive_files
except Exception:  # pragma: no cover
    ClientContext = None
    MIME_FOLDER = "application/vnd.google-apps.folder"  # fallback literal
    get_drive_service = None
    list_drive_files = None

_LOGGER = logging.getLogger("ui.components.drive_tree")
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
        return files
    for item in list_drive_files(service, parent_id, fields=_FIELDS_MINIMAL):
        files.append(item)
    files.sort(key=lambda f: (0 if f.get("mimeType") == MIME_FOLDER else 1, (f.get("name") or "").lower()))
    return files


def _find_child_folder(service: Any, parent_id: str, name: str) -> Optional[Dict[str, Any]]:
    if not callable(list_drive_files):  # pragma: no cover
        return None
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
    if ClientContext is None or not callable(get_drive_service):
        st.info("Supporto Google Drive non disponibile nella UI.")
        return index
    try:
        ctx = ClientContext.load(slug=slug, interactive=False, require_env=True, run_id=None)
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
    except Exception as exc:  # pragma: no cover
        st.error("Connessione a Google Drive fallita.")
        _LOGGER.warning("drive_tree.service_failed", extra={"slug": slug, "error": str(exc)})
        return index

    slug_folder = _find_child_folder(service, drive_parent_id, slug)
    if not slug_folder:
        st.warning(f"Cartella Drive '{slug}' non trovata sotto DRIVE_ID.")
        return index

    root_meta = _as_meta(slug_folder)
    root_container = st.expander(f"Drive :: {slug}", expanded=True)
    with root_container:
        children = _list_children(service, slug_folder["id"])
        index["./"] = root_meta
        _render_entry_line(f"{slug}/", root_meta, depth=0, suffix=_summarise_entries(children))
        raw_entry: Optional[Dict[str, Any]] = None
        for entry in children:
            name = entry.get("name") or ""
            rel_path = name
            meta = _as_meta(entry)
            index[rel_path] = meta
            if meta["type"] == "dir" and name == "raw":
                raw_entry = entry
                continue
            _render_entry_line(f"{slug}/{name.rstrip('/')}", meta, depth=0, suffix="")

        if raw_entry is None:
            _render_entry_line(f"{slug}/raw", {"type": "dir"}, depth=0, suffix="(cartella non presente)")
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
                    _render_entry_line(f"{slug}/{sub_rel}", sub_meta, depth=1)
                    continue
                sub_items = _list_children(service, sub["id"])
                with st.expander(f"raw/{sub_name}/", expanded=False):
                    _render_entry_line(
                        f"{slug}/raw/{sub_name}",
                        sub_meta,
                        depth=0,
                        suffix=_summarise_entries(sub_items),
                    )
                    for item in sub_items:
                        item_name = item.get("name") or ""
                        item_rel = f"raw/{sub_name}/{item_name}"
                        item_meta = _as_meta(item)
                        index[item_rel] = item_meta
                        _render_entry_line(f"{slug}/{item_rel}", item_meta, depth=1)
    return index
