# SPDX-License-Identifier: GPL-3.0-or-later
# src/ui/pages/registry.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

from ui.utils.stubs import get_streamlit


# ---- Costanti file-path (SSoT) ----
class PagePaths:
    HOME = "src/ui/pages/home.py"
    NEW_CLIENT = "src/ui/pages/new_client.py"
    MANAGE = "src/ui/pages/manage.py"
    SEMANTICS = "src/ui/pages/semantics.py"
    PREVIEW = "src/ui/pages/preview.py"

    SETTINGS = "src/ui/pages/settings.py"
    CONFIG_EDITOR = "src/ui/pages/config_editor.py"
    CLEANUP = "src/ui/pages/cleanup.py"
    GUIDA = "src/ui/pages/guida_ui.py"

    ADMIN = "src/ui/pages/admin.py"
    TUNING = "src/ui/pages/tools_check.py"
    SECRETS = "src/ui/pages/secrets_healthcheck.py"
    DIAGNOSTICS = "src/ui/pages/diagnostics.py"


# url_path per fallback < switch_page / query_param >
_URL_BY_PATH: Dict[str, str] = {
    PagePaths.HOME: "home",
    PagePaths.NEW_CLIENT: "new",
    PagePaths.MANAGE: "manage",
    PagePaths.SEMANTICS: "semantics",
    PagePaths.PREVIEW: "preview",
    PagePaths.SETTINGS: "settings",
    PagePaths.CONFIG_EDITOR: "config",
    PagePaths.CLEANUP: "cleanup",
    PagePaths.GUIDA: "guida",
    PagePaths.ADMIN: "admin",
    PagePaths.TUNING: "check",
    PagePaths.SECRETS: "secrets",
    PagePaths.DIAGNOSTICS: "diagnostics",
}


def url_path_for(page_path: str) -> str | None:
    return _URL_BY_PATH.get(page_path)


@dataclass(frozen=True)
class PageGroup:
    label: str
    pages: List[Any]  # st.Page


def build_pages() -> Dict[str, List[Any]]:
    """
    Restituisce il dict {gruppo: [st.Page(...), ...]} per st.navigation(...).
    """
    st = get_streamlit()

    def P(path: str, *, title: str, url_path: str | None = None) -> Any:
        up = url_path or url_path_for(path)
        kwargs = {"title": title}
        if up:
            kwargs["url_path"] = up
        return st.Page(path, **kwargs)

    return {
        "Onboarding": [
            P(PagePaths.HOME, title="Home"),
            P(PagePaths.NEW_CLIENT, title="Nuovo cliente"),
            P(PagePaths.MANAGE, title="Gestisci cliente"),
            P(PagePaths.SEMANTICS, title="Semantica"),
            P(PagePaths.PREVIEW, title="Docker Preview"),
        ],
        "Tools": [
            P(PagePaths.SETTINGS, title="Settings"),
            P(PagePaths.CONFIG_EDITOR, title="Config Editor"),
            P(PagePaths.CLEANUP, title="Cleanup"),
            P(PagePaths.GUIDA, title="Guida UI"),
        ],
        "Admin": [
            P(PagePaths.ADMIN, title="Admin"),
            P(PagePaths.TUNING, title="Tuning"),
            P(PagePaths.SECRETS, title="Secrets Healthcheck"),
            P(PagePaths.DIAGNOSTICS, title="Diagnostica"),
        ],
    }
