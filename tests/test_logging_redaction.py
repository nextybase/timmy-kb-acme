# SPDX-License-Identifier: GPL-3.0-or-later
# tests/test_logging_redaction.py
from __future__ import annotations

import logging
from io import StringIO
from types import SimpleNamespace

import pytest

from pipeline.logging_utils import get_structured_logger, redact_secrets
from tests.conftest import DUMMY_SLUG


def test_redact_secrets_masks_bearer_and_basic():
    # Placeholder innocui ma che matchano le regex
    fixture = "Authorization: Bearer demo\n" "authorization: basic abc\n" "Note: nessun altro contenuto qui"
    out = redact_secrets(fixture)
    out_lower = out.lower()

    # Verifica case-insensitive
    assert "authorization: bearer ***" in out_lower
    assert "authorization: basic ***" in out_lower
    # I placeholder non devono restare
    assert "demo" not in out
    assert "abc" not in out


def test_logger_applies_redaction_to_message_and_known_extra():
    buf = StringIO()
    handler = logging.StreamHandler(buf)
    # Formatter con sole chiavi note al redactor per i campi extra
    handler.setFormatter(
        logging.Formatter("%(message)s | Authorization=%(Authorization)s GIT_HTTP_EXTRAHEADER=%(GIT_HTTP_EXTRAHEADER)s")
    )

    ctx = SimpleNamespace(redact_logs=True, slug=DUMMY_SLUG)
    lg = get_structured_logger("tests.redaction", context=ctx, level=logging.INFO)

    # Isoliamo gli handler per il test
    lg.handlers.clear()
    lg.addHandler(handler)

    # Messaggio con pattern noti + extra su chiavi supportate
    msg = "Authorization: Bearer demo"
    lg.info(msg, extra={"Authorization": "any-value", "GIT_HTTP_EXTRAHEADER": "some-header"})

    text = buf.getvalue()
    # Messaggio redatto
    assert "Bearer ***" in text
    # Extra redatti (chiavi sensibili note)
    assert "Authorization=***" in text
    assert "GIT_HTTP_EXTRAHEADER=***" in text
    # Nessuna traccia dei placeholder
    assert "any-value" not in text
    assert "some-header" not in text


@pytest.mark.parametrize("enabled", [True, False])
def test_logger_safe_when_no_known_extras(enabled: bool):
    buf = StringIO()
    handler = logging.StreamHandler(buf)
    handler.setFormatter(logging.Formatter("%(message)s"))

    ctx = SimpleNamespace(redact_logs=enabled, slug=DUMMY_SLUG)
    lg = get_structured_logger("tests.redaction.noextra", context=ctx, level=logging.INFO)

    lg.handlers.clear()
    lg.addHandler(handler)

    lg.info("Authorization: Basic abc")  # verrà redatto solo se enabled=True
    text = buf.getvalue()
    out_lower = text.lower()

    if enabled:
        assert "authorization: basic ***" in out_lower
        assert "abc" not in text
    else:
        assert "authorization: basic ***" not in out_lower
        assert "abc" in text
