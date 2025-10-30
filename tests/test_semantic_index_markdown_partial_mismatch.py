# tests/test_semantic_index_markdown_partial_mismatch.py
import logging
from types import SimpleNamespace

from timmykb.semantic.api import index_markdown_to_db


class FakeEmbClient:
    def embed_texts(self, texts):
        # genera 1 solo vettore per forzare il mismatch con 2 contenuti
        return [[0.1, 0.2, 0.3]]


def test_index_markdown_partial_on_mismatch_inserts_and_logs(tmp_path, caplog, monkeypatch):
    base = tmp_path
    book = base / "book"
    book.mkdir(parents=True)

    # due file di contenuto (README/SUMMARY non considerati)
    (book / "content_1.md").write_text("# A\ntext", encoding="utf-8")
    (book / "content_2.md").write_text("# B\ntext", encoding="utf-8")

    # context minimo
    ctx = SimpleNamespace(base_dir=base, md_dir=book)
    logger = logging.getLogger("test.index_mismatch")
    caplog.set_level(logging.INFO)

    # stub del DB per evitare IO reale
    monkeypatch.setattr("src.semantic.api._init_kb_db", lambda db_path=None: None)
    monkeypatch.setattr("src.semantic.api._get_db_path", lambda: base / "kb.sqlite")

    calls = {"count": 0}

    def fake_insert_chunks(**kwargs):
        calls["count"] += 1
        return 1

    monkeypatch.setattr("src.semantic.api._insert_chunks", lambda **kw: fake_insert_chunks(**kw))

    inserted = index_markdown_to_db(
        ctx,
        logger,
        slug="dummy",
        scope="book",
        embeddings_client=FakeEmbClient(),
        db_path=base / "kb.sqlite",
    )

    # deve inserire min(len(contents), len(vecs)) == 1
    assert inserted == 1
    # logging strutturato atteso
    messages = [r.getMessage() for r in caplog.records]
    assert any("semantic.index.mismatched_embeddings" in m for m in messages)
    assert any("semantic.index.embedding_pruned" in m for m in messages)

    pruned_records = [r for r in caplog.records if r.getMessage() == "semantic.index.embedding_pruned"]
    assert pruned_records
    pruned = pruned_records[-1]
    assert getattr(pruned, "cause", None) == "mismatch"
    assert getattr(pruned, "dropped", None) == 1
    assert getattr(pruned, "kept", None) == 1
    assert any("semantic.index.skips" in m for m in messages)
