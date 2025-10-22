# SPDX-License-Identifier: GPL-3.0-or-later

from ui.utils import status as status_mod
from ui.utils.status import status_guard


def test_status_guard_no_streamlit_status(monkeypatch) -> None:
    class DummySt:
        pass

    monkeypatch.setattr(status_mod, "st", DummySt(), raising=False)

    with status_guard("Verifica fallback", expanded=True) as status:
        assert hasattr(status, "update")
        # Lo stub deve accettare update senza lanciare
        status.update(label="ok", state="complete")
