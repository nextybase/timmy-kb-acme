# SPDX-License-Identifier: GPL-3.0-only
# tests/ui/test_manage_dedup.py
import types
from pathlib import Path

from ui.pages import manage


def test_manage_shows_single_caption(monkeypatch):
    # stub streamlit
    calls = {"caption": 0, "warning": 0}
    st = types.SimpleNamespace(
        caption=lambda *a, **k: calls.__setitem__("caption", calls["caption"] + 1),
        warning=lambda *a, **k: calls.__setitem__("warning", calls["warning"] + 1),
        info=lambda *a, **k: None,
        success=lambda *a, **k: None,
    )
    monkeypatch.setattr(manage, "st", st, raising=True)
    # setup dir & flags
    semantic_dir = Path(".")  # senza tags.db
    manage._render_status_block(pdf_count=0, service_ok=True, semantic_dir=semantic_dir)
    # Status block disabilitato: nessuna caption/warning deve essere mostrata
    assert calls["caption"] == 0
    assert calls["warning"] == 0
