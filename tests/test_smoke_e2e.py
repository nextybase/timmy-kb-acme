from pathlib import Path

import pytest


def _make_pdf(path: Path, *, text: str, pages: int = 1, heavy: bool = False) -> None:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    c = canvas.Canvas(str(path), pagesize=A4)
    width, height = A4
    for _ in range(pages):
        c.setFont("Helvetica", 12)
        c.drawString(72, height - 72, text)
        if heavy:
            # disegna molte forme per simulare carico grafico
            c.setFillGray(0.9)
            for i in range(0, 40):
                x = 20 + (i % 10) * 50
                y = 100 + (i // 10) * 50
                c.rect(x, y, 40, 40, fill=1, stroke=0)
        c.showPage()
    c.save()


@pytest.mark.slow
def test_smoke_e2e_bad_pdfs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    # Workspace isolato nell'area temporanea
    slug = "dummy"
    workspace = tmp_path / f"timmy-kb-{slug}"
    raw = workspace / "raw"
    book = workspace / "book"
    semantic = workspace / "semantic"
    for d in (raw, book, semantic):
        d.mkdir(parents=True, exist_ok=True)

    # Forza la root repo al workspace temporaneo
    monkeypatch.setenv("REPO_ROOT_DIR", str(workspace))

    # Genera PDF 'cattivi'
    long_name = ("very_long_name_" * 8)[:150] + ".pdf"
    weird_name = "nome con caratteri strani – è ß Ω 😊 [v1].pdf"
    ctrl_text = "Test RTL ‎‏‎‏‎ (RLO/LRM) + combining é̄̀̈ + symbols §¶"

    # La pipeline si aspetta PDF dentro sottocartelle di categoria: usa 'misc/'
    cat = raw / "misc"
    cat.mkdir(parents=True, exist_ok=True)
    _make_pdf(cat / long_name, text="Documento con nome lunghissimo")
    _make_pdf(cat / weird_name, text="File con caratteri strani (emoji, accenti)")
    _make_pdf(cat / "malformato_control_chars.pdf", text=ctrl_text)
    _make_pdf(cat / "grafica_pesante.pdf", text="Molte forme", pages=3, heavy=True)

    # Import tardivi per evitare costi se marker esclusi
    from pipeline.context import ClientContext
    from pipeline.logging_utils import get_structured_logger
    from semantic.api import convert_markdown, enrich_frontmatter, load_reviewed_vocab, write_summary_and_readme

    ctx = ClientContext.load(slug=slug, require_env=False)
    logger = get_structured_logger("smoke.bad", context=ctx, run_id="test-run")

    from storage.tags_store import save_tags_reviewed

    tags_db_path = Path(ctx.base_dir) / "semantic" / "tags.db"
    save_tags_reviewed(
        str(tags_db_path),
        {
            "tags": [
                {
                    "name": "energia rinnovabile",
                    "action": "keep",
                    "synonyms": ["energia green"],
                }
            ]
        },
    )
    assert tags_db_path.exists()

    # 1) Conversione PDF -> Markdown
    mds = convert_markdown(ctx, logger, slug=slug)
    assert isinstance(mds, list)
    assert len(mds) >= 1

    # 2) Arricchimento frontmatter (vocabolario potrebbe essere vuoto -> no-op)
    base = Path(ctx.base_dir)
    vocab = load_reviewed_vocab(base, logger)
    touched = enrich_frontmatter(ctx, logger, vocab, slug=slug)
    assert isinstance(touched, list)

    # 3) README/SUMMARY
    write_summary_and_readme(ctx, logger, slug=slug)

    # Verifiche finali minime
    assert any(p.name.lower() == "readme.md" for p in (book.glob("*.md")))
    assert (book / "SUMMARY.md").exists()

    # TODO: se emergono debolezze di parsing per nomi/RTL/emoji, isolarle e aprire issue
