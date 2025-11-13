# SPDX-License-Identifier: GPL-3.0-only
# tests/test_vocab_loader_integration_db.py
from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Dict, Sequence

import timmykb.semantic.vocab_loader as vl


class _NoopLogger:
    def debug(self, *a, **k): ...
    def info(self, *a, **k): ...
    def warning(self, *a, **k): ...
    def error(self, *a, **k): ...


def test_loads_canonicals_from_db_when_loader_available(tmp_path: Path, monkeypatch):
    base = tmp_path / "output" / "timmy-kb-dummy"
    sem = base / "semantic"
    sem.mkdir(parents=True, exist_ok=True)

    # Crea un file 'tags.db' per superare la check di esistenza + open
    db = sem / "tags.db"
    db.write_bytes(b"\0")  # contenuto irrilevante per il nostro fake loader

    # Inietta un modulo 'storage.tags_store' con la funzione 'load_tags_reviewed'
    class _TagsStoreModule:
        @staticmethod
        def load_tags_reviewed(db_path: str) -> Dict[str, Dict[str, Sequence[str]]]:  # noqa: ARG001
            # Ignora il contenuto, ma rispetta la firma e ritorna una struttura valida.
            return {"canon": {"aliases": ["alias1", "alias2"]}}

    monkeypatch.setitem(sys.modules, "storage.tags_store", _TagsStoreModule)

    # Ricarica il modulo per agganciare l'import lazy (solo se necessario)
    importlib.reload(vl)

    vocab = vl.load_reviewed_vocab(base, _NoopLogger())
    assert "canon" in vocab
    assert "aliases" in vocab["canon"]
    assert vocab["canon"]["aliases"] == ["alias1", "alias2"]
