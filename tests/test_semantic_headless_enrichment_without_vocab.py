from types import SimpleNamespace

import src.semantic.api as sapi
import src.semantic_headless as sh


def test_headless_enriches_titles_even_when_vocab_empty(tmp_path, monkeypatch):
    base = tmp_path / "output" / "timmy-kb-x"
    book = base / "book"
    raw = base / "raw"
    for d in (book, raw):
        d.mkdir(parents=True, exist_ok=True)

    # Crea un markdown di contenuto senza frontmatter
    md = book / "my_first_doc.md"
    md.write_text("Body only\n", encoding="utf-8")

    # Context minimale compatibile
    ctx = SimpleNamespace(base_dir=base, raw_dir=raw, md_dir=book)

    # Evita conversione reale: ritorna il file già presente
    monkeypatch.setattr(sapi, "convert_markdown", lambda *a, **k: [md.relative_to(book)])
    # Forza vocab vuoto
    monkeypatch.setattr(sapi, "load_reviewed_vocab", lambda *a, **k: {})

    # Generatori SUMMARY/README no-op minimi
    monkeypatch.setattr(
        sapi, "_gen_summary", lambda shim: (shim.md_dir / "SUMMARY.md").write_text("* [x](x.md)", "utf-8")
    )
    monkeypatch.setattr(sapi, "_gen_readme", lambda shim: (shim.md_dir / "README.md").write_text("# Book", "utf-8"))
    monkeypatch.setattr(sapi, "_validate_md", lambda shim: None)

    # Esegue headless
    out = sh.build_markdown_headless(ctx, sapi.logging.getLogger("test.headless"), slug="x")
    assert md in [book / p.name for p in out["converted"]]  # type: ignore[index]

    # Il frontmatter deve avere un titolo derivato dal nome file
    text = md.read_text(encoding="utf-8")
    assert "title:" in text or text.startswith("---\n")
