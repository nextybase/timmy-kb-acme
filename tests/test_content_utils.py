from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import pytest

from pipeline.content_utils import (
    convert_files_to_structured_markdown,
    generate_summary_markdown,
    generate_readme_markdown,
    validate_markdown_dir,
)
from pipeline.exceptions import PipelineError


# --- Mini contesto compatibile con content_utils (duck typing su ClientContext) ---
@dataclass
class _MiniContext:
    slug: str
    base_dir: Path
    raw_dir: Path
    md_dir: Path


def _mk_ctx(dummy_kb) -> _MiniContext:
    base = dummy_kb["base"]
    raw = dummy_kb["raw"]
    md = dummy_kb["book"]
    return _MiniContext(slug="dummy", base_dir=base, raw_dir=raw, md_dir=md)


def _touch_pdf(p: Path) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"%PDF-1.4\n%Fake\n")  # contenuto fittizio: non viene letto dai test


# -----------------------------
# convert_files_to_structured_markdown
# -----------------------------
def test_convert_creates_md_per_category_and_respects_structure(dummy_kb):
    ctx = _mk_ctx(dummy_kb)

    # Struttura RAW:
    # raw/
    #   contratti/2024/Q4/doc1.pdf
    #   report/doc2.pdf
    #   vuota/               (nessun pdf)
    _touch_pdf(ctx.raw_dir / "contratti" / "2024" / "Q4" / "doc1.pdf")
    _touch_pdf(ctx.raw_dir / "report" / "doc2.pdf")
    (ctx.raw_dir / "vuota").mkdir(parents=True, exist_ok=True)

    convert_files_to_structured_markdown(ctx)

    # Devono esistere i 3 .md sotto book/
    contratti_md = ctx.md_dir / "contratti.md"
    report_md = ctx.md_dir / "report.md"
    vuota_md = ctx.md_dir / "vuota.md"

    assert contratti_md.exists()
    assert report_md.exists()
    assert vuota_md.exists()

    c_txt = contratti_md.read_text(encoding="utf-8")
    # Titolo principale dal nome cartella
    assert "# Contratti" in c_txt
    # Heading annidati da sottocartelle
    assert "## 2024" in c_txt      # depth 1
    assert "### Q4" in c_txt       # depth 2
    # Titolo PDF: depth=2 => livello (2+2)=4 -> ####
    assert "#### Doc1" in c_txt
    assert "(Contenuto estratto/conversione da `doc1.pdf`)" in c_txt

    r_txt = report_md.read_text(encoding="utf-8")
    # Nessuna sottocartella (depth=0) => sezione PDF con "##"
    assert "# Report" in r_txt
    assert "## Doc2" in r_txt
    assert "(Contenuto estratto/conversione da `doc2.pdf`)" in r_txt

    v_txt = vuota_md.read_text(encoding="utf-8")
    assert "_Nessun PDF trovato in questa categoria._" in v_txt


def test_convert_raises_on_unsafe_md_dir(dummy_kb):
    ctx = _mk_ctx(dummy_kb)
    unsafe_md = ctx.base_dir.parent / "outside-book"
    with pytest.raises(PipelineError):
        convert_files_to_structured_markdown(ctx, md_dir=unsafe_md)


# -----------------------------
# generate_summary_markdown & generate_readme_markdown
# -----------------------------
def test_generate_readme_and_summary(dummy_kb):
    ctx = _mk_ctx(dummy_kb)

    # Prepariamo qualche .md nella cartella book/
    (ctx.md_dir).mkdir(parents=True, exist_ok=True)
    (ctx.md_dir / "alpha.md").write_text("# Alpha\n", encoding="utf-8")
    (ctx.md_dir / "beta.md").write_text("# Beta\n", encoding="utf-8")

    # README e SUMMARY
    generate_readme_markdown(ctx)
    generate_summary_markdown(ctx)

    readme = ctx.md_dir / "README.md"
    summary = ctx.md_dir / "SUMMARY.md"
    assert readme.exists() and summary.exists()

    s_txt = summary.read_text(encoding="utf-8")
    # Deve elencare alpha.md e beta.md, ma non README.md né SUMMARY.md
    assert "[alpha](alpha.md)" in s_txt.lower()
    assert "[beta](beta.md)" in s_txt.lower()
    assert "readme.md" not in s_txt.lower()
    assert "summary.md" not in s_txt.lower()


def test_generate_summary_unsafe_dir_raises(dummy_kb):
    ctx = _mk_ctx(dummy_kb)
    unsafe_md = ctx.base_dir.parent / "outside-book"
    with pytest.raises(PipelineError):
        generate_summary_markdown(ctx, md_dir=unsafe_md)


def test_generate_readme_unsafe_dir_raises(dummy_kb):
    ctx = _mk_ctx(dummy_kb)
    unsafe_md = ctx.base_dir.parent / "outside-book"
    with pytest.raises(PipelineError):
        generate_readme_markdown(ctx, md_dir=unsafe_md)


# -----------------------------
# validate_markdown_dir
# -----------------------------
def test_validate_markdown_dir_happy_path(dummy_kb):
    ctx = _mk_ctx(dummy_kb)
    ctx.md_dir.mkdir(parents=True, exist_ok=True)
    # Non solleva nulla
    validate_markdown_dir(ctx)


def test_validate_markdown_dir_nonexistent_raises(dummy_kb):
    ctx = _mk_ctx(dummy_kb)
    if ctx.md_dir.exists():
        # pulizia difensiva
        for p in ctx.md_dir.glob("*"):
            p.unlink()
        ctx.md_dir.rmdir()
    with pytest.raises(PipelineError):
        validate_markdown_dir(ctx)


def test_validate_markdown_dir_not_a_directory_raises(dummy_kb):
    ctx = _mk_ctx(dummy_kb)
    ctx.md_dir.parent.mkdir(parents=True, exist_ok=True)
    # Creiamo un file con lo stesso nome
    ctx.md_dir.write_text("not a dir", encoding="utf-8")
    try:
        with pytest.raises(PipelineError):
            validate_markdown_dir(ctx)
    finally:
        # cleanup per non interferire con altri test
        ctx.md_dir.unlink()


def test_validate_markdown_dir_unsafe_dir_raises(dummy_kb):
    ctx = _mk_ctx(dummy_kb)
    unsafe_md = ctx.base_dir.parent / "outside-book"
    with pytest.raises(PipelineError):
        validate_markdown_dir(ctx, md_dir=unsafe_md)
