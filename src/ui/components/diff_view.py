# SPDX-License-Identifier: GPL-3.0-or-later
# src/ui/components/diff_view.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from pipeline.path_utils import ensure_within_and_resolve, iter_safe_paths, validate_slug

try:
    import streamlit as st
except Exception:  # pragma: no cover
    st = None

OUTPUT_ROOT = Path(__file__).resolve().parents[3] / "output"


@dataclass(frozen=True)
class DiffDataset:
    drive_entries: Dict[str, Dict[str, Any]]
    local_entries: Dict[str, Dict[str, Any]]
    only_drive: List[str]
    only_local: List[str]
    differences: List[Dict[str, Any]]


def _safe_mtime(path: Path) -> Optional[float]:
    try:
        return path.stat().st_mtime
    except OSError:  # pragma: no cover
        return None


def _build_local_index(raw_dir: Path) -> Dict[str, Dict[str, Any]]:
    index: Dict[str, Dict[str, Any]] = {}
    if not raw_dir.exists():
        return index

    # Indichiamo sempre la radice "raw" (come fa l'indice Drive)
    index["raw"] = {"type": "dir", "size": None, "mtime": _safe_mtime(raw_dir)}

    for directory in iter_safe_paths(raw_dir, include_dirs=True, include_files=False):
        rel_dir = directory.relative_to(raw_dir).as_posix()
        if not rel_dir:
            continue
        key = f"raw/{rel_dir}"
        index[key] = {"type": "dir", "size": None, "mtime": _safe_mtime(directory)}

    for file_path in iter_safe_paths(raw_dir, include_dirs=False, include_files=True):
        rel = file_path.relative_to(raw_dir).as_posix()
        if not rel:
            continue
        key = f"raw/{rel}"
        try:
            stat = file_path.stat()
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


# ------------------- LINK E FILTRI -----------------------------------------------


def _drive_web_url(meta: Dict[str, Any]) -> Optional[str]:
    """Restituisce un URL web per aprire file/cartella su Google Drive, se identificabile."""
    if not isinstance(meta, dict):
        return None
    url = meta.get("webViewLink") or meta.get("webViewUrl")
    if isinstance(url, str) and url.startswith("http"):
        return url
    _id = meta.get("id")
    if not _id:
        return None
    typ = (meta.get("type") or "").lower()
    if typ in {"dir", "folder"}:
        return f"https://drive.google.com/drive/folders/{_id}"
    return f"https://drive.google.com/file/d/{_id}/view"


def _mk_md_table(rows: List[Dict[str, str]], headers: List[str]) -> str:
    """Crea una tabella Markdown semplice; i valori possono includere link."""
    if not rows:
        return "_(vuoto)_"
    line_h = "| " + " | ".join(headers) + " |"
    line_s = "| " + " | ".join(["---"] * len(headers)) + " |"
    buf = [line_h, line_s]
    for r in rows:
        buf.append("| " + " | ".join(r.get(h, "") or "" for h in headers) + " |")
    return "\n".join(buf)


def _is_readme_pdf(path: str) -> bool:
    """True se il basename è README.pdf (case-insensitive)."""
    try:
        return Path(path).name.lower() == "readme.pdf"
    except Exception:
        return False


# ------------------- RAGGRUPPAMENTO PER CARTELLA ---------------------------------


def _split_category_and_rel(key: str) -> Tuple[str, str]:
    """
    Restituisce (categoria, relativo) partendo da chiavi "raw/...".
    - "raw/foo/bar.pdf" -> ("foo", "bar.pdf")
    - "raw/foo"         -> ("foo", "")
    - "raw"             -> ("(root)", "")
    - "raw/file.pdf"    -> ("(root)", "file.pdf")
    """
    if key == "raw":
        return "(root)", ""
    rest = key[4:] if key.startswith("raw/") else key
    if not rest:
        return "(root)", ""
    parts = rest.split("/", 1)
    if len(parts) == 1:
        return (parts[0] or "(root)"), ""
    return parts[0], parts[1]


