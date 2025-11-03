from __future__ import annotations

import types
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip(
    "googleapiclient.http",
    reason="Client Google Drive non disponibile: installa google-api-python-client",
)

from pipeline.drive import download as drv
from pipeline.drive.download import MIME_PDF, download_drive_pdfs_to_local
from pipeline.drive.download_steps import DriveCandidate
from pipeline.exceptions import PipelineError

pytestmark = pytest.mark.regression_light


class _LoggerStub:
    def __init__(self) -> None:
        self.infos: list[tuple[str, dict[str, Any] | None]] = []
        self.warnings: list[tuple[str, dict[str, Any] | None]] = []
        self.debugs: list[tuple[str, dict[str, Any] | None]] = []

    def info(self, event: str, *, extra: dict[str, Any] | None = None) -> None:
        self.infos.append((event, extra))

    def warning(self, event: str, *, extra: dict[str, Any] | None = None) -> None:
        self.warnings.append((event, extra))

    def debug(self, event: str, *, extra: dict[str, Any] | None = None) -> None:
        self.debugs.append((event, extra))


def test_download_drive_pdfs_to_local_downloads_new_and_skips_existing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ctx = types.SimpleNamespace(base_dir=tmp_path, slug="acme")
    local_root = tmp_path / "raw"

    existing_file = local_root / "Reports" / "existing.pdf"
    existing_file.parent.mkdir(parents=True, exist_ok=True)
    existing_file.write_bytes(b"x" * 42)

    monkeypatch.setattr(drv, "get_structured_logger", lambda *_a, **_k: _LoggerStub())
    new_dest = local_root / "Reports" / "report-finale.pdf"
    candidates = [
        DriveCandidate(
            category="Reports",
            filename="report-finale.pdf",
            destination=new_dest,
            remote_id="pdf-new",
            remote_size=12,
            metadata={"mimeType": MIME_PDF},
        ),
        DriveCandidate(
            category="Reports",
            filename="existing.pdf",
            destination=existing_file,
            remote_id="pdf-same",
            remote_size=42,
            metadata={"mimeType": MIME_PDF},
        ),
    ]

    monkeypatch.setattr(drv, "discover_candidates", lambda **_k: candidates)

    downloaded: list[Path] = []

    def _fake_download(service: Any, file_id: str, dest_path: Path, **_kwargs: Any) -> None:
        downloaded.append(dest_path)
        dest_path.write_bytes(b"pdf-bytes")

    monkeypatch.setattr(drv, "_download_one_pdf_atomic", _fake_download)

    count = download_drive_pdfs_to_local(
        service=object(),
        remote_root_folder_id="root",
        local_root_dir=local_root,
        context=ctx,
    )

    assert count == 1, "Dovrebbe scaricare solo il PDF non presente/localmente diverso."
    assert downloaded, "Nessun download effettuato."
    dest = downloaded[0]
    assert dest.exists()
    assert dest.parent == local_root / "Reports"
    assert dest.name.endswith(".pdf")
    # il file esistente con size uguale non deve essere riscritto
    assert existing_file.read_bytes() == b"x" * 42


def test_download_drive_pdfs_to_local_overwrite_rewrites_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ctx = types.SimpleNamespace(base_dir=tmp_path, slug="acme")
    local_root = tmp_path / "raw"
    existing = local_root / "Reports" / "existing.pdf"
    existing.parent.mkdir(parents=True, exist_ok=True)
    existing.write_bytes(b"old")

    candidates = [
        DriveCandidate(
            category="Reports",
            filename="existing.pdf",
            destination=existing,
            remote_id="pdf-new",
            remote_size=11,
            metadata={"mimeType": MIME_PDF},
        )
    ]

    monkeypatch.setattr(drv, "discover_candidates", lambda **_k: candidates)
    monkeypatch.setattr(drv, "get_structured_logger", lambda *_a, **_k: _LoggerStub())

    downloaded: list[Path] = []

    def _fake_download(service: Any, file_id: str, dest_path: Path, **_kwargs: Any) -> None:
        downloaded.append(dest_path)
        dest_path.write_bytes(b"new-content")

    monkeypatch.setattr(drv, "_download_one_pdf_atomic", _fake_download)

    count = download_drive_pdfs_to_local(
        service=object(),
        remote_root_folder_id="root",
        local_root_dir=local_root,
        context=ctx,
        overwrite=True,
    )

    assert count == 1
    assert downloaded and downloaded[0] == existing
    assert existing.read_bytes() == b"new-content"


def test_download_drive_pdfs_to_local_aggregates_failures(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ctx = types.SimpleNamespace(base_dir=tmp_path, slug="acme")
    local_root = tmp_path / "raw"

    dest = local_root / "broken.pdf"
    candidates = [
        DriveCandidate(
            category="",
            filename="broken.pdf",
            destination=dest,
            remote_id="pdf-fail",
            remote_size=10,
            metadata={"mimeType": MIME_PDF},
        )
    ]
    dest.parent.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(drv, "discover_candidates", lambda **_k: candidates)

    def _fail_download(*_a: Any, **_k: Any) -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr(drv, "_download_one_pdf_atomic", _fail_download)

    logger = _LoggerStub()
    monkeypatch.setattr(drv, "get_structured_logger", lambda *_a, **_k: logger)

    with pytest.raises(PipelineError) as exc:
        download_drive_pdfs_to_local(
            service=object(),
            remote_root_folder_id="root",
            local_root_dir=local_root,
            context=ctx,
            redact_logs=True,
        )

    assert "Download completato con errori" in str(exc.value)
    assert any(event == "download.fail" for event, _extra in logger.warnings), "Manca il warning di failure."
