# tests/test_logging_redaction.py
from __future__ import annotations

import logging
from io import StringIO
from types import SimpleNamespace

from pipeline.logging_utils import get_structured_logger, redact_secrets


def test_redact_secrets_standalone():
    msg = "Authorization: Bearer SECRET  x-access-token: TOPSECRET  Authorization: Basic Zm9vOmJhcg=="
    out = redact_secrets(msg)
    assert "Authorization: Bearer ***" in out
    assert "Authorization: Basic ***" in out
    assert "x-access-token:***" in out
    assert "SECRET" not in out
    assert "TOPSECRET" not in out
    assert "Zm9vOmJhcg==" not in out


def test_logger_applies_redaction_filter_to_message_and_extra():
    # Handler in-memory per ispezionare il testo formattato
    buf = StringIO()
    handler = logging.StreamHandler(buf)
    handler.setFormatter(
        logging.Formatter("%(message)s | Authorization=%(Authorization)s GITHUB_TOKEN=%(GITHUB_TOKEN)s")
    )

    # Context con redazione attiva
    ctx = SimpleNamespace(redact_logs=True, slug="acme")
    lg = get_structured_logger("tests.redaction", context=ctx, level=logging.INFO)

    # Usiamo solo il nostro handler per evitare rumore da configurazioni globali
    lg.handlers.clear()
    lg.addHandler(handler)

    # Messaggio e campi extra con segreti → devono venire redatti
    lg.info("Authorization: Bearer SECRET", extra={"Authorization": "sekret", "GITHUB_TOKEN": "ghs_123"})
    text = buf.getvalue()

    assert "Bearer ***" in text
    assert "Authorization=***" in text
    assert "GITHUB_TOKEN=***" in text
    assert "SECRET" not in text
    assert "ghs_123" not in text
