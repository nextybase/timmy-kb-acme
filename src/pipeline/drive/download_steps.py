# SPDX-License-Identifier: GPL-3.0-or-later
# src/pipeline/drive/download_steps.py
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, Optional, Sequence

from pipeline.exceptions import PipelineError
from pipeline.logging_utils import get_structured_logger
from pipeline.path_utils import sanitize_filename


@dataclass(frozen=True)
class DriveCandidate:
    """Singolo file Drive -> raw locale."""

    category: str
    filename: str
    destination: Path
    remote_id: str
    remote_size: int
    metadata: Dict[str, Any]

    @property
    def label(self) -> str:
        return f"{self.category}/{self.filename}" if self.category else self.filename


ListFoldersFn = Callable[[Any, str], Iterable[Dict[str, Any]]]
ListPdfsFn = Callable[[Any, str], Iterable[Dict[str, Any]]]
EnsureDestFn = Callable[[Path, Path, Sequence[str], str], Path]


def discover_candidates(
    *,
    service: Any,
    raw_folder_id: str,
    list_folders: ListFoldersFn,
    list_pdfs: ListPdfsFn,
    ensure_dest: EnsureDestFn,
    perimeter_root: Path,
    local_root: Path,
    logger: Optional[Any] = None,
) -> list[DriveCandidate]:
    """Restituisce i candidati download (categoria, filename, destinazione, id)."""
    candidates: list[DriveCandidate] = []
    invalid: list[dict[str, Any]] = []
    log = logger if logger is not None else get_structured_logger("pipeline.drive.download_steps")

    def _append(category: str, file_info: Dict[str, Any], rel_parts: Sequence[str]) -> None:
        raw_name = file_info.get("name") or ""
        file_id = file_info.get("id") or ""
        if not raw_name or not file_id:
            invalid.append(
                {
                    "category": category,
                    "has_name": bool(raw_name),
                    "has_id": bool(file_id),
                }
            )
            log.warning(
                "drive.candidate.invalid",
                extra={
                    "category": category,
                    "has_name": bool(raw_name),
                    "has_id": bool(file_id),
                    "reason": "missing_name_or_id",
                },
            )
            return
        name = sanitize_filename(raw_name, strict=True)
        if not name.lower().endswith(".pdf"):
            name = f"{name}.pdf"
        remote_size = int(file_info.get("size") or 0)
        try:
            dest = ensure_dest(perimeter_root, local_root, list(rel_parts), name)
        except Exception as exc:
            invalid.append(
                {
                    "category": category,
                    "file_name": name,
                    "reason": "ensure_dest_failed",
                }
            )
            log.error(
                "drive.candidate.ensure_failed",
                extra={"category": category, "file_name": name, "error": str(exc)},
            )
            return
        candidates.append(
            DriveCandidate(
                category=category,
                filename=name,
                destination=dest,
                remote_id=file_id,
                remote_size=remote_size,
                metadata=file_info,
            )
        )

    # PDF direttamente sotto raw/
    for file_info in list_pdfs(service, raw_folder_id):
        _append("", file_info, [])

    # PDF nelle sottocartelle di raw/
    for folder in list_folders(service, raw_folder_id):
        category = (folder.get("name") or "").strip()
        folder_id = folder.get("id") or ""
        if not category or not folder_id:
            invalid.append(
                {
                    "category": category,
                    "has_name": bool(category),
                    "has_id": bool(folder_id),
                    "reason": "missing_folder_name_or_id",
                }
            )
            log.warning(
                "drive.candidate.folder_invalid",
                extra={
                    "category": category,
                    "has_name": bool(category),
                    "has_id": bool(folder_id),
                    "reason": "missing_folder_name_or_id",
                },
            )
            continue
        for file_info in list_pdfs(service, folder_id):
            _append(category, file_info, [category])

    if invalid:
        raise PipelineError(
            f"Drive candidates invalid: {len(invalid)} elementi scartati.",
            component="drive.download",
        )

    return candidates


def emit_progress(
    candidates: Iterable[DriveCandidate],
    callback: Optional[Callable[[int, int, str], None]],
    *,
    logger: Optional[Any] = None,
) -> None:
    """Invoca callback(done, total, label) per ogni candidato."""
    if not callable(callback):
        return
    cand_list = list(candidates)
    total = len(cand_list)
    log = logger if logger is not None else get_structured_logger("pipeline.drive.download_steps")
    for idx, cand in enumerate(cand_list, start=1):
        try:
            callback(idx, total, cand.label)
        except Exception as exc:
            log.error(
                "drive.progress_callback.failed",
                extra={"index": idx, "total": total, "label": cand.label, "error": str(exc)},
            )
            raise PipelineError(
                "Callback di progresso fallita durante il download Drive.",
                component="drive.download",
            ) from exc


def snapshot_existing(candidates: Iterable[DriveCandidate]) -> set[Path]:
    """Restituisce il set dei path già presenti prima del download."""
    return {cand.destination for cand in candidates if cand.destination.exists()}


def compute_created(
    candidates: Iterable[DriveCandidate],
    before: set[Path],
) -> list[Path]:
    """Ritorna path ordinati dei file creati rispetto allo snapshot iniziale."""
    created = [cand.destination for cand in candidates if cand.destination.exists() and cand.destination not in before]
    return sorted(created)
