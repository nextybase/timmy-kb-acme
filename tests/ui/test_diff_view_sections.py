from __future__ import annotations

import importlib
import os
from pathlib import Path
from typing import Any, Dict

import pytest

from tests.ui.streamlit_stub import StreamlitStub


class DiffStreamlitStub(StreamlitStub):
    def __init__(self) -> None:
        super().__init__()
        self.markdown_calls: list[str] = []
        self.caption_calls: list[str] = []
        self.table_calls: list[Any] = []
        self.metric_history: list[tuple[str, int]] = []

    def markdown(self, content: str, **_kwargs: Any) -> None:
        self.markdown_calls.append(content)

    def caption(self, content: str, **_kwargs: Any) -> None:
        self.caption_calls.append(content)

    def table(self, data: Any, **_kwargs: Any) -> None:
        self.table_calls.append(data)

    def columns(self, spec: int | list[int]) -> list[Any]:
        cols = super().columns(spec)

        def _metric(label: str, value: int) -> None:
            self.metric_history.append((label, value))

        for col in cols:
            setattr(col, "metric", _metric)  # type: ignore[attr-defined]
        return cols


def _prepare_workspace(tmp_path: Path) -> Path:
    workspace = tmp_path / "timmy-kb-acme"
    raw_dir = workspace / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    (raw_dir / "foo.txt").write_bytes(b"local-file-updated")
    (raw_dir / "local_only.txt").write_bytes(b"local")
    os.utime(raw_dir / "foo.txt", (1_000, 1_500))
    return raw_dir


def _load_module(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    module = importlib.import_module("ui.components.diff_view")
    monkeypatch.setattr(module, "OUTPUT_ROOT", tmp_path, raising=False)
    return module


@pytest.fixture
def sample_dataset(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    module = _load_module(monkeypatch, tmp_path)
    _prepare_workspace(tmp_path)

    drive_index: Dict[str, Dict[str, Any]] = {
        "raw": {"type": "dir", "size": None, "mtime": 1_000.0},
        "raw/foo.txt": {
            "type": "file",
            "size": 8,
            "mtime": 1_000.0,
            "webViewLink": "https://drive.google.com/file/d/foo/view",
        },
        "raw/drive_only.txt": {
            "type": "file",
            "size": 12,
            "mtime": 1_100.0,
            "webViewLink": "https://drive.google.com/file/d/drive_only/view",
        },
    }

    dataset = module.build_diff_dataset("acme", drive_index)
    return module, dataset


def test_build_diff_dataset_detects_only_and_differences(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    module = _load_module(monkeypatch, tmp_path)
    _prepare_workspace(tmp_path)

    drive_index = {
        "raw": {"type": "dir", "size": None, "mtime": 1_000.0},
        "raw/foo.txt": {"type": "file", "size": 8, "mtime": 1_000.0},
        "raw/drive_only.txt": {"type": "file", "size": 12, "mtime": 1_100.0},
    }

    dataset = module.build_diff_dataset("acme", drive_index)

    assert dataset.only_drive == ["raw/drive_only.txt"]
    assert "raw/local_only.txt" in dataset.only_local
    diff_paths = {row["path"] for row in dataset.differences}
    assert "raw/foo.txt" in diff_paths
    assert dataset.drive_entries["raw/foo.txt"]["size"] == 8


def test_render_file_actions_outputs_tables(sample_dataset) -> None:
    module, dataset = sample_dataset
    stub = DiffStreamlitStub()

    module.render_file_actions(dataset, stub)

    assert any("drive_only" in call for call in stub.markdown_calls)
    assert stub.table_calls, "Expected local table to be rendered"
    assert not stub.caption_calls or "Nessun elemento" not in stub.caption_calls[-1]


def test_render_diff_table_marks_differences(sample_dataset) -> None:
    module, dataset = sample_dataset
    stub = DiffStreamlitStub()

    module.render_diff_table(dataset, stub)

    assert stub.markdown_calls, "Diff table should render markdown"

    no_diff_dataset = module.DiffDataset(
        drive_entries=dataset.drive_entries,
        local_entries=dataset.local_entries,
        only_drive=[],
        only_local=[],
        differences=[],
    )
    stub_empty = DiffStreamlitStub()
    module.render_diff_table(no_diff_dataset, stub_empty)
    assert any("Nessuna differenza" in msg for msg in stub_empty.caption_calls)


def test_render_drive_local_diff_integration(sample_dataset, monkeypatch: pytest.MonkeyPatch) -> None:
    module, dataset = sample_dataset
    stub = DiffStreamlitStub()
    monkeypatch.setattr(module, "st", stub, raising=False)

    module.render_drive_local_diff("acme", dataset.drive_entries)

    assert stub.metric_history[:3] == [
        ("Solo Drive", len(dataset.only_drive)),
        ("Solo locale", len(dataset.only_local)),
        ("Differenze", len(dataset.differences)),
    ]
    assert any("Confronto su dimensione" in msg for msg in stub.caption_calls)
    assert stub.markdown_calls, "Diff markdown not rendered"
    assert stub.table_calls, "Local table not rendered"
