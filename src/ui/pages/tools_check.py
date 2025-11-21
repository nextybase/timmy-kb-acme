# SPDX-License-Identifier: GPL-3.0-or-later
# src/ui/pages/tools_check.py

from __future__ import annotations

from typing import Optional

from ui.chrome import render_chrome_then_require
from ui.fine_tuning import render_advanced_options, render_controls
from ui.fine_tuning.vision_modal import _is_gate_error
from ui.utils.stubs import get_streamlit

st = get_streamlit()


def main() -> None:
    render_chrome_then_require(
        allow_without_slug=True,
        title="Tools > Tuning",
        subtitle="Interfaccia rapida per modali Vision/System Prompt e conversione PDF -> YAML.",
    )
    slug: Optional[str] = st.session_state.get("active_slug") or "dummy"

    render_controls(slug=slug or "dummy", st_module=st)
    render_advanced_options(st_module=st)


if __name__ == "__main__":
    main()


__all__ = ["main", "_is_gate_error"]
