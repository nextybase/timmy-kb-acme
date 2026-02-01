# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import json
import uuid

from pipeline.workspace_bootstrap import bootstrap_dummy_workspace
from storage import decision_ledger


def test_event_ledger_insert_roundtrip() -> None:
    layout = bootstrap_dummy_workspace("dummy")
    conn = decision_ledger.open_ledger(layout)

    event_id = uuid.uuid4().hex
    decision_ledger.record_event(
        conn,
        event_id=event_id,
        run_id=None,
        slug=layout.slug,
        event_name="test.event",
        actor="pytest",
        occurred_at="2026-01-30T00:00:00+00:00",
        payload={"a": 1, "b": 2},
    )

    row = conn.execute(
        "SELECT event_name, actor, payload_json FROM events WHERE event_id = ?",
        (event_id,),
    ).fetchone()
    assert row is not None
    assert row[0] == "test.event"
    assert row[1] == "pytest"
    assert json.loads(row[2]) == {"a": 1, "b": 2}
