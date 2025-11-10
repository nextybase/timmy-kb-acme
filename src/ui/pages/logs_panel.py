# SPDX-License-Identifier: GPL-3.0-or-later
# src/ui/pages/logs_panel.py
from __future__ import annotations

from ui.utils.route_state import clear_tab, get_slug_from_qp, get_tab, set_tab  # noqa: F401
from ui.utils.stubs import get_streamlit

st = get_streamlit()

from ui.chrome import header, sidebar


def main() -> None:
    """Placeholder Page for Log dashboard."""
    header(None)
    sidebar(None)

    st.subheader("Log dashboard")
    st.info("Questa pagina e' in costruzione. " "Il pannello dei log verra' aggiunto nelle prossime release.")
    st.write("Slug attivo non richiesto: le pagine Admin operano a livello globale.")


if __name__ == "__main__":
    main()
