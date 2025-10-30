# SPDX-License-Identifier: GPL-3.0-or-later
# src/ui/pages/registry.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Sequence

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


@dataclass(frozen=True)
class PageSpec:
    path: str
    title: str
    url_path: str | None


_PAGE_GROUPS: Dict[str, Sequence[PageSpec]] = {
    "Onboarding": (
        PageSpec(PagePaths.HOME, "Home", url_path_for(PagePaths.HOME)),
        PageSpec(PagePaths.NEW_CLIENT, "Nuovo cliente", url_path_for(PagePaths.NEW_CLIENT)),
        PageSpec(PagePaths.MANAGE, "Gestisci cliente", url_path_for(PagePaths.MANAGE)),
        PageSpec(PagePaths.SEMANTICS, "Semantica", url_path_for(PagePaths.SEMANTICS)),
        PageSpec(PagePaths.PREVIEW, "Docker Preview", url_path_for(PagePaths.PREVIEW)),
    ),
    "Tools": (
        PageSpec(PagePaths.SETTINGS, "Settings", url_path_for(PagePaths.SETTINGS)),
        PageSpec(PagePaths.CONFIG_EDITOR, "Config Editor", url_path_for(PagePaths.CONFIG_EDITOR)),
        PageSpec(PagePaths.CLEANUP, "Cleanup", url_path_for(PagePaths.CLEANUP)),
        PageSpec(PagePaths.GUIDA, "Guida UI", url_path_for(PagePaths.GUIDA)),
    ),
    "Admin": (
        PageSpec(PagePaths.ADMIN, "Admin", url_path_for(PagePaths.ADMIN)),
        PageSpec(PagePaths.TUNING, "Tuning", url_path_for(PagePaths.TUNING)),
        PageSpec(PagePaths.SECRETS, "Secrets Healthcheck", url_path_for(PagePaths.SECRETS)),
        PageSpec(PagePaths.DIAGNOSTICS, "Diagnostica", url_path_for(PagePaths.DIAGNOSTICS)),
    ),
}


def page_specs() -> Mapping[str, Sequence[PageSpec]]:
    """Restituisce la descrizione statica delle pagine per gruppo."""
    return _PAGE_GROUPS


def build_pages() -> Dict[str, List[Any]]:
    """
    Restituisce il dict {gruppo: [st.Page(...), ...]} per st.navigation(...).
    """
    st = get_streamlit()

    def make_page(spec: PageSpec) -> Any:
        kwargs = {"title": spec.title}
        if spec.url_path:
            kwargs["url_path"] = spec.url_path
        return st.Page(spec.path, **kwargs)

    return {group: [make_page(spec) for spec in specs] for group, specs in _PAGE_GROUPS.items()}
