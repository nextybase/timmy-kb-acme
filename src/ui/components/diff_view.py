from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

try:
    import streamlit as st  # type: ignore
except Exception:  # pragma: no cover
    st = None  # type: ignore

OUTPUT_ROOT = Path(__file__).resolve().parents[3] / "output"


def _safe_mtime(path: Path) -> Optional[float]:
    try:
        return path.stat().st_mtime
    except OSError:  # pragma: no cover
        return None


def _build_local_index(raw_dir: Path) -> Dict[str, Dict[str, Any]]:
    index: Dict[str, Dict[str, Any]] = {}
    if not raw_dir.exists():
        return index
    index["raw"] = {"type": "dir", "size": None, "mtime": _safe_mtime(raw_dir)}
    for entry in raw_dir.rglob("*"):
        rel = entry.relative_to(raw_dir).as_posix()
        if not rel:
            continue
        key = f"raw/{rel}"
        if entry.is_dir():
            index[key] = {"type": "dir", "size": None, "mtime": _safe_mtime(entry)}
        else:
            try:
                stat = entry.stat()
                index[key] = {
                    "type": "file",
                    "size": int(stat.st_size),
                    "mtime": float(stat.st_mtime),
                }
            except OSError:  # pragma: no cover
                index[key] = {"type": "file", "size": None, "mtime": None}
    return index


def _human_size(size: Optional[int]) -> str:
    if size is None:
        return "-"
    units = ["B", "KB", "MB", "GB", "TB"]
    value = float(size)
    for unit in units:
        if value < 1024.0 or unit == units[-1]:
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} {unit}"
        value /= 1024.0
    return f"{size} B"


def _format_mtime(ts: Optional[float]) -> str:
    if not ts:
        return "-"
    try:
        return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:  # pragma: no cover
        return "-"


def _rows_from(keys: Iterable[str], meta_map: Dict[str, Dict[str, Any]]) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    for key in keys:
        meta = meta_map.get(key, {})
        rows.append(
            {
                "path": key,
                "type": meta.get("type", "-"),
                "size": _human_size(meta.get("size")),
                "mtime": _format_mtime(meta.get("mtime")),
            }
        )
    return rows


def render_drive_local_diff(slug: str, drive_index: Optional[Dict[str, Dict[str, Any]]]) -> None:
    if st is None:
        return

    drive_index = drive_index or {}
    drive_entries = {key: meta for key, meta in drive_index.items() if key == "raw" or key.startswith("raw/")}

    raw_dir = OUTPUT_ROOT / f"timmy-kb-{slug}" / "raw"
    local_entries = _build_local_index(raw_dir)

    drive_keys = set(drive_entries.keys())
    local_keys = set(local_entries.keys())

    only_drive = sorted(drive_keys - local_keys)
    only_local = sorted(local_keys - drive_keys)

    intersections = sorted(drive_keys & local_keys)
    differences: List[Dict[str, Any]] = []
    for key in intersections:
        drive_meta = drive_entries.get(key, {})
        local_meta = local_entries.get(key, {})
        drive_type = drive_meta.get("type")
        local_type = local_meta.get("type")
        if drive_type != local_type:
            differences.append(
                {
                    "path": key,
                    "motivo": "tipo differente",
                    "drive_size": _human_size(drive_meta.get("size")),
                    "local_size": _human_size(local_meta.get("size")),
                    "drive_mtime": _format_mtime(drive_meta.get("mtime")),
                    "local_mtime": _format_mtime(local_meta.get("mtime")),
                }
            )
            continue
        if drive_type != "file":
            continue
        size_diff = drive_meta.get("size") != local_meta.get("size")
        drive_mtime = drive_meta.get("mtime")
        local_mtime = local_meta.get("mtime")
        if drive_mtime is not None and local_mtime is not None:
            mtime_diff = abs(drive_mtime - local_mtime) > 1.0
        else:
            mtime_diff = drive_mtime != local_mtime
        if not size_diff and not mtime_diff:
            continue
        reasons: List[str] = []
        if size_diff:
            reasons.append("dimensione")
        if mtime_diff:
            reasons.append("mtime")
        differences.append(
            {
                "path": key,
                "motivo": ", ".join(reasons),
                "drive_size": _human_size(drive_meta.get("size")),
                "local_size": _human_size(local_meta.get("size")),
                "drive_mtime": _format_mtime(drive_mtime),
                "local_mtime": _format_mtime(local_mtime),
            }
        )

    if not drive_entries and not local_entries:
        st.info("Nessun artefatto disponibile: Drive e directory locale risultano vuoti.")
        return

    st.caption(
        "Confronto basato su dimensione e timestamp (sec). Differenze di timezone o sync parziale possono"
        " produrre scostamenti."
    )

    col_drive, col_local, col_diff = st.columns(3)
    col_drive.metric("Solo Drive", len(only_drive))
    col_local.metric("Solo locale", len(only_local))
    col_diff.metric("Differenze", len(differences))

    with st.expander("Solo su Drive", expanded=False):
        if only_drive:
            st.table(_rows_from(only_drive, drive_entries))
        else:
            st.caption("Nessun elemento solo su Drive.")

    with st.expander("Solo su locale", expanded=False):
        if only_local:
            st.table(_rows_from(only_local, local_entries))
        else:
            st.caption("Nessun elemento solo locale.")

    with st.expander("Differenze dimensione/mtime", expanded=True):
        if differences:
            st.table(differences)
        else:
            st.caption("Nessuna differenza rilevata.")
