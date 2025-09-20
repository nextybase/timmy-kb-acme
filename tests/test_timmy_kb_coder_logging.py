from __future__ import annotations

import importlib
from pathlib import Path


def _drop_kb_handlers(logger) -> None:
    for h in list(getattr(logger, "handlers", [])):
        if getattr(h, "_kb_handler", False):
            logger.removeHandler(h)


def test_import_has_no_logging_side_effects(tmp_path, monkeypatch):
    # Isola CWD per far puntare LOGS_DIR a tmp_path/logs
    monkeypatch.chdir(tmp_path)
    import timmy_kb_coder as tkc

    # Import non deve creare logs/ o file di log
    assert not tkc.LOGS_DIR.exists()
    assert not (tkc.LOGS_DIR / "timmy_kb.log").exists()
    # Nessun handler marcato attaccato al logger
    assert not any(getattr(h, "_kb_handler", False) for h in tkc.LOGGER.handlers)


def test_configure_logging_creates_logs_and_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    import timmy_kb_coder as tkc

    importlib.reload(tkc)
    # Reindirizza logs in una cartella sotto tmp
    monkeypatch.setattr(tkc, "LOGS_DIR", tmp_path / "logs_test", raising=False)
    _drop_kb_handlers(tkc.LOGGER)

    # Prima configurazione
    tkc._configure_logging()
    assert tkc.LOGS_DIR.exists()
    assert (tkc.LOGS_DIR / "timmy_kb.log").exists()
    count1 = sum(1 for h in tkc.LOGGER.handlers if getattr(h, "_kb_handler", False))
    assert count1 >= 2  # file + stream

    # Seconda configurazione (idempotente)
    tkc._configure_logging()
    count2 = sum(1 for h in tkc.LOGGER.handlers if getattr(h, "_kb_handler", False))
    assert count2 == count1


def test_ensure_startup_does_not_create_logs(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    import timmy_kb_coder as tkc

    importlib.reload(tkc)
    # Evita scritture DB reali
    monkeypatch.setattr(tkc, "get_db_path", lambda: tmp_path / "db.sqlite", raising=False)
    monkeypatch.setattr(tkc, "init_db", lambda _p: None, raising=False)

    tkc._ensure_startup()

    # Verifica che le cartelle funzionali esistano
    assert Path("data").exists()
    assert Path(".timmykb").exists()
    assert Path(".timmykb/history").exists()
    # Nessuna creazione di logs/ implicita
    assert not tkc.LOGS_DIR.exists()
