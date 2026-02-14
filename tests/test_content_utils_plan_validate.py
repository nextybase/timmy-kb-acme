# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from pathlib import Path

import pipeline.content_utils as cu


def test_plan_and_validate_pdf_groups_collects_blocked_deterministically(monkeypatch) -> None:
    raw_root = Path("/raw")
    cat_a = raw_root / "a"
    cat_b = raw_root / "b"
    root_pdf = raw_root / "root.pdf"
    cat_items = [
        (cat_a, [cat_a / "ok-1.pdf", cat_a / "bad-1.pdf"]),
        (cat_b, [cat_b / "bad-2.pdf", cat_b / "ok-2.pdf"]),
    ]

    monkeypatch.setattr(cu, "_plan_pdf_groups", lambda **_k: ([root_pdf], cat_items), raising=True)

    calls: list[str] = []

    def _fake_filter(
        perimeter_root: Path,
        raw_root_arg: Path,
        pdfs: list[Path],
        *,
        slug: str | None = None,
        logger=None,
        blocked=None,
    ) -> list[Path]:
        _ = (perimeter_root, raw_root_arg, slug, logger)
        calls.append(pdfs[0].parent.name)
        safe: list[Path] = []
        for pdf in pdfs:
            if "bad" in pdf.name:
                if blocked is not None:
                    blocked.append({"file_path": str(pdf), "reason": "path_traversal"})
                continue
            safe.append(pdf)
        return safe

    monkeypatch.setattr(cu, "_filter_safe_pdfs", _fake_filter, raising=True)

    root, validated, blocked = cu._plan_and_validate_pdf_groups(
        perimeter_root=raw_root,
        raw_root=raw_root,
        safe_pdfs=None,
        slug="dummy",
        logger=cu.get_structured_logger("test.content_utils"),
    )

    assert root == [root_pdf]
    assert calls == ["a", "b"]
    assert validated == [(cat_a, [cat_a / "ok-1.pdf"]), (cat_b, [cat_b / "ok-2.pdf"])]
    assert blocked == [
        {"file_path": str(cat_a / "bad-1.pdf"), "reason": "path_traversal"},
        {"file_path": str(cat_b / "bad-2.pdf"), "reason": "path_traversal"},
    ]


def test_plan_and_validate_pdf_groups_skips_refilter_when_safe_pdfs_given(monkeypatch, tmp_path: Path) -> None:
    raw_root = tmp_path / "raw"
    cat = raw_root / "cat"
    safe = [raw_root / "root.pdf", cat / "ok.pdf"]

    def _must_not_run(*_a, **_k):
        raise AssertionError("unexpected refilter")

    monkeypatch.setattr(cu, "_filter_safe_pdfs", _must_not_run, raising=True)

    root, validated, blocked = cu._plan_and_validate_pdf_groups(
        perimeter_root=raw_root,
        raw_root=raw_root,
        safe_pdfs=safe,
        slug="dummy",
        logger=cu.get_structured_logger("test.content_utils"),
    )

    assert blocked == []
    assert root == [raw_root / "root.pdf"]
    assert validated == [(cat, [cat / "ok.pdf"])]
