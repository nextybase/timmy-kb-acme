# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

import json
import tempfile
import zipfile
from pathlib import Path
from typing import Sequence

import requests

from pipeline.exceptions import GitBookPublishError
from pipeline.layout_summary import read_layout_summary_entries
from pipeline.logging_utils import get_structured_logger
from pipeline.path_utils import ensure_within

logger = get_structured_logger("pipeline.gitbook_publish")


def _zip_directory(source: Path, target: Path) -> None:
    """Crea uno zip atomico del contenuto sotto source."""
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(source.rglob("*")):
            if path.is_file():
                arcname = path.relative_to(source)
                archive.write(path, arcname)


def _prepare_metadata(entries: Sequence[str] | None) -> dict[str, str]:
    payload = {"entries": entries or []}
    return {"layout_summary": json.dumps(payload, ensure_ascii=False)}


def publish_book_to_gitbook(
    book_dir: Path,
    *,
    space_id: str,
    token: str,
    slug: str | None = None,
    layout_entries: Sequence[str] | None = None,
) -> None:
    """Carica `book/` su GitBook (endpoint v1, payload da adattare se necessario)."""
    if not (space_id and token):
        logger.info("GitBook publish saltato: spazio/token mancanti", extra={"slug": slug})
        return

    ensure_within(book_dir, book_dir)

    summary_entries = layout_entries or read_layout_summary_entries(book_dir)
    metadata = _prepare_metadata(summary_entries)
    url = f"https://api.gitbook.com/v1/spaces/{space_id}/content"

    with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
        zip_path = Path(tmp.name)
    try:
        _zip_directory(book_dir, zip_path)
        with zip_path.open("rb") as fh:
            files = {"file": ("book.zip", fh, "application/zip")}
            headers = {
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
            }
            try:
                response = requests.post(url, headers=headers, data=metadata, files=files, timeout=60)
            except requests.RequestException as exc:
                raise GitBookPublishError(
                    "Errore rete durante la pubblicazione GitBook",
                    slug=slug,
                    file_path=str(book_dir),
                ) from exc
        if not response.ok:
            raise GitBookPublishError(
                f"GitBook publish fallito ({response.status_code})",
                slug=slug,
                file_path=str(book_dir),
            )
        logger.info(
            "GitBook publish completato",
            extra={
                "slug": slug,
                "entries": summary_entries,
                "status_code": response.status_code,
            },
        )
    finally:
        try:
            zip_path.unlink(missing_ok=True)
        except FileNotFoundError:
            pass
