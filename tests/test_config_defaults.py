# SPDX-License-Identifier: GPL-3.0-only
from __future__ import annotations

from timmy_kb.cli.tag_onboarding_raw import _normalize_provider


class _NoopLogger:
    def error(self, *a, **k):
        pass


def test_ingest_provider_defaults_to_drive_when_no_override():
    assert _normalize_provider({}, "drive", slug=None, logger=_NoopLogger()) == "drive"
