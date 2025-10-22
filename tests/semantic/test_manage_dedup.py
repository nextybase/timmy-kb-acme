# tests/ui/test_manage_dedup.py
import types
from pathlib import Path

from src.ui.pages import manage


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
    manage.pdf_count = 0  # o stub del calcolo
    manage.service_ok = True  # idem
    manage.semantic_dir = Path(".")  # senza tags.db
    # invoca il blocco che costruisce i messaggi
    # (adatta la chiamata secondo l'organizzazione della pagina)
    manage._render_status_block()  # se non esiste, chiama main() entro un contesto stub
    assert calls["caption"] == 1
    assert calls["warning"] == 1
