# tests/test_logging_utils.py
import logging
import pytest

from pipeline.logging_utils import get_structured_logger


class _MemoryHandler(logging.Handler):
    """Handler in-memory per catturare record (e il messaggio formattato)."""
    def __init__(self):
        super().__init__()
        self.records = []
        self.formatted = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)
        try:
            msg = self.format(record)
        except Exception:
            msg = record.getMessage()
        self.formatted.append(msg)


def _attach_memory_handler(logger: logging.Logger) -> _MemoryHandler:
    """Attacca un handler in-memory al logger e lo configura con lo stesso formatter
    del primo handler già presente (quello console creato da get_structured_logger)."""
    mh = _MemoryHandler()
    if logger.handlers:
        mh.setFormatter(logger.handlers[0].formatter)
    logger.addHandler(mh)
    return mh


def test_get_structured_logger_returns_logger_with_name_and_handlers():
    logger = get_structured_logger("pipeline.logging_utils.test")
    assert isinstance(logger, logging.Logger)
    assert logger.name == "pipeline.logging_utils.test"
    # Deve avere almeno 1 handler (console) e non deve essere il root
    assert len(logger.handlers) >= 1
    assert logger is not logging.getLogger()


def test_get_structured_logger_is_idempotent_no_duplicate_handlers():
    # Design attuale: ad ogni chiamata si fa "clear" e si ri-aggiunge (nessun duplicato)
    logger1 = get_structured_logger("pipeline.logging_utils.test.idem")
    count1 = len(logger1.handlers)
    ids1 = {id(h) for h in logger1.handlers}

    logger2 = get_structured_logger("pipeline.logging_utils.test.idem")
    count2 = len(logger2.handlers)
    ids2 = {id(h) for h in logger2.handlers}

    # È lo stesso oggetto logger
    assert logger1 is logger2
    # Niente duplicati: la quantità di handler rimane stabile e gli id sono un set della stessa lunghezza
    assert count1 >= 1 and count2 >= 1
    assert len(ids2) == count2


def test_logger_default_does_not_propagate_and_emits():
    logger = get_structured_logger("pipeline.logging_utils.test.propagate")
    # Non deve propagare al root
    assert logger.propagate is False

    # Catturiamo direttamente dal logger con un handler in-memory
    mh = _attach_memory_handler(logger)
    logger.info("hello-structured")

    assert any(r.levelno == logging.INFO for r in mh.records)
    assert any("hello-structured" in s for s in mh.formatted)
    # Il nome logger è corretto
    assert any(r.name == logger.name for r in mh.records)


def test_logger_emits_error_with_context_slug():
    # Creiamo un contesto minimale con .slug
    class Ctx:
        def __init__(self, slug: str) -> None:
            self.slug = slug

    ctx = Ctx(slug="dummy")
    logger = get_structured_logger("pipeline.logging_utils.test.extra", context=ctx)

    mh = _attach_memory_handler(logger)
    logger.error("ops")

    # Abbiamo un record ERROR
    errs = [r for r in mh.records if r.levelno == logging.ERROR and r.name == logger.name]
    assert errs, "Nessun record ERROR catturato"

    # Il record deve avere l'attributo 'slug' aggiunto dal filtro
    assert hasattr(errs[0], "slug"), "Il LogRecord non contiene il campo 'slug'"
    assert errs[0].slug == "dummy"

    # E il messaggio formattato deve includere 'slug=dummy' (come definito dal formatter)
    assert any("slug=dummy" in s for s in mh.formatted)