def _group_keys_by_category(keys: Iterable[str]) -> Dict[str, List[Tuple[str, str]]]:
    groups: Dict[str, List[Tuple[str, str]]] = {}
    for key in keys:
        # Escludi README.pdf ovunque compaia
        if _is_readme_pdf(key):
            continue
        category, relative = _split_category_and_rel(key)
        if category == "(root)" and relative == "":
            continue
        groups.setdefault(category, []).append((key, relative))
    return groups


def _rows_from_pairs(
    pairs: List[Tuple[str, str]],
    meta_map: Dict[str, Dict[str, Any]],
) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    for original, relative in pairs:
        meta = meta_map.get(original, {})
        display = relative if relative else "(cartella)"
        rows.append(
            {
                "path": display,
                "type": meta.get("type", "-"),
                "size": _human_size(meta.get("size")),
                "mtime": _format_mtime(meta.get("mtime")),
            }
        )
    return rows


def _group_differences_by_category(rows: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    groups: Dict[str, List[Dict[str, Any]]] = {}
    for row in rows:
        key = str(row.get("path", ""))
        # Escludi README.pdf nelle differenze
        if _is_readme_pdf(key):
            continue
        category, relative = _split_category_and_rel(key)
        if category == "(root)" and relative == "":
            continue
        entry = dict(row)
        entry["path"] = relative if relative else "(cartella)"
        groups.setdefault(category, []).append(entry)
    return groups


# ------------------- RENDER -------------------------------------------------------


def build_diff_dataset(
    slug: str,
    drive_index: Optional[Dict[str, Dict[str, Any]]],
) -> DiffDataset:
    drive_index = drive_index or {}
    drive_entries = {key: meta for key, meta in drive_index.items() if key == "raw" or key.startswith("raw/")}

    safe_slug = str(validate_slug(slug))
    workspace = ensure_within_and_resolve(OUTPUT_ROOT, OUTPUT_ROOT / f"timmy-kb-{safe_slug}")
    raw_dir = ensure_within_and_resolve(workspace, workspace / "raw")
    local_entries = _build_local_index(raw_dir)

    drive_keys = set(drive_entries.keys())
    local_keys = set(local_entries.keys())

    only_drive = sorted(k for k in (drive_keys - local_keys) if not _is_readme_pdf(k))
    only_local = sorted(k for k in (local_keys - drive_keys) if not _is_readme_pdf(k))

    intersections = sorted(drive_keys & local_keys)
    differences: List[Dict[str, Any]] = []
    for key in intersections:
        if _is_readme_pdf(key):
            continue

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

    return DiffDataset(
        drive_entries=drive_entries,
        local_entries=local_entries,
        only_drive=only_drive,
        only_local=only_local,
        differences=differences,
    )


def render_file_actions(dataset: DiffDataset, st_module: Any, *, columns: Optional[tuple[Any, Any]] = None) -> None:
    """Rende le sezioni "Solo su Drive" e "Solo su locale" su due colonne (degradazione: singola)."""
    col_drive, col_local = columns or (st_module, st_module)

    def _expander(target: Any) -> Any:
        expander_fn = getattr(target, "expander", None) or getattr(st_module, "expander", None)
        if not callable(expander_fn):
            raise AttributeError("expander API non disponibile")
        return expander_fn

    with _expander(col_drive)("Solo su Drive", expanded=False):
        if dataset.only_drive:
            grouped_pairs = _group_keys_by_category(dataset.only_drive)
            for category in sorted(grouped_pairs):
                with st_module.expander(f"{category} ({len(grouped_pairs[category])})", expanded=False):
                    md_rows: List[Dict[str, str]] = []
                    for key, rel in grouped_pairs[category]:
                        meta = dataset.drive_entries.get(key, {}) or {}
                        url = _drive_web_url(meta)
                        name = rel if rel else "(cartella)"
                        display = f"[{name}]({url})" if url else name
                        md_rows.append(
                            {
                                "file": display,
                                "size": _human_size(meta.get("size")),
                                "mtime": _format_mtime(meta.get("mtime")),
                            }
                        )
                    st_module.markdown(_mk_md_table(md_rows, headers=["file", "size", "mtime"]))
        else:
            st_module.caption("Nessun elemento solo su Drive.")

    with _expander(col_local)("Solo su locale", expanded=False):
        if dataset.only_local:
            grouped_pairs = _group_keys_by_category(dataset.only_local)
            for category in sorted(grouped_pairs):
                with st_module.expander(f"{category} ({len(grouped_pairs[category])})", expanded=False):
                    st_module.table(_rows_from_pairs(grouped_pairs[category], dataset.local_entries))
        else:
            st_module.caption("Nessun elemento solo locale.")


def render_diff_table(dataset: DiffDataset, st_module: Any, *, column: Optional[Any] = None) -> None:
    """Rende la sezione delle differenze dimensione/mtime con eventuali link Drive."""
    target = column or st_module
    expander_fn = getattr(target, "expander", None) or getattr(st_module, "expander", None)
    if not callable(expander_fn):
        raise AttributeError("expander API non disponibile")
    with expander_fn("Differenze dimensione/mtime", expanded=False):
        if dataset.differences:
            diff_groups = _group_differences_by_category(dataset.differences)
            for category in sorted(diff_groups):
                with st_module.expander(f"{category} ({len(diff_groups[category])})", expanded=False):
                    diff_rows: List[Dict[str, str]] = []
                    for row in diff_groups[category]:
                        rel = row.get("path", "")
                        if category == "(root)":
                            key_full = "raw" if rel == "(cartella)" else f"raw/{rel}"
                        else:
                            key_full = f"raw/{category}" if rel == "(cartella)" else f"raw/{category}/{rel}"
                        meta = (
                            dataset.drive_entries.get(key_full, {}) if isinstance(dataset.drive_entries, dict) else {}
                        )
                        url = _drive_web_url(meta)
                        file_cell = f"[{rel}]({url})" if url and rel and rel != "(cartella)" else (rel or "")
                        diff_rows.append(
                            {
                                "path": file_cell or "(cartella)",
                                "motivo": str(row.get("motivo", "")),
                                "drive_size": str(row.get("drive_size", "")),
                                "local_size": str(row.get("local_size", "")),
                                "drive_mtime": str(row.get("drive_mtime", "")),
                                "local_mtime": str(row.get("local_mtime", "")),
                            }
                        )
                    st_module.markdown(
                        _mk_md_table(
                            diff_rows,
                            headers=["path", "motivo", "drive_size", "local_size", "drive_mtime", "local_mtime"],
                        )
                    )
        else:
            st_module.caption("Nessuna differenza rilevata.")


def render_drive_local_diff(slug: str, drive_index: Optional[Dict[str, Dict[str, Any]]]) -> None:
    if st is None:
        return

    st.subheader("Differenze Drive/Locale")
    dataset = build_diff_dataset(slug, drive_index)

    if not dataset.drive_entries and not dataset.local_entries:
        st.info("Nessun artefatto disponibile: Drive e directory locale risultano vuoti.")
        return

    st.caption(
        "Confronto su dimensione e timestamp (s). Differenze di fuso o sincronizzazione possono produrre scostamenti."
    )
    columns = list(st.columns(3))
    metrics = [
        ("Solo Drive", len(dataset.only_drive)),
        ("Solo locale", len(dataset.only_local)),
        ("Differenze", len(dataset.differences)),
    ]
    for col, (label, value) in zip(columns, metrics, strict=False):
        metric_fn = getattr(col, "metric", None)
        if callable(metric_fn):
            metric_fn(label, value)
        else:  # degradazione minima per gli stub
            st.write(f"{label}: {value}")

    try:
        col_drive, col_local, col_diff = columns
    except Exception:
        col_drive = col_local = col_diff = st

    render_file_actions(dataset, st, columns=(col_drive, col_local))
    render_diff_table(dataset, st, column=col_diff)

    divider_fn = getattr(st, "divider", None)
    if callable(divider_fn):
        divider_fn()
    else:
        st.markdown("---")
