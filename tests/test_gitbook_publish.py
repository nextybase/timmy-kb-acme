# SPDX-License-Identifier: GPL-3.0-only
import io
import zipfile
from pathlib import Path

from pipeline import gitbook_publish


class DummyResponse:
    def __init__(self, ok: bool = True, status_code: int = 200):
        self.ok = ok
        self.status_code = status_code


def test_publish_book_to_gitbook_sends_zip(tmp_path: Path, monkeypatch):
    book_dir = tmp_path / "book"
    book_dir.mkdir()
    doc = book_dir / "README.md"
    doc.write_text("# Title\n", encoding="utf-8")
    summary = book_dir / "layout_summary.md"
    summary.write_text("- **strategy**\n", encoding="utf-8")

    captured: dict[str, object] = {}

    def fake_post(url, headers, data, files, timeout):
        captured["url"] = url
        captured["headers"] = headers
        captured["metadata"] = data
        captured["file"] = files["file"]
        captured["file_content"] = files["file"][1].read()
        return DummyResponse()

    monkeypatch.setattr("pipeline.gitbook_publish.requests.post", fake_post)

    gitbook_publish.publish_book_to_gitbook(book_dir, space_id="space", token="gitbook-pat", slug="dummy")  # noqa: S106

    assert captured["url"].endswith("/spaces/space/content")
    assert captured["headers"]["Authorization"] == "Bearer gitbook-pat"
    assert captured["metadata"]["layout_summary"]
    assert captured["file"][0] == "book.zip"

    with zipfile.ZipFile(io.BytesIO(captured["file_content"])) as zf:
        assert "README.md" in zf.namelist()


def test_publish_book_to_gitbook_skips_missing_token(tmp_path: Path, caplog):
    book_dir = tmp_path / "book"
    book_dir.mkdir()
    caplog.set_level("INFO")

    gitbook_publish.publish_book_to_gitbook(book_dir, space_id="space", token="", slug="dummy")

    assert "GitBook publish saltato" in caplog.text
