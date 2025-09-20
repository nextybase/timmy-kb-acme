from __future__ import annotations

from pathlib import Path

import pytest

from pipeline.exceptions import ConfigError
from pipeline.logging_utils import get_structured_logger
from semantic.vocab_loader import load_reviewed_vocab


def _mk_workspace(tmp_path: Path) -> Path:
    base = tmp_path / "kb"
    (base / "semantic").mkdir(parents=True, exist_ok=True)
    return base


def test_load_vocab_missing_db_raises(tmp_path: Path):
    base = _mk_workspace(tmp_path)
    logger = get_structured_logger("test.vocab.missing")

    with pytest.raises(ConfigError) as exc:
        load_reviewed_vocab(base, logger)
    # Il file_path dell'errore punta al DB atteso
    assert str(getattr(exc.value, "file_path", "")).endswith(str(Path("semantic") / "tags.db"))


def test_load_vocab_empty_db_warns(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]):
    base = _mk_workspace(tmp_path)
    # Crea un file DB vuoto per superare il check di esistenza
    db = base / "semantic" / "tags.db"
    db.write_bytes(b"")

    # Forza il loader dello store a restituire struttura vuota
    import semantic.vocab_loader as vl

    monkeypatch.setattr(vl, "load_tags_reviewed_db", lambda p: {}, raising=True)

    logger = get_structured_logger("test.vocab.empty")
    vocab = load_reviewed_vocab(base, logger)
    assert vocab == {}
    out = capsys.readouterr().out
    assert "senza canonici" in out


def test_load_vocab_valid_info(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]):
    base = _mk_workspace(tmp_path)
    db = base / "semantic" / "tags.db"
    db.write_bytes(b"sqlite placeholder")

    # Simula store con 2 canonici (1 keep e 1 merge_into)
    data = {
        "tags": [
            {"name": "finance", "action": "keep", "synonyms": ["finanza"]},
            {"name": "fatturato", "action": "merge_into:finance", "synonyms": ["revenues"]},
        ]
    }
    import semantic.vocab_loader as vl

    monkeypatch.setattr(vl, "load_tags_reviewed_db", lambda p: data, raising=True)

    logger = get_structured_logger("test.vocab.ok")
    vocab = load_reviewed_vocab(base, logger)
    assert "finance" in vocab and "aliases" in vocab["finance"]
    # Deve esserci un log informativo con il conteggio
    out = capsys.readouterr().out
    assert "Vocabolario reviewed caricato" in out
