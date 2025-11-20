# SPDX-License-Identifier: GPL-3.0-only
from ui.utils.stubs import get_streamlit

_st = get_streamlit()
_INJECTED = False


def inject_theme_css() -> None:
    global _INJECTED
    if _INJECTED:
        return

    _st.html(
        """
<style>
/* Override robusto del layout principale */
[data-testid="stAppViewContainer"] .block-container {
    width: 100%;
    padding: 3rem 1rem 8rem;
    max-width: initial;
    min-width: auto;
}
</style>
"""
    )
    _INJECTED = True
